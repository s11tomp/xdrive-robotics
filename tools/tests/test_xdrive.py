"""The host library (tools/xdrive): the generated names against the interface JSON the firmware embeds,
and Board against a fake link that behaves like the firmware's endpoint handlers.

The JSON comes from the interface generator with the template the firmware build uses
(`to_c_string` of the endpoint definitions), so no firmware build is needed.

Run from the repo root: python -m pytest -q tools/tests
"""
from __future__ import annotations

import enum
import pathlib
import struct
import subprocess
import sys
import time
from typing import Any, Iterator

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from xdrive import interface  # noqa: E402
from xdrive.board import Board, load_interface  # noqa: E402
from xdrive.enums import AxisError, AxisState, ControlMode  # noqa: E402
from xdrive.errors import InterfaceMismatch, LinkLost, Refused  # noqa: E402
from xdrive.interface import FORMATS, JSON_ENDPOINT, VERSION_OFFSET, Interface  # noqa: E402
from xdrive.model import Call, EndpointRef, Func, Prop, RwProp  # noqa: E402
from xdrive.props import odrv  # noqa: E402
from xdrive import usb as usb_link  # noqa: E402
import usb.core as usb_core  # noqa: E402
import usb.util as usb_util  # noqa: E402

SRC = HERE.parents[1] / "src"


@pytest.fixture(scope="module")
def json_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    out = tmp_path_factory.mktemp("json") / "interface.c"
    subprocess.run([sys.executable, "-B", "../tools/codegen/interface_generator.py", "--definitions",
                    "odrive-interface.yaml", "--generate-endpoints", "ODrive3",
                    "--template", str(HERE / "interface_json.j2"), "--output", str(out)], cwd=SRC, check=True)
    lines = out.read_text().strip().splitlines()  # C string literals, one per line, concatenated by the compiler
    return "".join(line[1:-1].replace('\\"', '"') for line in lines).encode()


def handles(obj: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    for name, value in vars(obj).items():
        if isinstance(value, (Prop, Func)):
            yield path + name, value
        else:
            yield from handles(value, f"{path}{name}.")


def test_props_match_the_interface(json_bytes: bytes) -> None:
    itf = Interface(json_bytes)
    tree = dict(handles(odrv))
    props = {k: v for k, v in tree.items() if isinstance(v, Prop)}
    funcs = {k: v for k, v in tree.items() if isinstance(v, Func)}
    assert set(props) == set(itf.properties)
    assert set(funcs) == set(itf.functions)
    for name, p in props.items():
        ep = itf.properties[name]
        assert p.path == name
        assert isinstance(p, RwProp) == ep.writable, name
        wire = ep.type
        if p.kind is bool:
            assert wire == "bool", name
        elif p.kind is float:
            assert wire == "float", name
        elif p.kind is EndpointRef:
            assert wire == "endpoint_ref", name
        else:
            assert wire in ("uint8", "uint16", "uint32", "uint64", "int32", "int64"), name
    for name, f in funcs.items():
        fn = itf.functions[name]
        assert [a.name for a in f.inputs] == [n for n, _ in fn.inputs], name
        assert [a.name for a in f.outputs] == [n for n, _ in fn.outputs], name


class FakeLink:
    """A board's endpoint table in memory, with the firmware's behavior where Board depends on it.

    `chunk` and `pad` choose how buffer reads end: USB returns up to 61 bytes and nothing past the
    end; CAN returns 4 bytes and zeros past the end.
    """

    def __init__(self, json_bytes: bytes, chunk: int = 61, pad: bool = False) -> None:
        self.json, self.chunk, self.pad = json_bytes, chunk, pad
        self.itf = Interface(json_bytes)
        self.by_id = {ep.id: ep for ep in self.itf.properties.values()}
        for fn in self.itf.functions.values():
            self.by_id.update({ep.id: ep for _, ep in fn.inputs + fn.outputs})
        self.values = {i: bytes(struct.calcsize(FORMATS[ep.type])) for i, ep in self.by_id.items()}
        self.functions = {fn.id: name for name, fn in self.itf.functions.items()}
        self.json_reads = 0
        self.armed = False
        self.rebooting = False
        self.uptime = 5000
        self.put("system_stats.uptime", self.uptime)

    def put(self, name: str, value: Any) -> None:
        ep = self.itf.properties[name]
        self.values[ep.id] = struct.pack(FORMATS[ep.type], value)

    def value(self, name: str) -> Any:
        ep = self.itf.properties[name]
        return struct.unpack(FORMATS[ep.type], self.values[ep.id])[0]

    def describe(self) -> str:
        return "fake"

    def read(self, endpoint_id: int, size: int) -> bytes:
        if endpoint_id not in self.by_id:
            raise Refused(f"endpoint {endpoint_id}")
        return self.values[endpoint_id][:size]

    def write(self, endpoint_id: int, data: bytes) -> bytes:
        ep = self.by_id.get(endpoint_id)
        if ep is None or not ep.writable or len(data) != len(self.values[endpoint_id]):
            raise Refused(f"endpoint {endpoint_id}")
        self.values[endpoint_id] = data
        return data

    def call(self, endpoint_id: int) -> None:
        name = self.functions[endpoint_id]
        fn = self.itf.functions[name]
        if name == "test_function":
            (_, d_in), (_, d_out) = fn.inputs[0], fn.outputs[0]
            total = struct.unpack("<i", self.values[d_out.id])[0] + struct.unpack("<i", self.values[d_in.id])[0]
            self.values[d_out.id] = struct.pack("<i", total)
        elif name == "save_configuration":
            if self.armed:
                self.values[fn.outputs[0][1].id] = struct.pack("<?", False)
                return
            self.rebooting = True
            raise LinkLost("fake: rebooted")
        elif name == "reboot":
            self.rebooting = True
            raise LinkLost("fake: rebooted")

    def read_buffer(self, endpoint_id: int, offset: int) -> bytes:
        assert endpoint_id == JSON_ENDPOINT
        if offset == VERSION_OFFSET:
            return struct.pack("<I", interface.version_id(self.json))
        self.json_reads += 1
        part = self.json[offset:offset + self.chunk]
        return part.ljust(self.chunk, b"\0") if self.pad else part

    def reconnect(self, timeout: float) -> None:
        if self.rebooting:
            self.rebooting = False
            self.put("system_stats.uptime", 120)

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def cache(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path / "xdrive"


@pytest.mark.parametrize("chunk, pad", [(61, False), (4, True)], ids=["usb", "can"])
def test_interface_is_fetched_once_then_cached(json_bytes: bytes, chunk: int, pad: bool, cache: pathlib.Path) -> None:
    link = FakeLink(json_bytes, chunk, pad)
    assert load_interface(link).data == json_bytes
    reads = link.json_reads
    assert reads >= len(json_bytes) // chunk
    assert load_interface(link).data == json_bytes
    assert link.json_reads == reads

    path, = cache.iterdir()
    path.write_bytes(json_bytes[:-1] + b" ")   # a cache file that doesn't match its version ID is ignored
    assert load_interface(link).data == json_bytes
    assert link.json_reads > reads


def test_get_and_set_convert_by_type(json_bytes: bytes) -> None:
    link = FakeLink(json_bytes)
    board = Board(link)
    ax = odrv.axis0
    link.put("axis0.current_state", 8)
    link.put("axis0.error", 0x41)
    link.put("axis0.steps", -(1 << 40))
    assert board.get(ax.current_state) is AxisState.CLOSED_LOOP_CONTROL
    assert board.get(ax.error) == AxisError.INVALID_STATE | AxisError.MOTOR_FAILED
    assert board.get(ax.steps) == -(1 << 40)
    assert board.set(ax.controller.config.vel_limit, 12.5) == 12.5
    assert link.value("axis0.controller.config.vel_limit") == 12.5
    assert board.set(ax.controller.config.vel_limit, 3) == 3.0       # an int for a float property
    assert board.set(ax.controller.config.control_mode, ControlMode.TORQUE_CONTROL) is ControlMode.TORQUE_CONTROL
    assert link.value("axis0.controller.config.control_mode") == ControlMode.TORQUE_CONTROL.value
    reading = board.get_many([ax.current_state, ax.steps])
    assert reading.values == (AxisState.CLOSED_LOOP_CONTROL, -(1 << 40)) and reading.t_end >= reading.t_start


def test_bad_values_and_names_fail_clearly(json_bytes: bytes) -> None:
    link = FakeLink(json_bytes)
    board = Board(link)
    ax = odrv.axis0
    with pytest.raises(TypeError):
        board.set(ax.requested_state, 1)  # type: ignore[misc]  # mypy rejects it too
    with pytest.raises(TypeError):
        board.set(ax.config.can.node_id, True)
    with pytest.raises(ValueError):
        board.set(ax.config.can.node_id, -1)
    link.put("axis0.current_state", 5)  # no AxisState has the value 5
    with pytest.raises(InterfaceMismatch, match="AxisState"):
        board.get(ax.current_state)
    with pytest.raises(InterfaceMismatch, match="no property"):
        board.get(Prop("axis0.no_such_property", float))
    with pytest.raises(InterfaceMismatch, match="vbus_voltage"):
        board.get(RwProp("vbus_voltage", float))  # read-only on the board
    with pytest.raises(InterfaceMismatch, match="vbus_voltage"):
        board.get(Prop("vbus_voltage", int))      # a float on the board


def test_call_writes_inputs_and_reads_outputs(json_bytes: bytes) -> None:
    board = Board(FakeLink(json_bytes))
    assert board.call(odrv.test_function(delta=3)) == 3
    assert board.call(odrv.test_function(delta=-5)) == -2
    assert board.call(odrv.clear_errors()) is None


def test_save_lifecycle(json_bytes: bytes) -> None:
    link = FakeLink(json_bytes)
    board = Board(link)
    link.armed = True
    with pytest.raises(Refused, match="armed"):
        board.save()
    link.armed = False
    board.save()                          # the board reboots: the call raises LinkLost, then reconnects
    assert board.get(odrv.system_stats.uptime) == 120
    link.put("system_stats.uptime", 5000)
    board.reboot()
    assert board.get(odrv.system_stats.uptime) == 120
    with pytest.raises(LinkLost, match="without having rebooted"):
        link.reconnect = lambda timeout: None  # type: ignore[method-assign]
        board.reboot()


def test_enums_are_strict() -> None:
    assert issubclass(AxisState, enum.Enum) and not issubclass(AxisState, int)
    assert issubclass(AxisError, enum.IntFlag)


def test_every_lookup_checks_the_handle(json_bytes: bytes) -> None:
    board = Board(FakeLink(json_bytes))
    board.get(odrv.vbus_voltage)
    with pytest.raises(InterfaceMismatch):
        board.get(Prop("vbus_voltage", int))
    with pytest.raises(InterfaceMismatch):
        board.set(RwProp("vbus_voltage", float), 1.0)


def test_call_needs_every_argument(json_bytes: bytes) -> None:
    board = Board(FakeLink(json_bytes))
    with pytest.raises(TypeError, match="takes 1"):
        board.call(Call(odrv.test_function, ()))


class CorruptJsonLink(FakeLink):
    """Serves a JSON that doesn't match the version ID it reports, and records close()."""
    closed = False

    def read_buffer(self, endpoint_id: int, offset: int) -> bytes:
        good = self.json
        self.json = good[:-1] + b" "
        try:
            return super().read_buffer(endpoint_id, offset) if offset != VERSION_OFFSET else \
                struct.pack("<I", interface.version_id(good))
        finally:
            self.json = good

    def close(self) -> None:
        self.closed = True


def test_failed_connect_closes_the_link(json_bytes: bytes) -> None:
    link = CorruptJsonLink(json_bytes)
    with pytest.raises(LinkLost):
        Board(link)
    assert link.closed


def test_unwritable_cache_only_warns(json_bytes: bytes, tmp_path: pathlib.Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "file").write_text("")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "file"))   # a file, so no cache directory under it
    with pytest.warns(UserWarning, match="can't cache"):
        board = Board(FakeLink(json_bytes))
    assert board.get(odrv.vbus_voltage) == 0.0


class FakeUsbDevice:
    """A board's native USB endpoint pair, answering like src/fibre-cpp/legacy_protocol.cpp."""

    def __init__(self, json_bytes: bytes) -> None:
        self.serial_number = "0123456789AB"
        self.json = json_bytes
        self.crc = interface.version_id(json_bytes) >> 16
        link = FakeLink(json_bytes)
        self.by_id, self.values = link.by_id, link.values
        self.replies: list[bytes] = []
        self.packets: list[tuple[int, int, int, bytes, int]] = []

    def write(self, ep: int, packet: bytes, timeout: int) -> int:
        assert ep == usb_link.EP_OUT and timeout > 0
        seq, endpoint, reply_len = struct.unpack_from("<HHH", packet)
        payload, trailer = packet[6:-2], struct.unpack_from("<H", packet, len(packet) - 2)[0]
        self.packets.append((seq, endpoint, reply_len, payload, trailer))
        endpoint_id = endpoint & 0x7FFF
        if trailer != (interface.PROTOCOL_VERSION if endpoint_id == 0 else self.crc):
            return len(packet)  # the firmware drops a packet with the wrong trailer
        reply_len = min(reply_len, 61)
        if endpoint_id == 0:
            offset = struct.unpack("<I", payload)[0]
            out = (struct.pack("<I", interface.version_id(self.json)) if offset == VERSION_OFFSET
                   else self.json[offset:offset + reply_len])
        elif endpoint_id in self.values:
            out = self.values[endpoint_id]
            if payload and self.by_id[endpoint_id].writable:
                self.values[endpoint_id] = payload
            out = out[:reply_len]
        else:
            out = b""
        if endpoint & 0x8000:
            self.replies.append(struct.pack("<H", seq | 0x8000) + out)
        return len(packet)

    def read(self, ep: int, size: int, timeout: int) -> bytes:
        assert ep == usb_link.EP_IN
        if not self.replies:
            raise usb_core.USBTimeoutError("timeout")
        return self.replies.pop(0)


@pytest.fixture
def usb_device(json_bytes: bytes, monkeypatch: pytest.MonkeyPatch) -> FakeUsbDevice:
    dev = FakeUsbDevice(json_bytes)
    monkeypatch.setattr(usb_core, "find", lambda **kw: [dev])
    for name in ("claim_interface", "release_interface", "dispose_resources"):
        monkeypatch.setattr(usb_util, name, lambda *a: None)
    return dev


def test_usb_link_speaks_the_firmware_protocol(usb_device: FakeUsbDevice) -> None:
    board = usb_link.connect()
    assert board.describe() == "USB 0123456789AB"
    assert board.set(odrv.axis0.controller.config.vel_limit, 7.5) == 7.5
    assert board.get(odrv.axis0.controller.config.vel_limit) == 7.5
    seq, endpoint, reply_len, payload, trailer = usb_device.packets[-1]
    assert endpoint & 0x8000 and reply_len == 4 and payload == b"" and trailer == usb_device.crc
    json_packets = [p for p in usb_device.packets if p[1] & 0x7FFF == 0]
    assert json_packets and all(p[4] == interface.PROTOCOL_VERSION for p in json_packets)


def test_usb_link_skips_stale_replies_and_refuses_short_ones(usb_device: FakeUsbDevice) -> None:
    link = usb_link.UsbLink()
    usb_device.replies.append(struct.pack("<H", 0x8000 | 0x7FFF) + b"\xff" * 4)  # a reply to an older request
    vbus = link.read(Interface(usb_device.json).properties["vbus_voltage"].id, 4)
    assert vbus == bytes(4)
    with pytest.raises(Refused):
        link.read(0x7000, 4)  # no such endpoint: an empty reply
    link.close()
    with pytest.raises(LinkLost):
        link.read(2, 4)


def test_usb_reconnect_retries_while_the_board_enumerates(usb_device: FakeUsbDevice,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    link = usb_link.UsbLink()
    attempts = []

    def find(**kw: Any) -> list[FakeUsbDevice]:
        attempts.append(1)
        if len(attempts) < 3:
            raise usb_core.USBError("device not ready")
        return [usb_device]

    monkeypatch.setattr(usb_core, "find", find)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    link.reconnect(timeout=5.0)
    assert len(attempts) == 3
