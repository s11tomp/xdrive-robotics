#!/usr/bin/env python3
"""Seal a firmware ELF for the CAN bootloader: write the image length, CRC-32 and firmware version into
its image header (APP_START + HEADER_OFFSET, layout in src/bootloader/boot_protocol.hpp).

The CRC covers the image as it lands in flash: the ELF's load segments from APP_START up to the end of
the last one (padding between sections inside a segment is zeros in the ELF), with any gap between
segments erased (0xFF). --bin and --hex write exactly that image, every byte included, so flashing the
ELF, the .bin or the .hex leaves the same bytes in flash. The build runs this on build/firmware.elf
right after linking.

Usage (from the repo root):
  python tools/seal_image.py build/firmware.elf --version-c build/autogen/version.c --bin build/firmware.bin --hex build/firmware.hex
"""
from __future__ import annotations

import argparse
import pathlib
import re
import struct
import sys

from xdrive import boot_frame as bf


def load_segments(raw: bytes) -> list[tuple[int, int, int]]:
    """(flash address, file offset, size) of each PT_LOAD segment with file data."""
    if raw[:4] != b"\x7fELF" or raw[4] != 1 or raw[5] != 1:
        raise SystemExit("not a 32-bit little-endian ELF")
    e_phoff, = struct.unpack_from("<I", raw, 0x1C)
    e_phentsize, e_phnum = struct.unpack_from("<HH", raw, 0x2A)
    segs = []
    for i in range(e_phnum):
        p_type, p_offset, _vaddr, p_paddr, p_filesz = struct.unpack_from("<IIIII", raw, e_phoff + i * e_phentsize)
        if p_type == 1 and p_filesz:
            segs.append((p_paddr, p_offset, p_filesz))
    return sorted(segs)


def flash_image(raw: bytes) -> bytes:
    """The bytes an application ELF leaves in flash from APP_START: its load segments, 0xFF between them."""
    segs = load_segments(raw)
    if not segs or segs[0][0] != bf.APP_START:
        raise SystemExit(f"the image must start at 0x{bf.APP_START:08X} (behind the bootloader), "
                         f"not 0x{segs[0][0] if segs else 0:08X}")
    end = max(addr + size for addr, _, size in segs)
    if end > bf.APP_END:
        raise SystemExit(f"the image ends at 0x{end:08X}, past the application sectors (0x{bf.APP_END:08X})")
    image = bytearray(b"\xff" * (end - bf.APP_START))
    for addr, offset, size in segs:
        image[addr - bf.APP_START:addr - bf.APP_START + size] = raw[offset:offset + size]
    return bytes(image)


def read_version(path: pathlib.Path) -> bytes:
    text = path.read_text()
    parts = [re.search(rf"fw_version_{name}_\s*=\s*(\d+)", text) for name in ("major", "minor", "revision", "unreleased")]
    if not all(parts):
        raise SystemExit(f"{path}: no fw_version_* values")
    return bytes(int(m.group(1)) for m in parts if m)


def intel_hex(base: int, data: bytes) -> str:
    """Intel HEX records for `data` at `base`: extended linear address records, 16-byte data records."""
    def record(kind: int, addr: int, payload: bytes) -> str:
        body = bytes([len(payload), addr >> 8 & 0xFF, addr & 0xFF, kind]) + payload
        return f":{body.hex().upper()}{(-sum(body)) & 0xFF:02X}\n"
    out, upper = [], None
    for off in range(0, len(data), 16):
        addr = base + off
        if addr >> 16 != upper:
            upper = addr >> 16
            out.append(record(4, 0, upper.to_bytes(2, "big")))
        out.append(record(0, addr & 0xFFFF, data[off:off + 16]))
    out.append(record(1, 0, b""))
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elf", type=pathlib.Path)
    ap.add_argument("--version-c", type=pathlib.Path, required=True, help="the build's generated version.c")
    ap.add_argument("--bin", type=pathlib.Path, help="write the sealed image as a raw binary (from APP_START)")
    ap.add_argument("--hex", type=pathlib.Path, help="write the sealed image as Intel HEX")
    args = ap.parse_args(argv)
    raw = bytearray(args.elf.read_bytes())
    segs = load_segments(bytes(raw))
    image = bytearray(flash_image(bytes(raw)))
    if bf.read_header(bytes(image)) is None:
        raise SystemExit("no image header placeholder at APP_START + HEADER_OFFSET")
    image[bf.HEADER_OFFSET + 20:bf.HEADER_OFFSET + 24] = read_version(args.version_c)
    sealed = bf.seal(bytes(image))
    header = sealed[bf.HEADER_OFFSET:bf.HEADER_OFFSET + bf.HEADER.size]
    addr, offset, size = next(s for s in segs if s[0] <= bf.APP_START + bf.HEADER_OFFSET < s[0] + s[2])
    pos = offset + bf.APP_START + bf.HEADER_OFFSET - addr
    raw[pos:pos + len(header)] = header
    args.elf.write_bytes(bytes(raw))
    if args.bin:
        args.bin.write_bytes(sealed)
    if args.hex:
        args.hex.write_text(intel_hex(bf.APP_START, sealed))
    h = bf.read_header(sealed)
    assert h is not None and bf.header_valid(sealed)
    print(f"sealed {args.elf.name}: {h.length} bytes, CRC-32 0x{h.crc:08X}, version {'.'.join(map(str, h.fw_version[:3]))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
