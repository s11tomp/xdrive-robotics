"""One board, over any link: typed reads, writes and function calls by the names in xdrive.props.

    from xdrive import usb
    from xdrive.enums import AxisState
    from xdrive.props import odrv

    with usb.connect() as board:
        board.set(odrv.axis0.requested_state, AxisState.IDLE)
        pos = board.get(odrv.axis0.encoder.pos_estimate)
        ok = board.call(odrv.capture.add_channel(endpoint_id=80))

Every get, set and call is one or more transfers on the link; nothing is read behind the caller's back.
"""
from __future__ import annotations

import enum
import struct
import time
from dataclasses import dataclass
from typing import Any, Sequence, TypeVar

from xdrive import interface
from xdrive.errors import InterfaceMismatch, LinkLost, LinkTimeout, Refused
from xdrive.interface import FORMATS, JSON_ENDPOINT, VERSION_OFFSET, Endpoint, Interface
from xdrive.link import Link
from xdrive.model import Call, EndpointRef, Prop, RwProp
from xdrive.props import odrv

T = TypeVar("T")
INT_TYPES = {"uint8", "uint16", "uint32", "uint64", "int32", "int64"}


def load_interface(link: Link) -> Interface:
    """The board's interface JSON, from the cache or (once per firmware build) over the link."""
    vid = interface.unpack_u32(link.read_buffer(JSON_ENDPOINT, VERSION_OFFSET))
    data = interface.cached(vid)
    if data is None:
        chunks, offset = [], 0
        while True:
            chunk = link.read_buffer(JSON_ENDPOINT, offset)
            if not chunk or 0 in chunk:  # past the end, USB returns nothing and CAN zeros; the JSON has no zero byte
                chunks.append(chunk.split(b"\0")[0])
                break
            chunks.append(chunk)
            offset += len(chunk)
        data = b"".join(chunks)
        if interface.version_id(data) != vid:
            raise LinkLost(f"{link.describe()}: the interface JSON read back doesn't match its version ID {vid:08x}")
        interface.store(data)
    return Interface(data)


def _compatible(kind: type, wire: str) -> bool:
    if kind is bool:
        return wire == "bool"
    if kind is float:
        return wire == "float"
    if kind is EndpointRef:
        return wire == "endpoint_ref"
    return wire in INT_TYPES  # int, and the generated Enum and IntFlag classes


def _decode(kind: type, wire: str, data: bytes) -> Any:
    values = struct.unpack(FORMATS[wire], data)
    if kind is EndpointRef:
        return EndpointRef(*values)
    if issubclass(kind, enum.Enum):
        try:
            return kind(values[0])
        except ValueError:
            raise InterfaceMismatch(f"{values[0]} is not a {kind.__name__}") from None
    return values[0]


def _encode(kind: type, wire: str, value: Any) -> bytes:
    ok = (isinstance(value, (int, float)) and not isinstance(value, bool) if kind is float
          else isinstance(value, kind) and (kind is bool or not isinstance(value, bool)))
    if not ok:
        raise TypeError(f"expected {kind.__name__}, got {value!r}")
    if kind is EndpointRef:
        return struct.pack(FORMATS[wire], *value)
    if isinstance(value, enum.Enum):
        value = value.value
    try:
        return struct.pack(FORMATS[wire], value)
    except struct.error as ex:
        raise ValueError(f"{value!r} doesn't fit a {wire}: {ex}") from None


@dataclass(frozen=True)
class Reading:
    """Values read one after another, and the host's perf_counter() span around the reads."""
    values: tuple[Any, ...]
    t_start: float
    t_end: float


class Board:
    def __init__(self, link: Link) -> None:
        self.link = link
        try:
            self.interface = load_interface(link)
        except BaseException:
            link.close()
            raise

    def __enter__(self) -> Board:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def describe(self) -> str:
        return self.link.describe()

    def _endpoint(self, p: Prop[Any]) -> Endpoint:
        ep = self.interface.properties.get(p.path)
        if ep is None:
            raise InterfaceMismatch(f"{self.describe()}: the board's firmware has no property {p.path}")
        if not _compatible(p.kind, ep.type) or isinstance(p, RwProp) != ep.writable:
            raise InterfaceMismatch(f"{self.describe()}: {p.path} is {ep.type} "
                                    f"({'rw' if ep.writable else 'ro'}) on the board, {p!r} here")
        return ep

    def get(self, p: Prop[T]) -> T:
        ep = self._endpoint(p)
        try:
            data = self.link.read(ep.id, struct.calcsize(FORMATS[ep.type]))
        except Refused as ex:
            raise Refused(f"read {p.path}: {ex}") from None
        value: T = _decode(p.kind, ep.type, data)
        return value

    def set(self, p: RwProp[T], value: T) -> T:
        """Writes the property; returns the value it holds afterwards (what its setter stored)."""
        ep = self._endpoint(p)
        try:
            data = self.link.write(ep.id, _encode(p.kind, ep.type, value))
        except Refused as ex:
            raise Refused(f"write {p.path}: {ex}") from None
        after: T = _decode(p.kind, ep.type, data)
        return after

    def get_many(self, props: Sequence[Prop[Any]]) -> Reading:
        """One read per property, in order. The values come from different control periods."""
        t_start = time.perf_counter()
        values = tuple(self.get(p) for p in props)
        return Reading(values, t_start, time.perf_counter())

    def call(self, c: Call[T]) -> T:
        """Writes the function's inputs, runs it and reads its outputs: None, one value or a tuple."""
        func = c.func
        fn = self.interface.functions.get(func.path)
        if fn is None:
            raise InterfaceMismatch(f"{self.describe()}: the board's firmware has no function {func.path}")
        for here, there in ((func.inputs, fn.inputs), (func.outputs, fn.outputs)):
            if ([a.name for a in here] != [n for n, _ in there]
                    or not all(_compatible(a.kind, ep.type) for a, (_, ep) in zip(here, there))):
                raise InterfaceMismatch(f"{self.describe()}: {func.path} has different arguments on the board")
        if len(c.args) != len(func.inputs):
            raise TypeError(f"{func.path} takes {len(func.inputs)} arguments, got {len(c.args)}")
        try:
            for (_, ep), arg, value in zip(fn.inputs, func.inputs, c.args):
                self.link.write(ep.id, _encode(arg.kind, ep.type, value))
            self.link.call(fn.id)
            outs = tuple(_decode(arg.kind, ep.type, self.link.read(ep.id, struct.calcsize(FORMATS[ep.type])))
                         for (_, ep), arg in zip(fn.outputs, func.outputs))
        except Refused as ex:
            raise Refused(f"call {func.path}: {ex}") from None
        result: Any = None if not outs else outs[0] if len(outs) == 1 else outs
        return result  # type: ignore[no-any-return]

    def save(self, timeout: float = 15.0) -> None:
        """save_configuration(): the board stores its config and reboots. Returns once it is back up.

        The board saves only while the motor is disarmed; armed, it refuses and stays up.
        """
        self._reboot_with(odrv.save_configuration(), timeout)

    def reboot(self, timeout: float = 15.0) -> None:
        """Reboots the board; returns once it is back up."""
        self._reboot_with(odrv.reboot(), timeout)

    def _reboot_with(self, c: Call[Any], timeout: float) -> None:
        uptime = self.get(odrv.system_stats.uptime)
        try:
            result = self.call(c)
        except (LinkTimeout, LinkLost):
            pass  # the board reset before it could reply
        else:
            raise Refused(f"{self.describe()}: {c.func.path} returned {result!r} without rebooting "
                          "(save_configuration refuses while the motor is armed)")
        self.link.reconnect(timeout)
        self.interface = load_interface(self.link)
        if self.get(odrv.system_stats.uptime) >= uptime:
            raise LinkLost(f"{self.describe()}: answered after {c.func.path} without having rebooted")

    def close(self) -> None:
        self.link.close()
