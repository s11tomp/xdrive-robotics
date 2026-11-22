"""The host library (tools/xdrive): the generated names against the interface JSON the firmware embeds,
Board against a fake link that behaves like the firmware's endpoint handlers, the USB link against a
fake device, and the CAN bus against fake boards on python-can's virtual bus.

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
import threading
import time
import uuid
from typing import Any, Iterator

import can as python_can
import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from xdrive import interface, paths, report  # noqa: E402
from xdrive.board import Board, load_interface  # noqa: E402
from xdrive.enums import AxisError, AxisState, ControlMode, MotorError  # noqa: E402
from xdrive.errors import InterfaceMismatch, LinkLost, LinkTimeout, Refused  # noqa: E402
from xdrive.interface import FORMATS, JSON_ENDPOINT, VERSION_OFFSET, Interface  # noqa: E402
from xdrive.model import Call, EndpointRef, Func, Prop, RwProp  # noqa: E402
from xdrive.props import odrv  # noqa: E402
from xdrive import usb as usb_link  # noqa: E402
from xdrive import can as xcan  # noqa: E402
from xdrive import endpoint_frame as ep_frame  # noqa: E402
from xdrive import impedance_frame as imp_frame  # noqa: E402
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


def test_report_decodes_every_bit(json_bytes: bytes) -> None:
    link = FakeLink(json_bytes)
    link.put("axis0.motor.error", MotorError.UNBALANCED_PHASES.value | MotorError.PHASE_RESISTANCE_OUT_OF_RANGE.value)
    link.put("axis0.error", 0x41 | 0x8000_0000)    # bit 31 has no AxisError name
    errs = report.errors(Board(link))
    assert report.jsonable(errs["motor"]) == {"hex": "0x800000001",
                                              "flags": ["PHASE_RESISTANCE_OUT_OF_RANGE", "UNBALANCED_PHASES"]}
    assert report.line(errs["axis"]) == "0x80000041 INVALID_STATE | MOTOR_FAILED | unknown 0x80000000"
    assert report.jsonable(errs["axis"])["unknown_bits"] == "0x80000000"
    assert report.line(errs["encoder"]) == "0x00000000"


def test_paths_give_plain_values_and_take_json_values(json_bytes: bytes) -> None:
    link = FakeLink(json_bytes)
    board = Board(link)
    assert set(paths.HANDLES) == set(Interface(json_bytes).properties)
    link.put("axis0.current_state", 8)
    link.put("axis0.error", 0x41)
    assert paths.get(board, "axis0.current_state") == 8 and type(paths.get(board, "axis0.current_state")) is int
    assert paths.get(board, "axis0.error") == 0x41 and type(paths.get(board, "axis0.error")) is int
    assert paths.set(board, "axis0.controller.config.control_mode", 3) == 3          # an int for an enum
    assert link.value("axis0.controller.config.control_mode") == 3
    assert paths.set(board, "axis0.controller.config.vel_limit", 4) == 4.0           # an int for a float
    assert paths.read(board, [odrv.axis0.current_state, odrv.vbus_voltage]) == [8, 0.0]
    with pytest.raises(TypeError):
        paths.set(board, "axis0.config.enable_watchdog", 1)                          # bools stay strict
    with pytest.raises(KeyError, match="read-only"):
        paths.set(board, "vbus_voltage", 1.0)
    with pytest.raises(KeyError, match="no property"):
        paths.get(board, "axis0.fet_thermistor.temperature")                         # a v0.5.1 name
    link.put("config.gpio12_mode", 12)                                               # the removed ENC1 mode
    assert paths.get(board, "config.gpio12_mode") == 12                              # read as its number
    assert paths.set(board, "config.gpio12_mode", 2) == 2                            # and replaced


@pytest.mark.parametrize("chunk", [61, 4], ids=["usb", "can"])
def test_read_buffer_reads_chunks_up_to_the_size(json_bytes: bytes, chunk: int) -> None:
    board = Board(FakeLink(json_bytes, chunk))
    assert board.read_buffer(JSON_ENDPOINT, 1000) == json_bytes[:1000]
    with pytest.raises(Refused, match="ended after"):
        board.read_buffer(JSON_ENDPOINT, len(json_bytes) + 10)
    assert board.endpoint_id(odrv.vbus_voltage) == Interface(json_bytes).properties["vbus_voltage"].id
    assert board.endpoint_id(odrv.clear_errors) == Interface(json_bytes).functions["clear_errors"].id


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


# ---- CAN: Bus and CanLink against fake boards on python-can's virtual bus ----

class FakeCanBoard:
    """A board on python-can's virtual bus: endpoint access answered like
    src/communication/can/endpoint_frame.hpp over FakeLink's table, impedance commands answered with
    their position, velocity and torque fields copied into the reply, and heartbeats every 20 ms.
    save_configuration and reboot send no reply and leave the board silent for 0.2 s."""

    def __init__(self, json_bytes: bytes, channel: str, node: int) -> None:
        self.link = FakeLink(json_bytes)
        for name, value in (("pos_range", 16.0), ("vel_range", 32.0), ("kp_max", 200.0), ("kd_max", 2.0),
                            ("torque_range", 4.0)):
            self.link.put(f"axis0.config.can.impedance_{name}", value)
        self.node = node
        self.answer_impedance = True
        self.decoy = False       # send a reply for another endpoint before each real endpoint reply
        self.json_frames = 0
        self.down_until = 0.0
        self.bus = python_can.Bus(interface="virtual", channel=channel)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _send(self, cmd: int, data: bytes) -> None:
        self.bus.send(python_can.Message(arbitration_id=self.node << 5 | cmd, is_extended_id=False, data=data))

    def _run(self) -> None:
        next_heartbeat = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= self.down_until and now >= next_heartbeat:
                self._send(xcan.MSG_HEARTBEAT, struct.pack("<IBBBB", self.link.value("axis0.error"),
                                                           self.link.value("axis0.current_state"), 0, 0, 0x80))
                next_heartbeat = now + 0.02
            msg = self.bus.recv(0.005)
            if msg is None or time.monotonic() < self.down_until or msg.arbitration_id >> 5 != self.node:
                continue
            cmd, frame = msg.arbitration_id & 0x1F, bytes(msg.data)
            if cmd == ep_frame.MSG_ENDPOINT:
                reply = self._endpoint(frame)
                if reply is not None:
                    if self.decoy:
                        other = struct.pack("<H", struct.unpack_from("<H", frame, 1)[0] ^ 1)
                        self._send(cmd, bytes([frame[0] | 0x80]) + other + b"\0" + b"\xff" * 4)
                        time.sleep(0.02)  # so a host that took the decoy has returned it before the real reply
                    self._send(cmd, reply)
            elif cmd == imp_frame.MSG_IMPEDANCE and self.answer_impedance:
                torque = (frame[6] & 0xF) << 8 | frame[7]
                self._send(cmd, frame[:3] + bytes([(frame[3] & 0xF0) | torque >> 8, torque & 0xFF,
                                                   imp_frame.FLAG_ARMED, 30, 96]))

    def _endpoint(self, f: bytes) -> bytes | None:
        S = ep_frame.Status
        op, eid, value = f[0], struct.unpack_from("<H", f, 1)[0], f[4:]
        link = self.link

        def reply(status: int, data: bytes = bytes(4)) -> bytes:
            return bytes([op | 0x80]) + f[1:3] + bytes([status]) + data

        known = eid == 0 or eid in link.by_id or eid in link.functions
        if op == ep_frame.Op.READ_BUFFER:
            if eid != JSON_ENDPOINT:
                return reply(S.WRONG_KIND if known else S.UNKNOWN_ENDPOINT)
            offset = struct.unpack("<I", value)[0]
            if offset == VERSION_OFFSET:
                return reply(S.OK, struct.pack("<I", interface.version_id(link.json)))
            self.json_frames += 1
            return reply(S.OK, link.json[offset:offset + 4].ljust(4, b"\0"))
        if not known:
            return reply(S.UNKNOWN_ENDPOINT)
        if op == ep_frame.Op.CALL:
            if eid not in link.functions:
                return reply(S.WRONG_KIND)
            try:
                link.call(eid)
            except LinkLost:  # save_configuration or reboot: the board resets before it replies
                link.reconnect(0)
                self.down_until = time.monotonic() + 0.2
                return None
            return reply(S.OK)
        if eid not in link.by_id:
            return reply(S.WRONG_KIND)
        size = len(link.values[eid])
        if size > 4:
            return reply(S.UNSUPPORTED_TYPE)
        if op == ep_frame.Op.WRITE:
            if not link.by_id[eid].writable:
                return reply(S.WRONG_KIND)
            if any(value[size:]):
                return reply(S.BAD_VALUE)
            link.values[eid] = value[:size]
        elif op != ep_frame.Op.READ:
            return reply(S.BAD_OPCODE)
        return reply(S.OK, link.values[eid].ljust(4, b"\0"))

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()
        self.bus.shutdown()


@pytest.fixture
def can_channel() -> str:
    return f"xdrive-test-{uuid.uuid4()}"


@pytest.fixture
def fakes(json_bytes: bytes, can_channel: str) -> Iterator[list[FakeCanBoard]]:
    boards = [FakeCanBoard(json_bytes, can_channel, node) for node in (1, 2)]
    yield boards
    for b in boards:
        b.stop()


@pytest.fixture
def can_bus(can_channel: str, fakes: list[FakeCanBoard]) -> Iterator[xcan.Bus]:
    # receive_own_messages: the host sees its own frames, as with a gs_usb adapter's echoes
    with xcan.open(timeout=0.2, interface="virtual", channel=can_channel, receive_own_messages=True) as bus:
        yield bus


@pytest.fixture
def cached_json(json_bytes: bytes, cache: pathlib.Path) -> None:
    interface.store(json_bytes)


def test_can_board_reads_writes_and_calls(can_bus: xcan.Bus, fakes: list[FakeCanBoard], cached_json: None) -> None:
    board = can_bus.connect(1)
    vel_limit = odrv.axis0.controller.config.vel_limit
    assert board.describe() == "CAN node 1"
    assert board.set(vel_limit, 7.5) == 7.5
    assert board.get(vel_limit) == 7.5
    assert fakes[0].link.value("axis0.controller.config.vel_limit") == 7.5
    assert fakes[1].link.value("axis0.controller.config.vel_limit") == 0.0
    assert board.set(odrv.axis0.controller.config.control_mode, ControlMode.TORQUE_CONTROL) \
        is ControlMode.TORQUE_CONTROL
    assert board.call(odrv.test_function(delta=3)) == 3
    assert board.call(odrv.test_function(delta=-5)) == -2
    fakes[0].decoy = True        # a reply for another endpoint on the node's ID is not this request's reply
    assert board.get(vel_limit) == 7.5
    with pytest.raises(Refused, match="out of reach"):
        board.get(odrv.axis0.steps)  # int64
    with pytest.raises(Refused, match="UNKNOWN_ENDPOINT"):
        board.link.read(0x7000, 4)
    with pytest.raises(Refused, match="WRONG_KIND"):
        board.link.read(board.interface.functions["test_function"].id, 4)
    board.close()
    with pytest.raises(LinkLost, match="closed"):
        board.get(vel_limit)


def test_can_interface_json_is_read_4_bytes_at_a_time(can_bus: xcan.Bus, fakes: list[FakeCanBoard],
                                                      json_bytes: bytes) -> None:
    board = can_bus.connect(2)
    assert board.interface.data == json_bytes
    assert fakes[1].json_frames == len(json_bytes) // 4 + 1   # the last read ends in zeros
    assert can_bus.connect(2).interface.data == json_bytes      # then from the cache
    assert fakes[1].json_frames == len(json_bytes) // 4 + 1


def test_can_missing_node_times_out(can_bus: xcan.Bus, cached_json: None) -> None:
    t0 = time.monotonic()
    with pytest.raises(LinkTimeout, match="node 5"):
        can_bus.connect(5)
    assert time.monotonic() - t0 < 1.0
    with pytest.raises(ValueError):
        can_bus.connect(64)


def test_can_heartbeats_and_scan(can_bus: xcan.Bus, fakes: list[FakeCanBoard]) -> None:
    fakes[0].link.put("axis0.current_state", 8)
    fakes[0].link.put("axis0.error", 0x41)
    assert can_bus.scan(0.1) == [1, 2]
    hb = can_bus.heartbeat(1)
    assert hb is not None and hb.state is AxisState.CLOSED_LOOP_CONTROL
    assert hb.axis_error == AxisError.INVALID_STATE | AxisError.MOTOR_FAILED
    assert hb.trajectory_done and not hb.motor_error
    assert can_bus.heartbeat(5) is None
    fakes[1].stop()
    assert can_bus.scan(0.1) == [1]


def test_can_cycle_lifecycle(can_bus: xcan.Bus, fakes: list[FakeCanBoard], cached_json: None) -> None:
    """Connect two joints, command them for 50 cycles, lose one, change ranges, save and keep going."""
    with pytest.raises(KeyError, match=r"\[1\]"):
        can_bus.cycle({1: xcan.Impedance(0.0)}, timeout=0.01)
    j1, j2 = can_bus.connect(1), can_bus.connect(2)
    assert can_bus.ranges[1] == imp_frame.Ranges()
    j1.set(odrv.axis0.requested_state, AxisState.CLOSED_LOOP_CONTROL)
    for i in range(50):
        replies = can_bus.cycle({1: xcan.Impedance(pos=0.01 * i, vel=1.0, kp=20.0, torque=0.5),
                                 2: xcan.Impedance(pos=-3.0)}, timeout=0.5)
        r1, r2 = replies[1], replies[2]
        assert r1 is not None and r2 is not None
        assert abs(r1.pos - 0.01 * i) < 0.001 and abs(r1.vel - 1.0) < 0.02 and abs(r1.torque - 0.5) < 0.002
        assert r1.armed and not r1.error and r1.vbus == 24.0
        assert abs(r2.pos + 3.0) < 0.001 and r2.torque == 0.0

    fakes[1].answer_impedance = False    # node 2 stops answering; its own echoed command is not a reply
    t0 = time.monotonic()
    replies = can_bus.cycle({1: xcan.Impedance(pos=1.0), 2: xcan.Impedance(pos=1.0)}, timeout=0.05)
    assert replies[1] is not None and replies[2] is None
    assert 0.05 <= time.monotonic() - t0 < 0.5

    j1.set(odrv.axis0.config.can.impedance_pos_range, 4.0)
    j1 = can_bus.connect(1)               # rereads the ranges
    assert can_bus.ranges[1].pos == 4.0
    reply = can_bus.cycle({1: xcan.Impedance(pos=1.0)}, timeout=0.5)[1]
    assert reply is not None and abs(reply.pos - 1.0) < 0.0002

    fakes[0].link.armed = True
    with pytest.raises(Refused, match="armed"):
        j1.save()
    fakes[0].link.armed = False
    j1.save()                              # no reply, the node goes silent, then answers with a reset uptime
    assert j1.get(odrv.system_stats.uptime) == 120
    reply = can_bus.cycle({1: xcan.Impedance(pos=1.0)}, timeout=0.5)[1]
    assert reply is not None and abs(reply.pos - 1.0) < 0.0002
    j2.close()


def test_can_bus_failure_raises_link_lost(can_bus: xcan.Bus, cached_json: None,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    board = can_bus.connect(1)

    def unplugged(timeout: float) -> None:
        raise python_can.CanOperationError("adapter unplugged")

    monkeypatch.setattr(can_bus._bus, "recv", unplugged)
    with pytest.raises(LinkLost, match="unplugged"):
        for _ in range(100):               # until the reader's next recv fails
            board.get(odrv.vbus_voltage)
    with pytest.raises(LinkLost, match="unplugged"):
        can_bus.cycle({1: xcan.Impedance(0.0)}, timeout=0.05)


def test_can_reconnect_retries_send_errors(can_bus: xcan.Bus, monkeypatch: pytest.MonkeyPatch) -> None:
    link = xcan.CanLink(can_bus, 1)
    real_send = can_bus._bus.send
    failures: list[python_can.Message] = []

    def send(msg: python_can.Message, timeout: float | None = None) -> None:
        if len(failures) < 3:            # nothing acknowledges the frames while the node reboots
            failures.append(msg)
            raise python_can.CanOperationError("transmit buffer full")
        real_send(msg, timeout)

    monkeypatch.setattr(can_bus._bus, "send", send)
    link.reconnect(timeout=2.0)
    assert len(failures) == 3


def test_can_close_ends_requests_in_flight(can_bus: xcan.Bus) -> None:
    link = xcan.CanLink(can_bus, 5, timeout=5.0)    # no node 5: the request waits for its timeout
    raised: list[BaseException] = []

    def request() -> None:
        try:
            link.read(2, 4)
        except BaseException as ex:
            raised.append(ex)

    t = threading.Thread(target=request)
    t0 = time.monotonic()
    t.start()
    time.sleep(0.1)
    can_bus.close()
    t.join()
    assert len(raised) == 1 and isinstance(raised[0], LinkLost)
    assert time.monotonic() - t0 < 1.0
