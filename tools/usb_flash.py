#!/usr/bin/env python3
"""Flash a firmware image to the board over USB through the STM32's built-in DFU bootloader. No ST-Link needed.

Motor moves: every run, dry run included, ends by leaving the bootloader, so the board reboots and its
startup calibration runs. WRITES THE CHIP only with --write.

  1. Find the board: on USB as an ODrive (put axis0 in IDLE, then enter_dfu_mode()), or already in the
     bootloader (USB 0483:df11, e.g. after a failed write or the BOOT0 button held through a reset).
  2. Pre-flash backup: whole flash read over DFU twice (must match) -> backups/<stamp>_<serial>_pre-flash/.
  3. Compare the image with the chip; list the sectors a write erases.
  4. (--write) Erase only those sectors (the config sectors 10-11 stay unless the image covers them), write,
     then read the whole flash back and check it as swd_flash.py does. On a mismatch the board stays in
     the bootloader, and the script prints the restore command.
  5. Leave the bootloader (jump to 0x08000000), wait for the board on USB and for its startup sequence to end.

The bootloader only uses the flash interface (DFU alternate setting 0); option bytes and OTP are never touched.
It is safe to enter on the XDRIVE Mini: it pulls up PB10/PB11 (the brake half-bridge inputs AUX_L/AUX_H),
and the Mini's 3.3 kohm pull-downs (R21, R24) hold them low, as on ODrive v3.5+.

Usage (from the repo root):
  python tools/usb_flash.py --elf build/firmware.elf            # dry run
  python tools/usb_flash.py --elf build/firmware.elf --write    # flash
  python tools/usb_flash.py --bin backups/<dir>/flash.bin --write                  # restore
"""
import argparse
import datetime
import hashlib
import sys
import time
from typing import Any

import usb.core
import usb.util

from logfiles import log_action, rel
from xdrive import usb as xusb
from xdrive.board import Board
from xdrive.enums import AxisState
from xdrive.errors import LinkError, LinkLost, LinkTimeout
from xdrive.props import odrv
from swd_backup import FLASH_BASE
from swd_flash import (SECTORS, bootloader_check, compare, describe_image, load_segments, readback_check, save_backup,
                       sectors_touched)

VID, PID = 0x0483, 0xDF11  # STM32 system bootloader in DFU mode
FLASH_SIZE = 0x100000
LAYOUT = "@Internal Flash  /0x08000000/04*016Kg,01*064Kg,07*128Kg"  # alternate 0 on an STM32F405 (matches SECTORS)
DNLOAD, UPLOAD, GETSTATUS, CLRSTATUS, ABORT = 1, 2, 3, 4, 6
DFU_IDLE, DNLOAD_SYNC, DNBUSY, DNLOAD_IDLE, MANIFEST_SYNC, MANIFEST, UPLOAD_IDLE, DFU_ERROR = 2, 3, 4, 5, 6, 7, 9, 10
OUT, IN = 0x21, 0xA1


class DfuError(Exception):
    pass


class Dfu:
    """ST's DfuSe protocol on the bootloader's flash interface (alternate setting 0)."""

    def __init__(self, dev):
        self.dev = dev
        dev.set_configuration()
        intf = dev.get_active_configuration()[(0, 0)]
        self.layout = usb.util.get_string(dev, intf.iInterface)
        usb.util.claim_interface(dev, 0)
        intf.set_altsetting()
        # The DFU functional descriptor (type 0x21; wTransferSize at bytes 5-6) follows the last alternate
        # setting on ST's bootloader (alternate 3, Device Feature).
        func = [x for i in dev.get_active_configuration() if len(x := bytes(i.extra_descriptors)) >= 9 and x[1] == 0x21]
        if not func:
            raise DfuError("no DFU functional descriptor")
        self.xfer = func[0][5] | (func[0][6] << 8)
        _, state = self.status()
        if state == DFU_ERROR:
            self.dev.ctrl_transfer(OUT, CLRSTATUS, 0, 0, None)
        elif state != DFU_IDLE:
            self.dev.ctrl_transfer(OUT, ABORT, 0, 0, None)
        self.expect(DFU_IDLE)

    def status(self):
        s = self.dev.ctrl_transfer(IN, GETSTATUS, 0, 0, 6, timeout=10000)
        time.sleep((s[1] | (s[2] << 8) | (s[3] << 16)) / 1000)  # bwPollTimeout: the device's requested wait
        return s[0], s[4]

    def expect(self, want):
        while True:
            st, state = self.status()
            if st != 0 or state == DFU_ERROR:
                raise DfuError(f"DFU status {st}, state {state}")
            if state == want:
                return
            if state not in (DNLOAD_SYNC, DNBUSY, MANIFEST_SYNC):
                raise DfuError(f"DFU state {state}, expected {want}")

    def command(self, code, addr):
        """DfuSe command on block 0: 0x21 set the address pointer, 0x41 erase the sector at addr."""
        self.dev.ctrl_transfer(OUT, DNLOAD, 0, 0, bytes([code]) + addr.to_bytes(4, "little"))
        self.expect(DNLOAD_IDLE)

    def idle(self):
        self.dev.ctrl_transfer(OUT, ABORT, 0, 0, None)
        self.expect(DFU_IDLE)

    def erase(self, addr):
        self.command(0x41, addr)
        self.idle()

    def write(self, addr, data):
        # Block n >= 2 lands at pointer + (n - 2) * wTransferSize.
        self.command(0x21, addr)
        for n, off in enumerate(range(0, len(data), self.xfer)):
            self.dev.ctrl_transfer(OUT, DNLOAD, n + 2, 0, data[off:off + self.xfer])
            self.expect(DNLOAD_IDLE)
        self.idle()

    def read(self, addr, size):
        self.command(0x21, addr)
        self.idle()
        out = bytearray()
        for n in range((size + self.xfer - 1) // self.xfer):
            out += self.dev.ctrl_transfer(IN, UPLOAD, n + 2, 0, self.xfer, timeout=5000)
        self.idle()
        if len(out) < size:
            raise DfuError(f"short read: {len(out)} of {size} bytes")
        return bytes(out[:size])

    def leave(self):
        """Jump to the application at 0x08000000. The device drops off USB, so the last status may not arrive."""
        self.command(0x21, FLASH_BASE)
        self.dev.ctrl_transfer(OUT, DNLOAD, 0, 0, None)
        try:
            self.status()
        except usb.core.USBError:
            pass
        usb.util.dispose_resources(self.dev)


def find_dfu(serial=None, timeout=0.0):
    t0 = time.monotonic()
    while True:
        kw = {} if serial is None else {"serial_number": serial}
        dev = usb.core.find(idVendor=VID, idProduct=PID, **kw)
        if dev is not None or time.monotonic() - t0 >= timeout:
            return dev
        time.sleep(0.2)


def connect_firmware(serial=None, timeout=10.0) -> Board:
    """The board running this firmware on USB, waiting up to `timeout` s for it to enumerate."""
    t0 = time.monotonic()
    while True:
        try:
            return xusb.connect(serial)
        except LinkError:
            if time.monotonic() - t0 >= timeout:
                raise
            time.sleep(0.2)


def version(b: Board) -> str:
    return f"{b.get(odrv.fw_version_major)}.{b.get(odrv.fw_version_minor)}.{b.get(odrv.fw_version_revision)}"


def enter_bootloader():
    """Board running this firmware -> IDLE -> enter_dfu_mode(); returns (serial, usb device in DFU, firmware version).

    A board on Makerbase's firmware can't be reached this way: put it in DFU mode first, or flash it over SWD."""
    try:
        b = connect_firmware()
    except LinkError as ex:
        raise SystemExit(f"Board not found on USB running this firmware, nor in DFU mode ({ex}).")
    serial = format(b.get(odrv.serial_number), "X")
    fw = version(b)
    hw = (b.get(odrv.hw_version_major), b.get(odrv.hw_version_minor))
    if hw < (3, 5):
        raise SystemExit(f"hw_version {hw}: the firmware refuses enter_dfu_mode() below 3.5. Stop.")
    b.set(odrv.axis0.requested_state, AxisState.IDLE)
    time.sleep(0.3)
    state = b.get(odrv.axis0.current_state)
    if state is not AxisState.IDLE:
        raise SystemExit(f"Axis didn't go IDLE (state {state.name}). Stop.")
    print(f"USB: board {serial}, fw {fw}, hw {hw[0]}.{hw[1]}, axis0 IDLE. Entering the bootloader...")
    try:
        b.call(odrv.enter_dfu_mode())
    except (LinkLost, LinkTimeout):  # the board resets mid-call
        pass
    b.close()
    dfu = find_dfu(serial, timeout=10)
    if dfu is None:
        raise SystemExit("The board didn't appear in DFU mode within 10 s.")
    return serial, dfu, fw


def wait_for_firmware(serial, timeout=40):
    """After leaving the bootloader: wait for the board on USB and for its startup sequence to settle."""
    try:
        b = connect_firmware(serial, timeout=15)
    except LinkError:
        return {"back_on_usb": False}
    with b:
        ax = odrv.axis0
        t0 = time.monotonic()
        while (b.get(ax.current_state) not in (AxisState.IDLE, AxisState.CLOSED_LOOP_CONTROL)
               and time.monotonic() - t0 < timeout):
            time.sleep(0.2)
        return {"back_on_usb": True, "fw_version": version(b), "axis_state": b.get(ax.current_state).value,
                "odrv_error": int(b.get(odrv.error)), "axis_error": int(b.get(ax.error)),
                "motor_error": int(b.get(ax.motor.error)), "encoder_error": int(b.get(ax.encoder.error))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--elf", help="firmware ELF to flash (load segments at their flash addresses)")
    src.add_argument("--bin", help="raw flash image written at 0x08000000 (e.g. a backup's flash.bin)")
    ap.add_argument("--write", action="store_true", help="actually erase and program the chip (default: dry run)")
    args = ap.parse_args()

    segs, path = load_segments(args)
    total = sum(len(d) for _, d in segs)
    touched = sectors_touched(segs)
    describe_image(segs, path, touched)

    # 1. Find the board.
    record: dict[str, Any] = {"t": datetime.datetime.now().astimezone().isoformat(), "action": "usb_flash" if args.write else "usb_flash_dry_run",
              "image": str(path), "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "image_bytes": total,
              "sectors": [SECTORS.index(t) for t in touched]}
    t0 = time.monotonic()
    usbdev = find_dfu()
    if usbdev is not None:
        serial, record["fw_before"] = usbdev.serial_number, None
        print(f"Board {serial} is already in DFU mode.")
    else:
        serial, usbdev, record["fw_before"] = enter_bootloader()
    record["serial"] = serial
    dfu = Dfu(usbdev)
    print(f"DFU: bootloader up after {time.monotonic() - t0:.1f} s; transfer size {dfu.xfer} B; {dfu.layout.strip()}")
    if dfu.layout.strip() != LAYOUT.strip():
        raise SystemExit("Unexpected flash layout (not an STM32F405 with 1 MB?). Stop; the board stays in DFU mode.")

    # 2. Pre-flash backup.
    print("Pre-flash backup: reading the whole flash twice...")
    t1 = time.monotonic()
    pre = dfu.read(FLASH_BASE, FLASH_SIZE)
    if dfu.read(FLASH_BASE, FLASH_SIZE) != pre:
        raise SystemExit("FAIL: two flash reads differ. Stop; the board stays in DFU mode.")
    print(f"  {2 * FLASH_SIZE / (time.monotonic() - t1) / 1024:.0f} KiB/s")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = save_backup(pre, serial, stamp, f"before flashing {path} over USB DFU")
    record.update(pre_flash_backup=rel(outdir), pre_sha256=hashlib.sha256(pre).hexdigest())

    # 3. Compare.
    refusal, note = bootloader_check(segs, pre)
    if note:
        print(note)
    if refusal:
        print(f"REFUSED: {refusal}. Nothing written.")
        record["refused"] = refusal
    before = compare(segs, pre)
    record["bytes_differing_before"] = before
    print(f"Image vs chip now: {before} of {total} bytes differ" + ("  (the chip already holds this image)" if before == 0 else ""))

    # 4. Program and check.
    if args.write and not refusal:
        t1 = time.monotonic()
        for addr, size in touched:
            print(f"  erase sector {SECTORS.index((addr, size))} (0x{addr:08X}, {size // 1024} KiB)")
            dfu.erase(addr)
        for addr, data in segs:
            print(f"  write 0x{addr:08X} ({len(data)} B)")
            dfu.write(addr, data)
        record["program_s"] = round(time.monotonic() - t1, 1)
        print(f"  erased and written in {record['program_s']} s. Read-back: whole flash...")
        post = dfu.read(FLASH_BASE, FLASH_SIZE)
        record.update(readback_check(segs, touched, pre, post))
        ok = (record["image_bytes_wrong_after"] == 0 and record["untouched_sectors_changed_bytes"] == 0
              and record["erased_not_programmed_non_ff"] == 0)
        print(f"  image bytes wrong: {record['image_bytes_wrong_after']}; changed bytes outside erased sectors: "
              f"{record['untouched_sectors_changed_bytes']}; non-FF bytes in erased-but-unprogrammed areas: "
              f"{record['erased_not_programmed_non_ff']}")
        if not ok:
            record["result"] = "READBACK MISMATCH"
            log_action(record)
            print(f"RESULT: READ-BACK MISMATCH. The board stays in DFU mode. Restore with:\n"
                  f"  python tools/usb_flash.py --bin {rel(outdir)}/flash.bin --write")
            return 4
    else:
        print("Dry run: nothing written.")

    # 5. Leave the bootloader.
    print("Leaving the bootloader: the board reboots and its startup calibration moves the motor...")
    dfu.leave()
    record.update(wait_for_firmware(serial))
    record["total_s"] = round(time.monotonic() - t0, 1)
    errors = [k for k in ("odrv_error", "axis_error", "motor_error", "encoder_error") if record.get(k)]
    ok = record["back_on_usb"] and not errors
    record["result"] = "REFUSED" if refusal else "OK" if ok else "BOARD NOT BACK CLEANLY"
    log_action(record)
    if record["back_on_usb"]:
        print(f"  back on USB: fw {record['fw_version']}, axis0 state {record['axis_state']}, "
              f"errors {({k: record[k] for k in errors}) or 'none'}; {record['total_s']} s in all")
    else:
        print("  the board didn't come back on USB within 15 s")
    if refusal:
        print(f"RESULT: REFUSED, nothing written ({refusal})")
        return 5
    print("RESULT: OK" if ok else "RESULT: check the board (dump_board.py) before driving the motor.")
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
