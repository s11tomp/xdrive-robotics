"""The board over USB: the firmware's native packet protocol, spoken directly with pyusb.

The board's USB interface 2 has one bulk endpoint pair (0x03 out, 0x83 in, 64-byte packets).
A request is one packet, little-endian:

    seq (u16) | endpoint ID | 0x8000 (u16) | reply length (u16) | payload | trailer (u16)

where bit 15 of the endpoint ID asks for a reply and the trailer is the interface JSON's CRC-16
(the protocol version, 1, for endpoint 0). The board runs the endpoint's handler with the payload
and answers with `seq | 0x8000 (u16)` followed by up to `reply length` bytes of output: a property
returns its value (its value before the write, for a write), a buffer returns the bytes at the
payload's offset. A failed handler writes no output, so a short reply is a refusal; a failed
write or call with no output bytes requested is invisible, which is why `write` asks for the old value.
Source: src/fibre-cpp/legacy_protocol.cpp.
"""
from __future__ import annotations

import struct
import threading
import time
from typing import Any

import usb.core
import usb.util

from xdrive.board import Board
from xdrive.errors import LinkError, LinkLost, LinkTimeout, Refused
from xdrive.interface import JSON_ENDPOINT, PROTOCOL_VERSION, VERSION_OFFSET, unpack_u32

VID, PID = 0x1209, 0x0D32
INTERFACE, EP_OUT, EP_IN, MTU = 2, 0x03, 0x83, 64


def serials() -> list[str]:
    """Serial numbers of the boards on USB."""
    return [serial for _, serial in _boards()]


def _boards() -> list[tuple[Any, str]]:
    """(device, serial number) of each board on USB. A board that is still enumerating (after a
    reboot) can make pyusb raise; that is a LinkError, so a reconnect loop retries it."""
    try:
        return [(d, d.serial_number) for d in usb.core.find(find_all=True, idVendor=VID, idProduct=PID)]
    except (usb.core.USBError, ValueError) as ex:
        raise LinkError(f"USB: can't list the boards ({ex})") from ex


class UsbLink:

    def __init__(self, serial: str | None = None, timeout: float = 1.0) -> None:
        self.timeout_ms = int(timeout * 1000)
        self._lock = threading.Lock()
        self._seq = 0
        self._dev: Any = None
        self.serial = serial
        self._open(serial)

    def _open(self, serial: str | None) -> None:
        boards = [(d, s) for d, s in _boards() if serial is None or s == serial]
        if not boards:
            raise LinkError(f"no board on USB{f' with serial {serial}' if serial else ''}")
        if len(boards) > 1:
            raise LinkError(f"{len(boards)} boards on USB ({', '.join(s for _, s in boards)}): pick one by serial")
        dev, found = boards[0]
        try:
            usb.util.claim_interface(dev, INTERFACE)
        except usb.core.USBError as ex:
            usb.util.dispose_resources(dev)
            raise LinkError(f"USB {found}: can't claim the interface ({ex}); is another tool connected?") from ex
        self._dev, self.serial = dev, found
        try:
            self._drain()
            version = self.read_buffer(JSON_ENDPOINT, VERSION_OFFSET)
            if len(version) != 4:
                raise LinkError(f"{self.describe()}: no interface version ID ({version.hex()})")
        except LinkError:
            self.close()
            raise
        self._crc = unpack_u32(version) >> 16

    def _drain(self) -> None:
        """Drops a reply left over from a process that stopped mid-transfer."""
        try:
            while True:
                self._dev.read(EP_IN, MTU, 20)
        except usb.core.USBError:
            pass

    def describe(self) -> str:
        return f"USB {self.serial}"

    def _transact(self, endpoint_id: int, payload: bytes, reply_len: int, trailer: int) -> bytes:
        with self._lock:
            if self._dev is None:
                raise LinkLost(f"{self.describe()}: the link is closed")
            self._seq = (self._seq + 1) & 0x7FFF
            seq = self._seq
            packet = struct.pack("<HHH", seq, endpoint_id | 0x8000, reply_len) + payload + struct.pack("<H", trailer)
            try:
                self._dev.write(EP_OUT, packet, self.timeout_ms)
                while True:
                    reply = bytes(self._dev.read(EP_IN, MTU, self.timeout_ms))
                    if len(reply) >= 2 and struct.unpack_from("<H", reply)[0] == seq | 0x8000:
                        return reply[2:]
                    # a reply to an earlier, timed-out request: skip it
            except usb.core.USBTimeoutError as ex:
                raise LinkTimeout(f"{self.describe()}: no reply for endpoint {endpoint_id}") from ex
            except usb.core.USBError as ex:
                raise LinkLost(f"{self.describe()}: {ex}") from ex

    def read(self, endpoint_id: int, size: int) -> bytes:
        reply = self._transact(endpoint_id, b"", size, self._crc)
        if len(reply) != size:
            raise Refused(f"{self.describe()}: endpoint {endpoint_id} returned {len(reply)} of {size} bytes")
        return reply

    def write(self, endpoint_id: int, data: bytes) -> bytes:
        old = self._transact(endpoint_id, data, len(data), self._crc)
        if len(old) != len(data):
            raise Refused(f"{self.describe()}: write to endpoint {endpoint_id} failed")
        return self.read(endpoint_id, len(data))

    def call(self, endpoint_id: int) -> None:
        self._transact(endpoint_id, b"", 0, self._crc)

    def read_buffer(self, endpoint_id: int, offset: int) -> bytes:
        trailer = PROTOCOL_VERSION if endpoint_id == JSON_ENDPOINT else self._crc
        return self._transact(endpoint_id, struct.pack("<I", offset), MTU - 2, trailer)  # the board sends at most 61

    def reconnect(self, timeout: float) -> None:
        self.close()
        deadline = time.monotonic() + timeout
        while True:
            try:
                self._open(self.serial)
                return
            except LinkError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)

    def close(self) -> None:
        if self._dev is not None:
            try:
                usb.util.release_interface(self._dev, INTERFACE)
            except usb.core.USBError:
                pass  # the board is gone (rebooted or unplugged)
            usb.util.dispose_resources(self._dev)
            self._dev = None


def connect(serial: str | None = None, timeout: float = 1.0) -> Board:
    """The board on USB (the only one, or the one with this serial number)."""
    return Board(UsbLink(serial, timeout))
