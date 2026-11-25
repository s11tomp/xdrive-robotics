#!/usr/bin/env python3
"""Change board settings safely: dump first, write, read back, optionally save.

  python tools/set_config.py [--save] path=value [path=value ...]
  python tools/set_config.py [--save] --file configs/<board>.json [path=value ...]
  python tools/set_config.py --save
  e.g. python tools/set_config.py --save axis0.encoder.config.calib_range=0.05

- Refuses unless axis0 is IDLE (nothing is driving the motor).
- Runs dump_board.py first, so the pre-change config is in logs/.
- Values are typed from the property (bool: true/false/1/0, int, float, enum: its number or name).
- Reads every value back and reports old -> new.
- --file: a JSON file {"settings": {path: value}} (e.g. examples/dji-10018.json),
  or a dump_board.py *_config-backup.json (nested, odrivetool restore-config format). The backup
  restores a board's own calibration results (R/L, encoder offset, pre_calibrated) after a flash
  that reset its config, without moving the motor. Backup keys the board's firmware doesn't have
  (e.g. from an older firmware) are skipped and listed. Assignments on the command line are applied after it.
- --save calls save_configuration(). Alone (no assignments, no --file) it saves the board's current RAM config,
  which is how to keep what the RAM-only tools wrote (e.g. correction_table.py). The board saves and
  reboots, and THE STARTUP SEQUENCE RUNS (if startup calibration is enabled, the motor moves); the
  tool returns once the board is back up.
- Never erases. Appends the change set to logs/actions.jsonl.
"""
import argparse
import datetime
import enum
import json
import math
import pathlib
import subprocess
import sys

from logfiles import log_action
from xdrive import paths, usb
from xdrive.enums import AxisState
from xdrive.errors import LinkError, Refused
from xdrive.model import RwProp
from xdrive.props import odrv



def parse(prop, text):
    """A JSON value or command-line text as the property's type."""
    kind = prop.kind
    if not isinstance(text, str):          # a JSON value
        return paths.typed(prop, bool(text) if kind is bool else text)
    if kind is bool:
        if text.lower() in ("true", "1"):
            return True
        if text.lower() in ("false", "0"):
            return False
        raise ValueError(f"not a bool: {text}")
    if issubclass(kind, enum.Enum):
        return kind[text] if text in kind.__members__ else kind(int(text))
    return int(float(text)) if kind is int else kind(text)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", action="store_true", help="save_configuration() after writing (alone: saves the current RAM config)")
    ap.add_argument("--file", help='JSON file {"settings": {path: value}} or a *_config-backup.json, applied before the assignments')
    ap.add_argument("assignments", nargs="*", metavar="path=value")
    args = ap.parse_args(argv)
    if not (args.file or args.assignments or args.save):
        ap.error("nothing to do: give path=value, --file, or --save")
    for a in args.assignments:
        if not a.partition("=")[2]:
            ap.error(f"expected path=value, got {a!r}")
    return args


def main():
    args = parse_args()
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
        pairs.append((path.strip(), val.strip()))

    # Pre-change snapshot (separate process; read-only)
    r = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent / "dump_board.py"), "--label", "pre-set-config"],
                       capture_output=True, text=True)
    snap = [l for l in r.stdout.splitlines() if "_dump.json" in l]
    if r.returncode != 0 or not snap:
        print("Pre-change dump failed; not changing anything.\n" + r.stdout + r.stderr)
        return 1
    print("pre-change dump: " + snap[0].split()[-1])

    try:
        b = usb.connect()
    except LinkError as ex:
        print(ex)
        return 1
    serial = format(b.get(odrv.serial_number), "X")
    if (state := b.get(odrv.axis0.current_state)) is not AxisState.IDLE:
        print(f"axis0 is not IDLE (state {state.name}); not changing anything.")
        return 2

    props = []
    skipped = []
    for path, text in pairs:  # validate everything before writing anything
        if path not in paths.HANDLES or path not in b.interface.properties:
            if path not in backup_paths:
                print(f"{path}: no such property on this firmware")
                return 2
            skipped.append(path)
            continue
        prop = paths.prop(path)
        if not isinstance(prop, RwProp):
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
    for path, prop, value in props:
        old = paths.get(b, path)
        back = paths.plain(b.set(prop, value))
        new = paths.plain(value)
        ok = back == new or (isinstance(new, float) and math.isfinite(new)
                             and abs(back - new) <= 1e-6 * max(1.0, abs(new)))
        changes.append({"path": path, "old": old, "requested": new, "readback": back, "ok": ok})
        print(f"  {path}: {old!r} -> {back!r}{'' if ok else '   !!! READBACK MISMATCH'}")

    saved = False
    if args.save:
        if not changes:
            print("no settings given: saving the board's current RAM config")
        if all(c["ok"] for c in changes):
            print("save_configuration(): the board saves and REBOOTS; its startup sequence runs "
                  "(with startup calibration enabled, the motor moves).")
            try:
                b.save()
            except Refused as ex:
                print(f"!!! NOT SAVED: {ex}")
            else:
                saved = True
                print("saved; the board is back up.")
        else:
            print("Not saving: a readback mismatched.")
    b.close()
    log_action({"t": datetime.datetime.now().astimezone().isoformat(), "action": "set_config",
                "serial": serial, "pre_dump": snap[0].split()[-1], "file": args.file,
                "changes": changes, "skipped": skipped, "saved": saved})
    return 0 if all(c["ok"] for c in changes) and (saved or not args.save) else 3


if __name__ == "__main__":
    sys.exit(main())
