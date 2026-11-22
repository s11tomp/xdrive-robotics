"""The boards on a CAN bus: the same `Board` as over USB, through endpoint access (0x1F), plus
heartbeats and one impedance command (0x1E) per joint per control cycle.

    from xdrive import can
    from xdrive.props import odrv

    with can.open(interface="gs_usb", channel=0, bitrate=1_000_000) as bus:
        print(bus.scan())                                    # node IDs heard in heartbeats: [1, 2]
        j1 = bus.connect(1)                                  # a Board, as over USB
        j1.set(odrv.axis0.controller.config.vel_gain, 0.05)
        replies = bus.cycle({1: can.Impedance(pos=0.25, kp=20.0, kd=0.3)}, timeout=0.002)

`open()` passes its arguments to python-can's `can.Bus`. One reader thread takes every frame off
the bus and routes it by node ID (arbitration ID >> 5) and command (the low 5 bits); frames this
host sent (python-can's `is_rx` false: gs_usb adapters echo them) are never replies.

- Endpoint access: each request is one frame pair, so a node has one request in flight at a time
  (a per-node lock). The reply must echo the request's opcode and endpoint ID; other replies on
  the node's ID are dropped. A reply that arrives after its request timed out can be taken for the
  next request with the same opcode and endpoint ID, even one with a different value or offset.
- Impedance: the board answers on the command's own ID. `cycle()` sends one command per node and
  waits for one reply per node up to the timeout. A reply that arrives after its cycle's timeout and
  during the next cycle can be taken for that cycle's reply (one cycle old); outside a cycle replies
  are dropped.
- A failure of the bus (`recv` raising, an adapter unplugged) stops the reader; every later request
  raises LinkLost with that failure.

Frames: docs/can.md.
"""
from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

import can

from xdrive import endpoint_frame as ep
from xdrive import impedance_frame
from xdrive.board import Board
from xdrive.enums import AxisError, AxisState
from xdrive.errors import InterfaceMismatch, LinkError, LinkLost, LinkTimeout, Refused
from xdrive.impedance_frame import MSG_IMPEDANCE, Ranges, Reply
from xdrive.interface import JSON_ENDPOINT, VERSION_OFFSET
from xdrive.props import odrv

MSG_HEARTBEAT = 0x01
NODE_IDS = range(64)   # standard 11-bit IDs: 6 bits of node ID, 5 of command


def arbitration_id(node_id: int, cmd: int) -> int:
    return node_id << 5 | cmd


@dataclass(frozen=True)
class Impedance:
    """One impedance command: torque = kp·(pos − position) + kd·(vel − velocity) + torque."""
    pos: float               # turn
    vel: float = 0.0         # turn/s
    kp: float = 0.0          # Nm/turn
    kd: float = 0.0          # Nm/(turn/s)
    torque: float = 0.0      # Nm, feed-forward


@dataclass(frozen=True)
class Heartbeat:
    axis_error: AxisError
    state: AxisState
    motor_error: bool        # motor.error is non-zero
    encoder_error: bool
    controller_error: bool
    trajectory_done: bool
    t: float                 # host time.monotonic() at receipt


def decode_heartbeat(data: bytes, t: float) -> Heartbeat:
    axis_error, state, motor, encoder, controller = struct.unpack("<IBBBB", data)
    try:
        axis_state = AxisState(state)
    except ValueError:
        raise InterfaceMismatch(f"heartbeat: {state} is not an AxisState") from None
    return Heartbeat(AxisError(axis_error), axis_state, bool(motor), bool(encoder), bool(controller & 1),
                     bool(controller & 0x80), t)


class Bus:
    """The boards on one CAN bus. Takes ownership of the python-can bus: `close()` shuts it down.

    `ranges` holds each connected node's impedance ranges (axis0.config.can.impedance_*), read by
    `connect()`; after changing them on a board, `connect()` it again.
    """

    def __init__(self, bus: can.BusABC, timeout: float = 1.0) -> None:
        self._bus = bus
        self.timeout = timeout
        self.ranges: dict[int, Ranges] = {}
        self._cond = threading.Condition()
        self._node_locks = {n: threading.Lock() for n in NODE_IDS}
        self._cycle_lock = threading.Lock()
        self._send_lock = threading.Lock()              # python-can buses aren't thread-safe for send
        self._pending: dict[int, bytes] = {}            # node -> the reply's first 3 bytes it waits for
        self._endpoint_replies: dict[int, bytes] = {}
        self._heartbeats: dict[int, tuple[bytes, float]] = {}
        self._awaiting: set[int] = set()                # nodes whose impedance reply the current cycle waits for
        self._impedance_replies: dict[int, bytes] = {}
        self._error: BaseException | None = None
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read, name="xdrive-can-reader", daemon=True)
        self._reader.start()

    def __enter__(self) -> Bus:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _read(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self._bus.recv(0.05)
            except Exception as ex:  # any failure of the adapter ends the reader; requests then raise LinkLost
                with self._cond:
                    self._error = ex
                    self._cond.notify_all()
                return
            if msg is not None:
                self._route(msg)

    def _route(self, msg: can.Message) -> None:
        if msg.is_extended_id or msg.is_remote_frame or msg.is_error_frame or not msg.is_rx or msg.dlc != 8:
            return
        node, cmd, data = msg.arbitration_id >> 5, msg.arbitration_id & 0x1F, bytes(msg.data)
        with self._cond:
            if cmd == MSG_HEARTBEAT:
                self._heartbeats[node] = (data, time.monotonic())
            elif cmd == ep.MSG_ENDPOINT:
                if self._pending.get(node) == data[:3]:
                    self._endpoint_replies[node] = data
            elif cmd == MSG_IMPEDANCE:
                if node in self._awaiting:
                    self._impedance_replies[node] = data
            else:
                return
            self._cond.notify_all()

    def _ended(self) -> bool:
        return self._error is not None or self._stop.is_set()

    def _check(self) -> None:
        if self._error is not None:
            raise LinkLost(f"CAN: the bus failed: {self._error!r}")
        if self._stop.is_set():
            raise LinkLost("CAN: the bus is closed")

    def _send(self, arb_id: int, data: bytes, timeout: float) -> None:
        try:
            with self._send_lock:
                self._bus.send(can.Message(arbitration_id=arb_id, is_extended_id=False, data=data), timeout=timeout)
        except can.CanError as ex:
            raise LinkError(f"CAN: can't send to ID 0x{arb_id:03x}: {ex}") from ex

    def endpoint_request(self, node: int, frame: bytes, timeout: float) -> ep.Reply:
        """Sends one endpoint-access request and returns its reply; LinkTimeout if none comes in time."""
        with self._node_locks[node]:
            with self._cond:
                self._check()
                self._pending[node] = bytes([frame[0] | ep.REPLY_FLAG]) + frame[1:3]
                self._endpoint_replies.pop(node, None)
            try:
                self._send(arbitration_id(node, ep.MSG_ENDPOINT), frame, timeout)
                with self._cond:
                    self._cond.wait_for(lambda: node in self._endpoint_replies or self._ended(), timeout)
                    self._check()
                    data = self._endpoint_replies.pop(node, None)
            finally:
                with self._cond:
                    self._pending.pop(node, None)
        if data is None:
            raise LinkTimeout(f"CAN node {node}: no endpoint reply (opcode {frame[0]}, "
                              f"endpoint {struct.unpack_from('<H', frame, 1)[0]})")
        try:
            return ep.decode_reply(data)
        except ValueError as ex:
            raise LinkError(f"CAN node {node}: {ex}") from None

    def heartbeat(self, node: int) -> Heartbeat | None:
        """The node's latest heartbeat, or None if none has been heard since the bus was opened."""
        with self._cond:
            self._check()
            hb = self._heartbeats.get(node)
        return None if hb is None else decode_heartbeat(*hb)

    def scan(self, timeout: float = 0.3) -> list[int]:
        """Node IDs that send a heartbeat within `timeout` (the default heartbeat interval is 0.1 s)."""
        start = time.monotonic()
        time.sleep(timeout)
        with self._cond:
            self._check()
            return sorted(n for n, (_, t) in self._heartbeats.items() if t >= start)

    def connect(self, node: int, timeout: float | None = None) -> Board:
        """A Board for the node, over endpoint access; also reads the node's impedance ranges."""
        board = Board(CanLink(self, node, self.timeout if timeout is None else timeout))
        try:
            c = odrv.axis0.config.can
            self.ranges[node] = Ranges(*(board.get(p) for p in (c.impedance_pos_range, c.impedance_vel_range,
                                                                c.impedance_kp_max, c.impedance_kd_max,
                                                                c.impedance_torque_range)))
        except BaseException:
            board.close()
            raise
        return board

    def cycle(self, commands: Mapping[int, Impedance], timeout: float) -> dict[int, Reply | None]:
        """Sends one impedance command per node and returns each node's reply, None for a node that
        didn't answer within `timeout`. Returns as soon as every node has answered."""
        missing = [n for n in commands if n not in self.ranges]
        if missing:
            raise KeyError(f"CAN nodes {missing}: connect() them first, to read their impedance ranges")
        frames = {n: impedance_frame.encode_command(self.ranges[n], c.pos, c.vel, c.kp, c.kd, c.torque)
                  for n, c in commands.items()}
        with self._cycle_lock:
            with self._cond:
                self._check()
                self._impedance_replies.clear()
                self._awaiting = set(commands)
            try:
                for n, frame in frames.items():
                    self._send(arbitration_id(n, MSG_IMPEDANCE), frame, timeout)
                with self._cond:
                    self._cond.wait_for(lambda: len(self._impedance_replies) == len(commands) or self._ended(),
                                        timeout)
                    self._check()
                    got = dict(self._impedance_replies)
            finally:
                with self._cond:
                    self._awaiting = set()
                    self._impedance_replies.clear()
        return {n: impedance_frame.decode_reply(self.ranges[n], got[n]) if n in got else None for n in commands}

    def close(self) -> None:
        if not self._stop.is_set():
            with self._cond:
                self._stop.set()
                self._cond.notify_all()               # requests in flight raise LinkLost now
            self._reader.join()
            self._bus.shutdown()


def open(timeout: float = 1.0, **kwargs: Any) -> Bus:  # noqa: A001  (the module's entry point, as usb.connect)
    """A Bus on a python-can bus: `open(interface="gs_usb", channel=0, bitrate=1_000_000)`."""
    return Bus(can.Bus(**kwargs), timeout)


class CanLink:
    """One node's endpoints over endpoint access: 4 bytes per request, so properties wider than
    4 bytes (uint64: `motor.error`, `axis0.steps`; `serial_number`) are out of reach."""

    def __init__(self, bus: Bus, node: int, timeout: float = 1.0) -> None:
        if node not in NODE_IDS:
            raise ValueError(f"CAN node ID {node} is outside 0..63")
        self.bus, self.node, self.timeout = bus, node, timeout
        self._closed = False

    def describe(self) -> str:
        return f"CAN node {self.node}"

    def _request(self, frame: bytes, timeout: float | None = None) -> bytes:
        if self._closed:
            raise LinkLost(f"{self.describe()}: the link is closed")
        reply = self.bus.endpoint_request(self.node, frame, self.timeout if timeout is None else timeout)
        if reply.status != ep.Status.OK:
            raise Refused(f"{self.describe()}: endpoint {reply.endpoint_id}: {reply.status.name}")
        return reply.data

    def _fits(self, endpoint_id: int, size: int) -> None:
        if size > 4:
            raise Refused(f"{self.describe()}: endpoint {endpoint_id} is {size} bytes wide, "
                          "out of reach over CAN (4 at most)")

    def read(self, endpoint_id: int, size: int) -> bytes:
        self._fits(endpoint_id, size)
        return self._request(ep.read_request(endpoint_id))[:size]

    def write(self, endpoint_id: int, data: bytes) -> bytes:
        self._fits(endpoint_id, len(data))
        return self._request(ep.request(ep.Op.WRITE, endpoint_id, data.ljust(4, b"\0")))[:len(data)]

    def call(self, endpoint_id: int) -> None:
        self._request(ep.call_request(endpoint_id))

    def read_buffer(self, endpoint_id: int, offset: int, timeout: float | None = None) -> bytes:
        return self._request(ep.read_buffer_request(endpoint_id, offset), timeout)

    def reconnect(self, timeout: float) -> None:
        """Polls the interface version ID until the node answers again (it needs no heartbeat). A
        send error counts as no answer: with the rebooting node the only other one on the bus,
        nothing acknowledges the frames and the adapter's queue fills."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.read_buffer(JSON_ENDPOINT, VERSION_OFFSET, timeout=0.1)
                return
            except LinkLost:
                raise
            except LinkError:
                if time.monotonic() > deadline:
                    raise

    def close(self) -> None:
        self._closed = True
