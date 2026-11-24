"""The flash tools' bootloader check (swd_flash.bootloader_check, also used by usb_flash.py)."""
from __future__ import annotations

import struct

from swd_flash import bootloader_check
from xdrive import boot_frame as bf

BASE = 0x08000000
MARKER = struct.pack("<I", bf.BOOTLOADER_MAGIC)
OLD_CHIP = b"\x00" * 0x100000                                            # an image linked at 0x08000000
NEW_CHIP = (bytes(bf.HEADER_OFFSET) + MARKER).ljust(0x100000, b"\xff")    # the CAN bootloader in sectors 0-1
APP = [(bf.APP_START, b"\x01" * 64)]


def test_an_app_behind_the_bootloader_needs_the_bootloader() -> None:
    refusal, note = bootloader_check(APP, OLD_CHIP)
    assert refusal is not None and "firmware-with-bootloader.bin" in refusal and note is None
    assert bootloader_check(APP, NEW_CHIP) == (None, None)


def test_an_image_from_0x08000000_may_replace_the_bootloader_with_a_note() -> None:
    old_image = [(BASE, b"\x02" * 0x400)]
    refusal, note = bootloader_check(old_image, NEW_CHIP)
    assert refusal is None and note is not None and "replaces the CAN bootloader" in note
    assert bootloader_check(old_image, OLD_CHIP) == (None, None)
    combined = [(BASE, (bytes(bf.HEADER_OFFSET) + MARKER).ljust(0x8000, b"\xff") + b"\x03" * 64)]
    assert bootloader_check(combined, NEW_CHIP) == (None, None)
    assert bootloader_check(combined, OLD_CHIP) == (None, None)
