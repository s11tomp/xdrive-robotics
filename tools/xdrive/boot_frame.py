"""Codec for the CAN bootloader's frames and the application image header (no I/O).

Mirrors src/bootloader/boot_protocol.hpp, which documents the layout; tools/tests/test_boot_frame.py
runs this codec against that header compiled on the host.
"""
from __future__ import annotations

import enum
import struct
import zlib
from dataclasses import dataclass

TAG = 0xB
SERIAL_MASK = 0xFFFFF
BROADCAST = SERIAL_MASK
PROTOCOL_VERSION = 1
NODE_UNKNOWN = 0xFF

BOOT_START = 0x08000000
APP_START = 0x08008000
APP_END = 0x080C0000
APP_SIZE = APP_END - APP_START
BLOCK_MAX = 1024

HEADER_OFFSET = 0x200
IMAGE_MAGIC = 0x4D494458          # "XDIM"
HEADER_VERSION = 1
HW_XDRIVE_MINI = 0x00030656
HEADER = struct.Struct("<IIIII4s8x")  # magic, header_version, length, crc, hw, fw_version
HEADER_CRC_OFFSET = HEADER_OFFSET + 12
BOOTLOADER_MAGIC = 0x4C544258     # "XBTL", at BOOT_START + HEADER_OFFSET


class Cmd(enum.IntEnum):
    DISCOVER = 0
    ERASE = 1
    BLOCK_START = 2
    DATA = 3
    BLOCK_END = 4
    VERIFY = 5
    START_APP = 6


class Status(enum.IntEnum):
    OK = 0
    BAD_COMMAND = 1
    BAD_LENGTH = 2
    OUT_OF_RANGE = 3
    BAD_CRC = 4
    FLASH_ERROR = 5
    NO_VALID_IMAGE = 6
    NO_BLOCK = 7


FLAG_IMAGE_VALID = 1 << 0
FLAG_REQUESTED = 1 << 1


def make_id(from_board: bool, cmd: int, serial20: int) -> int:
    return TAG << 25 | int(from_board) << 24 | (cmd & 0xF) << 20 | serial20 & SERIAL_MASK


@dataclass(frozen=True)
class Id:
    ours: bool
    from_board: bool
    cmd: int
    serial20: int


def parse_id(arb_id: int) -> Id:
    return Id((arb_id >> 25) & 0xF == TAG, bool((arb_id >> 24) & 1), (arb_id >> 20) & 0xF, arb_id & SERIAL_MASK)


def serial20(serial: int) -> int:
    return serial & SERIAL_MASK


# --- host requests: (arbitration ID, data) -------------------------------------------------------
def discover(serial: int | None = None) -> tuple[int, bytes]:
    """Discover every board in the bootloader (serial None) or one board."""
    return make_id(False, Cmd.DISCOVER, BROADCAST if serial is None else serial20(serial)), b""


def erase(serial: int, length: int) -> tuple[int, bytes]:
    return make_id(False, Cmd.ERASE, serial20(serial)), struct.pack("<I", length)


def block(serial: int, offset: int, data: bytes) -> list[tuple[int, bytes]]:
    """The frames of one block: BLOCK_START, DATA frames of up to 8 bytes, BLOCK_END with the CRC."""
    s = serial20(serial)
    frames = [(make_id(False, Cmd.BLOCK_START, s), struct.pack("<II", offset, len(data)))]
    frames += [(make_id(False, Cmd.DATA, s), data[i:i + 8]) for i in range(0, len(data), 8)]
    frames.append((make_id(False, Cmd.BLOCK_END, s), struct.pack("<I", zlib.crc32(data))))
    return frames


def verify(serial: int) -> tuple[int, bytes]:
    return make_id(False, Cmd.VERIFY, serial20(serial)), b""


def start_app(serial: int) -> tuple[int, bytes]:
    return make_id(False, Cmd.START_APP, serial20(serial)), b""


# --- board answers -------------------------------------------------------------------------------
@dataclass(frozen=True)
class Discovered:
    serial: int
    node_id: int | None
    image_valid: bool
    requested: bool
    protocol_version: int


def decode_discover(data: bytes) -> Discovered:
    if len(data) != 8:
        raise ValueError(f"discover answer must be 8 bytes, got {len(data)}")
    node = data[6]
    return Discovered(int.from_bytes(data[:6], "little"), None if node == NODE_UNKNOWN else node,
                      bool(data[7] & FLAG_IMAGE_VALID), bool(data[7] & FLAG_REQUESTED), data[7] >> 4)


def status(data: bytes) -> Status:
    if not data:
        raise ValueError("empty answer")
    return Status(data[0])


def decode_block_end(data: bytes) -> tuple[Status, int]:
    """(status, the block's offset)."""
    if len(data) != 5:
        raise ValueError(f"BLOCK_END answer must be 5 bytes, got {len(data)}")
    return Status(data[0]), struct.unpack_from("<I", data, 1)[0]


def decode_verify(data: bytes) -> tuple[Status, int]:
    """(status, the image length when valid)."""
    if len(data) != 6:
        raise ValueError(f"VERIFY answer must be 6 bytes, got {len(data)}")
    return Status(data[0]), struct.unpack_from("<I", data, 2)[0]


# --- the image header ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ImageHeader:
    length: int
    crc: int
    hw: int
    fw_version: tuple[int, int, int, int]


def image_crc(image: bytes) -> int:
    """CRC-32 of an application image (starting at APP_START) with the header's crc field as zero."""
    return zlib.crc32(image[:HEADER_CRC_OFFSET] + bytes(4) + image[HEADER_CRC_OFFSET + 4:])


def read_header(image: bytes) -> ImageHeader | None:
    """The header of an image starting at APP_START, None if its magic or version doesn't match."""
    if len(image) < HEADER_OFFSET + HEADER.size:
        return None
    magic, version, length, crc, hw, fw = HEADER.unpack_from(image, HEADER_OFFSET)
    if magic != IMAGE_MAGIC or version != HEADER_VERSION:
        return None
    return ImageHeader(length, crc, hw, (fw[0], fw[1], fw[2], fw[3]))


def header_valid(image: bytes) -> bool:
    """The checks the bootloader makes before it starts an application image."""
    h = read_header(image)
    return (h is not None and h.hw == HW_XDRIVE_MINI and HEADER_OFFSET + HEADER.size <= h.length <= APP_SIZE
            and h.length <= len(image) and image_crc(image[:h.length]) == h.crc)


def seal(image: bytes) -> bytes:
    """Writes the length and CRC into an image whose header carries the magic, version, hw and
    firmware version (the linker's placeholder); returns the sealed image."""
    h = read_header(image)
    if h is None:
        raise ValueError("no image header at APP_START + HEADER_OFFSET")
    out = bytearray(image)
    struct.pack_into("<I", out, HEADER_OFFSET + 8, len(image))
    struct.pack_into("<I", out, HEADER_CRC_OFFSET, 0)
    struct.pack_into("<I", out, HEADER_CRC_OFFSET, image_crc(bytes(out)))
    return bytes(out)
