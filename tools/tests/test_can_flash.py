"""can_flash.py end to end against a fake CAN bootloader on python-can's virtual bus.

The fake speaks the bootloader's protocol (src/bootloader/boot_protocol.hpp; test_boot_frame.py checks the
codec against the real one) over a flash array. For --node it sits behind a fake application board
(test_xdrive's FakeCanBoard) and answers once that board's enter_can_bootloader() has run.
"""
from __future__ import annotations

import json
import pathlib
import struct
import threading
import uuid
import zlib
from typing import Any, Iterator

import can as python_can
import pytest

from test_boot_frame import make_image
from test_xdrive import FakeCanBoard, FakeLink, cache, json_bytes  # noqa: F401  (fixtures)
from xdrive import boot_frame as bf
from xdrive.enums import AxisState

import can_flash  # noqa: E402

SERIAL = 0x2F0034523235


class FakeBootloader:
    def __init__(self, channel: str, node: int | None = None, link: FakeLink | None = None,
                 image: bytes | None = None, drop_data: int = 0) -> None:
        self.node, self.link, self.drop_data = node, link, drop_data
        self.flash = bytearray(b"\xff" * bf.APP_SIZE)
        if image is not None:
            self.flash[:len(image)] = image
        self.frames = 0
        self.started = False
        self.erases = 0
        self.block: bytearray | None = None
        self.block_offset = self.block_len = 0
        self.bus = python_can.Bus(interface="virtual", channel=channel)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()
        self.thread.join()
        self.bus.shutdown()

    @property
    def active(self) -> bool:
        return self.link.in_bootloader if self.link is not None else not self.started

    def _valid(self) -> bool:
        return bf.header_valid(bytes(self.flash))

    def _reply(self, cmd: int, data: bytes) -> None:
        self.bus.send(python_can.Message(arbitration_id=bf.make_id(True, cmd, SERIAL), data=data, is_extended_id=True))

    def _run(self) -> None:
        while not self.stopped.is_set():
            msg = self.bus.recv(0.02)
            if msg is None or not msg.is_extended_id or not self.active:
                continue
            i = bf.parse_id(msg.arbitration_id)
            if not i.ours or i.from_board:
                continue
            if i.serial20 != bf.serial20(SERIAL) and not (i.serial20 == bf.BROADCAST and i.cmd == bf.Cmd.DISCOVER):
                continue
            self.frames += 1
            self._handle(i.cmd, bytes(msg.data))

    def _handle(self, cmd: int, data: bytes) -> None:
        flags = (bf.FLAG_IMAGE_VALID if self._valid() else 0) | (bf.FLAG_REQUESTED if self.link else 0) | bf.PROTOCOL_VERSION << 4
        if cmd == bf.Cmd.DISCOVER:
            self._reply(cmd, SERIAL.to_bytes(6, "little") + bytes([bf.NODE_UNKNOWN if self.node is None else self.node, flags]))
        elif cmd == bf.Cmd.ERASE:
            length, = struct.unpack("<I", data)
            self.flash[:length] = b"\xff" * length
            self.erases += 1
            self._reply(cmd, bytes([bf.Status.OK]))
        elif cmd == bf.Cmd.BLOCK_START:
            self.block_offset, self.block_len = struct.unpack("<II", data)
            self.block = bytearray()
        elif cmd == bf.Cmd.DATA and self.block is not None:
            if self.drop_data:
                self.drop_data -= 1  # a frame lost on the bus
            else:
                self.block += data
        elif cmd == bf.Cmd.BLOCK_END:
            crc, = struct.unpack("<I", data)
            status = (bf.Status.NO_BLOCK if self.block is None else bf.Status.BAD_LENGTH if len(self.block) != self.block_len
                      else bf.Status.BAD_CRC if zlib.crc32(self.block) != crc else bf.Status.OK)
            if status is bf.Status.OK and self.block is not None:
                self.flash[self.block_offset:self.block_offset + self.block_len] = self.block
            self.block = None
            self._reply(cmd, bytes([status]) + struct.pack("<I", self.block_offset))
        elif cmd == bf.Cmd.VERIFY:
            h = bf.read_header(bytes(self.flash))
            ok = self._valid() and h is not None
            self._reply(cmd, bytes([bf.Status.OK if ok else bf.Status.NO_VALID_IMAGE, flags])
                        + struct.pack("<I", h.length if ok and h is not None else 0))
        elif cmd == bf.Cmd.START_APP:
            if not self._valid():
                self._reply(cmd, bytes([bf.Status.NO_VALID_IMAGE]))
                return
            self._reply(cmd, bytes([bf.Status.OK]))
            self.started = True
            if self.link is not None:
                self.link.in_bootloader = False


@pytest.fixture
def channel(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.chdir(tmp_path)
    return f"can-flash-{uuid.uuid4()}"


@pytest.fixture
def image(tmp_path: pathlib.Path) -> tuple[bytes, pathlib.Path]:
    img = make_image(9000, seed=7)
    path = tmp_path / "firmware.bin"
    path.write_bytes(img)
    return img, path


def run(channel: str, *args: str) -> int:
    return can_flash.main(["--interface", "virtual", "--channel", channel, *args])


def last_log(tmp_path: pathlib.Path) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((tmp_path / "logs" / "actions.jsonl").read_text().splitlines()[-1])
    return out


def test_write_by_serial(channel: str, image: tuple[bytes, pathlib.Path], tmp_path: pathlib.Path) -> None:
    img, path = image
    fake = FakeBootloader(channel)
    try:
        assert run(channel, "--bin", str(path), "--serial", f"{SERIAL:X}", "--write") == 0
        assert bytes(fake.flash[:len(img)]) == img and fake.started and fake.erases == 1
        assert last_log(tmp_path)["result"] == "OK"
    finally:
        fake.stop()


def test_a_lost_frame_sends_the_block_again(channel: str, image: tuple[bytes, pathlib.Path], tmp_path: pathlib.Path) -> None:
    img, path = image
    fake = FakeBootloader(channel, drop_data=1)
    try:
        assert run(channel, "--bin", str(path), "--write") == 0     # the only board in the bootloader
        assert bytes(fake.flash[:len(img)]) == img
        assert last_log(tmp_path)["block_retries"] == 1
    finally:
        fake.stop()


def test_an_invalid_image_is_refused_before_the_bus(channel: str, image: tuple[bytes, pathlib.Path]) -> None:
    img, path = image
    bad = bytearray(img)
    bad[-1] ^= 1
    path.write_bytes(bytes(bad))
    fake = FakeBootloader(channel)
    try:
        assert run(channel, "--bin", str(path), "--write") == 1
        assert fake.frames == 0
    finally:
        fake.stop()


def test_dry_run_starts_the_current_image(channel: str, image: tuple[bytes, pathlib.Path]) -> None:
    img, path = image
    fake = FakeBootloader(channel, image=img)
    try:
        assert run(channel, "--bin", str(path), "--serial", f"{SERIAL:X}") == 0
        assert fake.started and fake.erases == 0
    finally:
        fake.stop()


def test_no_valid_image_stays_in_the_bootloader(channel: str, image: tuple[bytes, pathlib.Path]) -> None:
    _, path = image
    fake = FakeBootloader(channel)                                   # erased: nothing to start
    try:
        assert run(channel, "--bin", str(path)) == 2
        assert not fake.started
    finally:
        fake.stop()


@pytest.fixture
def app_board(json_bytes: bytes, channel: str, image: tuple[bytes, pathlib.Path]) -> Iterator[tuple[FakeCanBoard, FakeBootloader]]:  # noqa: F811
    img, _ = image
    h = bf.read_header(img)
    assert h is not None
    app = FakeCanBoard(json_bytes, channel, 3)
    app.link.put("axis0.current_state", AxisState.IDLE.value)
    for name, value in zip(("major", "minor", "revision", "unreleased"), h.fw_version):
        app.link.put(f"fw_version_{name}", value)
    boot = FakeBootloader(channel, node=3, link=app.link)
    yield app, boot
    boot.stop()
    app.stop()


def test_write_by_node(app_board: tuple[FakeCanBoard, FakeBootloader], image: tuple[bytes, pathlib.Path],
                       channel: str, cache: pathlib.Path) -> None:  # noqa: F811
    app, boot = app_board
    img, path = image
    assert run(channel, "--bin", str(path), "--node", "3", "--write") == 0
    assert bytes(boot.flash[:len(img)]) == img and boot.started and not app.link.in_bootloader


def test_a_node_that_stays_armed_is_left_alone(app_board: tuple[FakeCanBoard, FakeBootloader],
                                              image: tuple[bytes, pathlib.Path], channel: str,
                                              cache: pathlib.Path) -> None:  # noqa: F811
    app, boot = app_board
    app.link.armed = True                                            # the fake ignores the IDLE request
    app.link.put("axis0.current_state", AxisState.CLOSED_LOOP_CONTROL.value)
    assert run(channel, "--bin", str(image[1]), "--node", "3", "--write") == 2
    assert boot.frames == 0 and not app.link.in_bootloader
