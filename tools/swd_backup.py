#!/usr/bin/env python3
"""Read-only SWD backup of the board's STM32F405 over an ST-Link (via OpenOCD).

Never halts, resets, erases or writes the MCU: it connects with `reset_config none`
and only reads memory while the firmware keeps running. Put the axis in IDLE first
(idle.py) anyway, so nothing is driving the motor if the link misbehaves.

What it reads:
  - DBGMCU_IDCODE, flash size, 96-bit unique ID (-> the ODrive serial, to confirm
    which board is connected), FLASH_OPTCR (read protection level, write protection)
  - with --dump (default): the whole flash twice (the two reads must match), the
    OTP area (528 B) and the raw option bytes, plus a SHA-256 manifest

Output: backups/<stamp>_<serial>/ (flash.bin, otp.bin, optbytes.bin,
manifest.json); one line appended to logs/actions.jsonl.

Usage (from the repo root):
  python tools/swd_backup.py --probe      # identify only, no dump
  python tools/swd_backup.py              # identify + full backup
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
BACKUPS = WORKDIR / "backups"

FLASH_BASE = 0x08000000
NVM_START = 0x080C0000          # ODrive config lives in sectors 10-11 (0x080C0000, 0x080E0000)
OTP_BASE, OTP_LEN = 0x1FFF7800, 528
OPTBYTES_BASE, OPTBYTES_LEN = 0x1FFFC000, 16
UID_BASE = 0x1FFF7A10
FLASH_SIZE_REG = 0x1FFF7A22
DBGMCU_IDCODE = 0xE0042000
FLASH_OPTCR = 0x40023C14

OPENOCD_BASE = [
    "openocd",
    "-f", "interface/stlink.cfg",
    "-f", "target/stm32f4x.cfg",
    "-c", "adapter speed 1000",       # conservative; the stand has motor noise
    "-c", "reset_config none",        # never touch NRST, never sysresetreq
    "-c", "init",
]


def openocd(cmds, timeout=120):
    """Run OpenOCD with read-only commands; return its combined output."""
    args = list(OPENOCD_BASE)
    for c in cmds:
        args += ["-c", c]
    args += ["-c", "shutdown"]
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    out = p.stdout + p.stderr
    if p.returncode != 0:
        sys.stderr.write(out)
        raise SystemExit(f"OpenOCD failed (exit {p.returncode}); see output above.")
    return out


def words_at(out, addr):
    """Parse `mdw`/`mdh` output lines like '0x1fff7a10: 00380024 31315104 ...'."""
    m = re.search(rf"^0x{addr:08x}:\s+((?:[0-9a-f]+\s*)+)$", out, re.M | re.I)
    if not m:
        raise SystemExit(f"Could not read 0x{addr:08X}; OpenOCD output:\n{out}")
    return [int(w, 16) for w in m.group(1).split()]


def probe():
    out = openocd([
        f"mdw 0x{DBGMCU_IDCODE:08x}",
        f"mdh 0x{FLASH_SIZE_REG:08x}",
        f"mdw 0x{UID_BASE:08x} 3",
        f"mdw 0x{FLASH_OPTCR:08x}",
    ])
    idcode = words_at(out, DBGMCU_IDCODE)[0]
    flash_kb = words_at(out, FLASH_SIZE_REG)[0]
    uid = words_at(out, UID_BASE)
    optcr = words_at(out, FLASH_OPTCR)[0]
    # ODrive fw: serial = ((uid0 + uid2) mod 2^32) << 16 | uid1 >> 16
    serial = (((uid[0] + uid[2]) & 0xFFFFFFFF) << 16) | (uid[1] >> 16)
    rdp = (optcr >> 8) & 0xFF
    info = {
        "dev_id": f"0x{idcode & 0xFFF:03X}",            # 0x413 = STM32F405/407
        "rev_id": f"0x{idcode >> 16:04X}",
        "flash_kb": flash_kb,
        "uid": [f"0x{w:08X}" for w in uid],
        "serial": format(serial, "X"),
        "optcr": f"0x{optcr:08X}",
        "rdp_byte": f"0x{rdp:02X}",
        "rdp_level": 0 if rdp == 0xAA else (2 if rdp == 0xCC else 1),
        "nwrp_sectors": f"0x{(optcr >> 16) & 0xFFF:03X}",  # 0xFFF = no sector write-protected
        "bor_lev": (optcr >> 2) & 3,
    }
    return info, out


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="identify the chip only; no dump")
    args = ap.parse_args()

    info, _ = probe()
    print(f"STM32 dev_id {info['dev_id']} rev {info['rev_id']}, flash {info['flash_kb']} KB")
    print(f"UID {' '.join(info['uid'])}  ->  ODrive serial {info['serial']}")
    print(f"FLASH_OPTCR {info['optcr']}: RDP byte {info['rdp_byte']} (level {info['rdp_level']}), "
          f"nWRP {info['nwrp_sectors']}, BOR_LEV {info['bor_lev']}")
    if info["dev_id"] != "0x413":
        print("WARNING: not an STM32F405/407 (expected dev_id 0x413).")
    if info["rdp_level"] != 0:
        print("Read protection is ON: flash can't be read over SWD. Stop here; removing it mass-erases.")
        return 2

    record = {"t": datetime.datetime.now().astimezone().isoformat(), "action": "swd_backup" if not args.probe else "swd_probe", **info}
    if not args.probe:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        outdir = BACKUPS / f"{stamp}_{info['serial']}"
        outdir.mkdir(parents=True)
        size = info["flash_kb"] * 1024
        with tempfile.TemporaryDirectory() as td:
            second = pathlib.Path(td) / "flash2.bin"
            print(f"Reading {size // 1024} KB of flash twice, plus OTP and option bytes (≈1-2 min)...")
            openocd([
                f"dump_image {outdir / 'flash.bin'} 0x{FLASH_BASE:08x} 0x{size:x}",
                f"dump_image {second} 0x{FLASH_BASE:08x} 0x{size:x}",
                f"dump_image {outdir / 'otp.bin'} 0x{OTP_BASE:08x} {OTP_LEN}",
                f"dump_image {outdir / 'optbytes.bin'} 0x{OPTBYTES_BASE:08x} {OPTBYTES_LEN}",
            ], timeout=600)
            flash = (outdir / "flash.bin").read_bytes()
            if len(flash) != size or flash != second.read_bytes():
                print("FAIL: the two flash reads differ (or are short). Check wiring/ground; try again.")
                return 3
        record["dir"] = str(outdir.relative_to(WORKDIR))
        record["sha256"] = {f.name: sha256(f) for f in sorted(outdir.glob("*.bin"))}
        fw_end = NVM_START - FLASH_BASE
        used = len(flash[:fw_end].rstrip(b"\xff"))
        record["firmware_bytes_used"] = used
        (outdir / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"Saved to {outdir.relative_to(WORKDIR)}/  (both reads identical)")
        print(f"  firmware region uses {used} bytes (0x{FLASH_BASE:08X}..0x{FLASH_BASE + used:08X})")
        for k, v in record["sha256"].items():
            print(f"  sha256 {k}: {v}")

    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
