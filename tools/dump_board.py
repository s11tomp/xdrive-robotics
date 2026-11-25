#!/usr/bin/env python3
"""Read-only snapshot of an MKS XDRIVE Mini board running this firmware.

Reads every property in the board's interface (config + live state), decodes error flags and enum
fields, and writes to logs/:

  <stamp>_<serial>[_<label>]_dump.json           every value + decoded errors
  <stamp>_<serial>[_<label>]_config-backup.json  writable config only, nested by path, restorable
      with set_config.py --file (the format of odrivetool backup-config)

It only reads properties: no writes, no function calls (no clear_errors, save_configuration,
requested_state, ...). It cannot move the motor or change the board.

Usage:  python tools/dump_board.py [--label no-motor-boot] [--compare configs/<board>.json]
"""
import argparse
import datetime
import enum
import json
import math
import pathlib
import sys
import time
from typing import Any

from logfiles import logs_dir, rel
from xdrive import paths, report, usb
from xdrive.errors import InterfaceMismatch, LinkError, XdriveError
from xdrive.model import Prop, RwProp


# Fields worth eyeballing in the console summary.
SUMMARY = [
    "fw_version_major", "fw_version_minor", "fw_version_revision", "fw_version_unreleased",
    "hw_version_major", "hw_version_minor", "hw_version_variant",
    "user_config_loaded", "vbus_voltage", "ibus",
    "brake_resistor_armed", "brake_resistor_saturated",
    "axis0.current_state", "axis0.motor.is_calibrated", "axis0.encoder.is_ready",
    "axis0.motor.config.phase_resistance", "axis0.motor.config.phase_inductance",
    "axis0.motor.config.torque_constant", "axis0.motor.config.current_lim_margin",
    "axis0.encoder.config.direction", "axis0.motor.effective_current_lim",
    "axis0.encoder.config.phase_offset", "axis0.encoder.config.phase_offset_float",
    "axis0.encoder.config.pre_calibrated", "axis0.encoder.config.calib_scan_distance",
    "axis0.encoder.calib_scan_response", "axis0.encoder.pos_abs", "axis0.encoder.pos_estimate",
    "axis0.controller.config.enable_overspeed_error", "axis0.controller.config.vel_limit_tolerance",
    "axis0.controller.config.anticogging.anticogging_enabled",
    "axis0.controller.config.anticogging.pre_calibrated",
    "axis0.config.can.node_id", "can.config.baud_rate",
    "axis0.motor.fet_thermistor.temperature",
]


def jsonable(v):
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    if isinstance(v, tuple):
        return [jsonable(x) for x in v]
    return v


def read_all(board):
    """(values, access, functions, failures, errors, enums) for every property in the board's interface."""
    values, access, failures, errors, enums = {}, {}, {}, {}, {}
    for path, ep in board.interface.properties.items():
        try:
            v = board.get(paths.prop(path))
        except InterfaceMismatch:  # an enum value the enum lacks (a setting saved by another build): keep the int
            raw = board.get((RwProp if ep.writable else Prop)(path, int))
            values[path], access[path] = raw, "rw" if ep.writable else "r"
            enums[path] = f"<unknown {raw}>"
            continue
        except XdriveError as ex:  # keep going; record what failed
            failures[path] = repr(ex)
            continue
        values[path] = jsonable(paths.plain(v))
        access[path] = "rw" if ep.writable else "r"
        if isinstance(v, enum.IntFlag) and path.endswith("error"):
            errors[path] = report.jsonable(v)
        elif isinstance(v, enum.IntFlag):
            enums[path] = " | ".join(report.flag_names(v))
        elif isinstance(v, enum.Enum):
            enums[path] = v.name
    return values, access, sorted(board.interface.functions), failures, errors, enums


def config_only(values, access):
    """Nested dict of writable `.config.` values, in the shape set_config.py --file reads.

    Read-only config fields (e.g. can.config.baud_rate) and endpoint refs are
    left out: a restore would try to write them back.
    """
    out: dict[str, Any] = {}
    for path, v in values.items():
        parts = path.split(".")
        if "config" not in parts[:-1] or access.get(path) != "rw" or isinstance(v, list):
            continue
        node = out
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = v
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="", help="suffix for the output filenames, e.g. no-motor-boot")
    ap.add_argument("--compare", help='settings file to diff the board against ({"settings": {path: value}}, '
                                      'the format set_config.py --file takes); nothing is written')
    args = ap.parse_args()

    try:
        board = usb.connect()
    except LinkError as ex:
        print(f"{ex}. Is the PSU output on and the USB cable in?")
        return 1

    t_host = datetime.datetime.now().astimezone()
    t0 = time.monotonic()
    with board:
        values, access, functions, failures, errors, enums_decoded = read_all(board)
        version_id = board.interface.version_id
    read_s = time.monotonic() - t0

    serial = format(values.get("serial_number", 0), "X")

    def get(k):
        return values.get(k, "<missing>")

    def same(actual, exp):
        if isinstance(actual, (int, float)) and isinstance(exp, (int, float)):
            return math.isclose(actual, exp, rel_tol=1e-4, abs_tol=1e-6)
        return actual == exp

    expected = json.loads(pathlib.Path(args.compare).read_text())["settings"] if args.compare else {}
    diffs = {k: {"expected": exp, "actual": get(k)} for k, exp in expected.items() if not same(get(k), exp)}

    stamp = t_host.strftime("%Y%m%d-%H%M%S")
    stem = f"{stamp}_{serial}" + (f"_{args.label}" if args.label else "")
    dump_path = logs_dir() / f"{stem}_dump.json"
    backup_path = logs_dir() / f"{stem}_config-backup.json"

    dump = {
        "meta": {
            "host_time": t_host.isoformat(),
            "read_duration_s": round(read_s, 3),
            "serial": serial,
            "interface_version_id": f"{version_id:08x}",
            "script": "dump_board.py (read-only)",
            "label": args.label,
            "n_values": len(values),
        },
        "errors_decoded": errors,
        "enums_decoded": enums_decoded,
        "compared_with": args.compare,
        "diff_vs_expected": diffs,
        "values": values,
        "access": access,
        "functions_not_called": functions,
        "read_failures": failures,
    }
    dump_path.write_text(json.dumps(dump, indent=2) + "\n")
    backup_path.write_text(json.dumps(config_only(values, access), indent=2) + "\n")

    # Console summary
    print(f"\nBoard {serial}: read {len(values)} values in {read_s:.2f} s")
    for k in SUMMARY:
        if k in values:
            extra = f"  ({enums_decoded[k]})" if k in enums_decoded else ""
            print(f"  {k} = {values[k]}{extra}")
    print("\nErrors (only from this boot; errors are RAM-only and cleared by a power cycle):")
    for path, d in errors.items():
        if d["flags"] or d.get("unknown_bits"):
            print(f"  {path} = {d['hex']}  {' | '.join(d['flags'])} {d.get('unknown_bits', '')}")
    if not any(d["flags"] or d.get("unknown_bits") for d in errors.values()):
        print("  none")
    if args.compare:
        print(f"\nDifferences vs. {args.compare} ({len(diffs)} of {len(expected)} settings):")
        for k, d in diffs.items():
            print(f"  {k}: expected {d['expected']}, actual {d['actual']}")
    if failures:
        print(f"\n{len(failures)} properties failed to read (see read_failures in the dump)")
    print(f"\nWrote {rel(dump_path)}\n      {rel(backup_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
