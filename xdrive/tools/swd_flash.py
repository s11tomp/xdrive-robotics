#!/usr/bin/env python3
"""Flash a firmware image to the board over SWD (ST-Link + OpenOCD), with checks on both sides.

WRITES THE CHIP only with --write. Without --write it stops after step 4.

  1. Identify the chip over SWD (read-only) and check that its serial matches the board on
     USB (so the ST-Link and the USB cable are on the same board), and that read protection is off.
  2. Put axis0 in IDLE over USB (motor limp, PWM off).
  3. Full pre-flash backup: whole flash read twice (must match) -> backups/<stamp>_<serial>_pre-flash/.
  4. Compare the image's load segments with what's on the chip now; list the sectors a write erases.
  5. (--write) OpenOCD: reset init, flash write_image erase <elf>, verify_image, reset run.
     Only the sectors the image covers are erased; the config sectors (10-11) are untouched.
  6. (--write) Read the whole flash back: the image must be there, sectors the image doesn't
     touch must equal the pre-flash backup, and erased bytes outside the image must be FF.

After step 5 the board reboots and runs its startup sequence: THE MOTOR MOVES (calibration).

Input: an ELF (load segments at their flash addresses), e.g. Firmware/build/ODriveFirmware.elf.
To restore a backup, use --bin <flash.bin> (written at 0x08000000, whole file).

Usage (from the repo root):
  python xdrive/tools/swd_flash.py --elf Firmware/build/ODriveFirmware.elf            # dry run
  python xdrive/tools/swd_flash.py --elf Firmware/build/ODriveFirmware.elf --write    # flash
  python xdrive/tools/swd_flash.py --bin backups/<dir>/flash.bin --write                  # restore
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import time

from swd_backup import FLASH_BASE, NVM_START, probe, openocd as openocd_readonly

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
BACKUPS = WORKDIR / "backups"

# STM32F405: 4 x 16 KB, 1 x 64 KB, 7 x 128 KB.
SECTORS = [(0x08000000 + o, s) for o, s in
           [(0x0000, 0x4000), (0x4000, 0x4000), (0x8000, 0x4000), (0xC000, 0x4000), (0x10000, 0x10000)]
           + [(0x20000 + i * 0x20000, 0x20000) for i in range(7)]]

# Flashing needs halt/reset, so this is NOT swd_backup's read-only `reset_config none`. stm32f4x.cfg's
# default (srst_nogate) resets through NRST: wire the ST-Link's RST to J2 pin 5.
OPENOCD_FLASH = ["openocd", "-f", "interface/stlink.cfg", "-f", "target/stm32f4x.cfg",
                 "-c", "adapter speed 1000", "-c", "init"]


def load_segments(args):
    """Return [(address, bytes)] to program, plus a description of the source file."""
    if args.bin:
        data = pathlib.Path(args.bin).read_bytes()
        return [(FLASH_BASE, data)], pathlib.Path(args.bin)
    path = pathlib.Path(args.elf)
    raw = path.read_bytes()
    if raw[:4] != b"\x7fELF" or raw[4] != 1 or raw[5] != 1:
        raise SystemExit(f"{path} is not a 32-bit little-endian ELF")
    e_phoff, = struct.unpack_from("<I", raw, 0x1C)
    e_phentsize, e_phnum = struct.unpack_from("<HH", raw, 0x2A)
    segs = []
    for i in range(e_phnum):
        p_type, p_offset, _vaddr, p_paddr, p_filesz = struct.unpack_from("<IIIII", raw, e_phoff + i * e_phentsize)
        if p_type == 1 and p_filesz:                       # PT_LOAD with file data -> goes to flash at LMA
            if not (FLASH_BASE <= p_paddr and p_paddr + p_filesz <= FLASH_BASE + 0x100000):
                raise SystemExit(f"segment at 0x{p_paddr:08X} is outside flash")
            segs.append((p_paddr, raw[p_offset:p_offset + p_filesz]))
    if not segs:
        raise SystemExit("no loadable segments in the ELF")
    return sorted(segs), path


def sectors_touched(segs):
    return [(a, s) for a, s in SECTORS if any(sa < a + s and a < sa + len(d) for sa, d in segs)]


def full_dump(tag):
    """Read the whole flash twice (read-only, target keeps running); return (bytes, saved path)."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as td:
        a, b = pathlib.Path(td) / "a.bin", pathlib.Path(td) / "b.bin"
        openocd_readonly([f"dump_image {a} 0x{FLASH_BASE:08x} 0x100000",
                          f"dump_image {b} 0x{FLASH_BASE:08x} 0x100000"], timeout=600)
        data = a.read_bytes()
        if len(data) != 0x100000 or data != b.read_bytes():
            raise SystemExit("FAIL: two flash reads differ (or are short). Check the SWD wiring.")
    return data, stamp


def compare(segs, flash):
    diffs = 0
    for addr, d in segs:
        o = addr - FLASH_BASE
        diffs += sum(x != y for x, y in zip(d, flash[o:o + len(d)]))
    return diffs


def save_backup(data, serial, stamp, reason):
    """Save a whole-flash read under backups/<stamp>_<serial>_pre-flash/, or reuse an identical backup."""
    sha = hashlib.sha256(data).hexdigest()
    same = [p for p in sorted(BACKUPS.glob("*/flash.bin")) if hashlib.sha256(p.read_bytes()).hexdigest() == sha]
    if same:
        print(f"  identical to the existing backup {same[0].parent.relative_to(WORKDIR)}/ (sha256 {sha[:16]}…), not saved again")
        return same[0].parent
    outdir = BACKUPS / f"{stamp}_{serial}_pre-flash"
    outdir.mkdir(parents=True)
    (outdir / "flash.bin").write_bytes(data)
    (outdir / "manifest.json").write_text(json.dumps({"t": stamp, "serial": serial, "reason": reason,
                                                      "sha256": {"flash.bin": sha}}, indent=2) + "\n")
    print(f"  saved {outdir.relative_to(WORKDIR)}/flash.bin (sha256 {sha[:16]}…)")
    return outdir


def readback_check(segs, touched, pre, post):
    """Compare a whole-flash read after programming with the image and the pre-flash read."""
    erased = [(a - FLASH_BASE, s) for a, s in touched]
    def in_erased(o): return any(eo <= o < eo + es for eo, es in erased)
    covered = set()
    for a, d in segs:
        covered.update(range(a - FLASH_BASE, a - FLASH_BASE + len(d)))
    return {"post_sha256": hashlib.sha256(post).hexdigest(),
            "image_bytes_wrong_after": compare(segs, post),
            "untouched_sectors_changed_bytes": sum(1 for o in range(len(post)) if not in_erased(o) and post[o] != pre[o]),
            "erased_not_programmed_non_ff": sum(1 for o in range(len(post)) if in_erased(o) and o not in covered and post[o] != 0xFF),
            "whole_flash_identical_to_before": post == pre}


def board_on_usb():
    import odrive
    from odrive.enums import AXIS_STATE_IDLE
    dev = odrive.find_any(timeout=10)
    if dev is None:
        return None, None
    dev.axis0.requested_state = AXIS_STATE_IDLE
    time.sleep(0.3)
    return format(dev.serial_number, "X"), dev.axis0.current_state


def log(record):
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--elf", help="firmware ELF to flash (load segments at their flash addresses)")
    src.add_argument("--bin", help="raw flash image written at 0x08000000 (e.g. a backup's flash.bin)")
    ap.add_argument("--write", action="store_true", help="actually erase and program the chip (default: dry run)")
    ap.add_argument("--no-usb", action="store_true", help="proceed without the board on USB (no serial cross-check, no IDLE)")
    args = ap.parse_args()

    segs, path = load_segments(args)
    total = sum(len(d) for _, d in segs)
    touched = sectors_touched(segs)
    print(f"Image {path}: {len(segs)} segment(s), {total} bytes, sha256 {hashlib.sha256(path.read_bytes()).hexdigest()[:16]}…")
    for a, d in segs:
        print(f"  0x{a:08X}..0x{a + len(d):08X} ({len(d)} B)")
    print("Sectors a write erases: " + ", ".join(f"{SECTORS.index(t)} (0x{t[0]:08X})" for t in touched))
    if any(a + s > NVM_START for a, s in touched):
        print("NOTE: the image covers the config sectors (10-11): the board's saved config gets replaced too.")

    # 1. Identify over SWD.
    info, _ = probe()
    print(f"SWD: STM32 dev {info['dev_id']}, flash {info['flash_kb']} KB, serial {info['serial']}, RDP level {info['rdp_level']}")
    if info["dev_id"] != "0x413" or info["flash_kb"] != 1024:
        raise SystemExit("Not an STM32F405 with 1 MB flash. Stop.")
    if info["rdp_level"] != 0:
        raise SystemExit("Read protection is on. Stop.")

    # 2. Same board on USB; IDLE.
    if not args.no_usb:
        usb_serial, state = board_on_usb()
        if usb_serial is None:
            raise SystemExit("Board not found on USB (use --no-usb to proceed without the cross-check and IDLE).")
        if usb_serial != info["serial"]:
            raise SystemExit(f"USB board serial {usb_serial} != SWD chip serial {info['serial']}. Stop.")
        print(f"USB: same board ({usb_serial}); axis0 state now {state} (1 = IDLE)")
        if state != 1:
            raise SystemExit("Axis didn't go IDLE. Stop.")

    # 3. Pre-flash backup.
    print("Pre-flash backup: reading the whole flash twice...")
    pre, stamp = full_dump("pre")
    pre_sha = hashlib.sha256(pre).hexdigest()
    outdir = save_backup(pre, info["serial"], stamp, f"before flashing {path}")

    # 4. Compare.
    before = compare(segs, pre)
    print(f"Image vs chip now: {before} of {total} bytes differ" + ("  (the chip already holds this image)" if before == 0 else ""))
    record = {"t": datetime.datetime.now().astimezone().isoformat(), "action": "swd_flash" if args.write else "swd_flash_dry_run",
              "image": str(path), "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "image_bytes": total,
              "serial": info["serial"], "pre_flash_backup": str(outdir.relative_to(WORKDIR)), "pre_sha256": pre_sha,
              "bytes_differing_before": before, "sectors": [SECTORS.index(t) for t in touched]}
    if not args.write:
        print("Dry run: nothing written. Add --write to flash.")
        log(record)
        return 0

    # 5. Program.
    print("Programming (reset init, erase + write, verify, reset run)...")
    if args.bin:
        prog = [f"flash write_image erase {path} 0x{FLASH_BASE:08x} bin", f"verify_image {path} 0x{FLASH_BASE:08x} bin"]
    else:
        prog = [f"flash write_image erase {path}", f"verify_image {path}"]
    cmd = list(OPENOCD_FLASH) + sum([["-c", c] for c in ["reset init", *prog, "reset run", "shutdown"]], [])
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    out = p.stdout + p.stderr
    record["openocd_exit"] = p.returncode
    record["openocd_tail"] = out.strip().splitlines()[-8:]
    print("\n".join("  " + ln for ln in out.strip().splitlines()[-8:]))
    if p.returncode != 0 or "verified" not in out:
        record["result"] = "FAILED"
        log(record)
        print(f"FLASH FAILED (exit {p.returncode}). Restore with:\n  python xdrive/tools/swd_flash.py --bin {outdir.relative_to(WORKDIR)}/flash.bin --write")
        return 3
    print(f"  done in {time.time() - t0:.1f} s. The board is rebooting: startup calibration moves the motor.")

    # 6. Read back.
    time.sleep(2)
    print("Read-back: reading the whole flash twice...")
    post, _ = full_dump("post")
    record.update(readback_check(segs, touched, pre, post))
    img_diffs, outside_changed, stray = (record[k] for k in ("image_bytes_wrong_after", "untouched_sectors_changed_bytes",
                                                             "erased_not_programmed_non_ff"))
    ok = img_diffs == 0 and outside_changed == 0 and stray == 0
    record["result"] = "OK" if ok else "READBACK MISMATCH"
    log(record)
    print(f"  image bytes wrong: {img_diffs}; changed bytes outside erased sectors: {outside_changed}; "
          f"non-FF bytes in erased-but-unprogrammed areas: {stray}")
    print(f"  whole flash identical to the pre-flash backup: {record['whole_flash_identical_to_before']}")
    print("RESULT: OK" if ok else "RESULT: READ-BACK MISMATCH: investigate before driving the motor.")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
