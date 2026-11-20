#!/usr/bin/env python3
"""Change board settings safely: dump first, write, read back, optionally save.

  python xdrive/tools/set_config.py [--save] path=value [path=value ...]
  python xdrive/tools/set_config.py [--save] --file configs/<board>.json [path=value ...]
  e.g. python xdrive/tools/set_config.py --save axis0.encoder.config.calib_range=0.05

- Refuses unless axis0 is IDLE (nothing is driving the motor).
- Runs dump_board.py first, so the pre-change config is in logs/.
- Values are typed from the property (bool: true/false/1/0, int, float).
- Reads every value back and reports old -> new.
- --file: a JSON file {"settings": {path: value}} (e.g. xdrive/examples/dji-10018.json),
  or a dump_board.py *_config-backup.json (nested, odrivetool restore-config format). The backup
  restores a board's own calibration results (R/L, encoder offset, pre_calibrated) after a flash
  that reset its config, without moving the motor. Backup keys the board's firmware doesn't have
  (e.g. from an older firmware) are skipped and listed. Assignments on the command line are applied after it.
- --save calls save_configuration().
  - v0.5.1: writes flash and does NOT reboot. The flash write breaks PWM/ADC timing until a
    reboot, so reboot before moving.
  - v0.5.2+ (this firmware): the board saves and reboots by itself, and THE STARTUP SEQUENCE
    RUNS (if startup calibration is enabled, the motor moves).
- Never erases. Appends the change set to logs/actions.jsonl.
"""
import argparse
import datetime
import json
import math
import pathlib
import subprocess
import sys

import odrive
from dump_board import connect
from odrive.enums import AXIS_STATE_IDLE

from sample import resolve

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"


def parse(prop, text):
    t = prop._property_type
    if not isinstance(text, str):          # typed value from a JSON file
        return t(text)
    if t is bool:
        if text.lower() in ("true", "1"):
            return True
        if text.lower() in ("false", "0"):
            return False
        raise ValueError(f"not a bool: {text}")
    return t(float(text)) if t is int else t(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", action="store_true", help="save_configuration() after writing")
    ap.add_argument("--file", help='JSON file {"settings": {path: value}} or a *_config-backup.json, applied before the assignments')
    ap.add_argument("assignments", nargs="*", metavar="path=value")
    args = ap.parse_args()
    if not args.file and not args.assignments:
        ap.error("nothing to set")
    pairs = []
    backup_paths = set()  # keys from a config backup; skipped when the board's firmware doesn't have them
    if args.file:
        doc = json.loads(pathlib.Path(args.file).read_text())
        if "settings" in doc:
            pairs.extend(doc["settings"].items())
        else:
            def flatten(obj, prefix):
                for k, v in obj.items():
                    path = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, dict):
                        yield from flatten(v, path)
                    else:
                        yield path, v
            backup = list(flatten(doc, ""))
            backup_paths = {path for path, _ in backup}
            pairs.extend(backup)
    for a in args.assignments:
        path, _, val = a.partition("=")
        if not val:
            ap.error(f"expected path=value, got {a!r}")
        pairs.append((path.strip(), val.strip()))

    # Pre-change snapshot (separate process; read-only)
    r = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent / "dump_board.py"), "--label", "pre-set-config"],
                       capture_output=True, text=True)
    snap = [l for l in r.stdout.splitlines() if "_dump.json" in l]
    if r.returncode != 0 or not snap:
        print("Pre-change dump failed; not changing anything.\n" + r.stdout + r.stderr)
        return 1
    print("pre-change dump: " + snap[0].split()[-1])

    dev = connect(timeout=10)
    if dev is None:
        print("No board found on USB.")
        return 1
    serial = format(dev.serial_number, "X")
    if dev.axis0.current_state != AXIS_STATE_IDLE:
        print(f"axis0 is not IDLE (state {dev.axis0.current_state}); not changing anything.")
        return 2

    props = []
    skipped = []
    for path, text in pairs:  # validate everything before writing anything
        try:
            prop = resolve(dev, path)
        except KeyError:
            if path not in backup_paths:
                raise
            skipped.append(path)
            continue
        if not prop._can_write:
            print(f"{path} is read-only")
            return 2
        props.append((path, prop, parse(prop, text)))
    if skipped:
        # A top-level object the firmware lacks entirely (e.g. axis1) prints as one line.
        tops = {path.split(".")[0] for path in skipped}
        gone = {t for t in tops if all(p.split(".")[0] != t or p in skipped for p in backup_paths)}
        shown = [f"{t}.* ({sum(p.split('.')[0] == t for p in skipped)} keys)" for t in sorted(gone)]
        shown += [p for p in skipped if p.split(".")[0] not in gone]
        print(f"skipped {len(skipped)} backup keys this firmware doesn't have: {', '.join(shown)}")

    changes = []
    for path, prop, new in props:
        old = prop.get_value()
        prop.set_value(new)
        back = prop.get_value()
        ok = back == new or (isinstance(new, float) and math.isfinite(new)
                             and abs(back - new) <= 1e-6 * max(1.0, abs(new)))
        changes.append({"path": path, "old": old, "requested": new, "readback": back, "ok": ok})
        print(f"  {path}: {old!r} -> {back!r}{'' if ok else '   !!! READBACK MISMATCH'}")

    saved = False
    if args.save:
        if all(c["ok"] for c in changes):
            reboots = (dev.fw_version_major, dev.fw_version_minor, dev.fw_version_revision) >= (0, 5, 2)
            try:
                dev.save_configuration()
            except Exception as ex:          # v0.5.2+: the board reboots and the USB link drops
                if not reboots:
                    raise
                print(f"(link dropped during save, as expected on v0.5.2+: {type(ex).__name__})")
            saved = True
            if reboots:
                print("save_configuration() done: the board saved and is REBOOTING (v0.5.2+).\n"
                      "!!! The startup sequence runs: if startup calibration is enabled, the motor moves.")
            else:
                print("save_configuration() done (stored in flash; no reboot).")
                print("!!! fw 0.5.1: the flash write disrupts PWM/ADC timing. REBOOT before driving the motor\n"
                      "    (python xdrive/tools/reboot_watch.py). Until then the motor gets no current and\n"
                      "    move/disturb tests refuse to start.")
        else:
            print("Not saving: a readback mismatched.")
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": datetime.datetime.now().astimezone().isoformat(), "action": "set_config",
                            "serial": serial, "pre_dump": snap[0].split()[-1], "file": args.file,
                            "changes": changes, "skipped": skipped, "saved": saved}) + "\n")
    return 0 if all(c["ok"] for c in changes) and (saved or not args.save) else 3


if __name__ == "__main__":
    sys.exit(main())
