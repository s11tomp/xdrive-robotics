#!/usr/bin/env python3
"""Read-only snapshot of an MKS XDRIVE Mini (ODrive fw v0.5.1) board.

Reads every readable property in the object tree (config + live state, both
axes), decodes error bitmasks and enum fields, and writes to logs/:

  <stamp>_<serial>[_<label>]_dump.json           every value + decoded errors
  <stamp>_<serial>[_<label>]_config-backup.json  config only, same format as
      `odrivetool backup-config`, restorable with `odrivetool restore-config`

It only ever calls RemoteProperty.get_value(): no property writes, no remote
function calls (no clear_errors, save_configuration, requested_state, ...).
It cannot move the motor or change the board.

Usage:  python xdrive/tools/dump_board.py [--label no-motor-boot] [--timeout 20]
"""
import argparse
import datetime
import json
import math
import pathlib
import re
import sys
import time

import fibre.remote_object as ro
import odrive
import odrive.enums as enums

from sample import ALIASES

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"

# Bitmask error fields: regex on the full path -> enum name prefix.
BITMASK_FIELDS = [
    (r"^axis\d\.error$", "AXIS_ERROR_"),
    (r"\.motor\.error$", "MOTOR_ERROR_"),
    (r"\.encoder\.error$", "ENCODER_ERROR_"),
    (r"\.controller\.error$", "CONTROLLER_ERROR_"),
    (r"\.sensorless_estimator\.error$", "SENSORLESS_ESTIMATOR_ERROR_"),
    (r"_thermistor\.error$", "THERMISTOR_CURRENT_LIMITER_ERROR_"),
    (r"^can\.error$", "CAN_ERROR_"),
    (r"\.gate_driver\.drv_fault$", "DRV_FAULT_"),
    (r"\.last_drv_fault$", "DRV_FAULT_"),          # v0.5.6
]

# Single-value enum fields.
ENUM_FIELDS = [
    (r"\.(current|requested)_state$", "AXIS_STATE_"),
    (r"\.controller\.config\.control_mode$", "CONTROL_MODE_"),
    (r"\.controller\.config\.input_mode$", "INPUT_MODE_"),
    (r"\.motor\.config\.motor_type$", "MOTOR_TYPE_"),
    (r"\.encoder\.config\.mode$", "ENCODER_MODE_"),
    (r"\.motor\.armed_state$", "ARMED_STATE_"),
    (r"\.lockin_state$", "LOCKIN_STATE_"),
]

# Extra fields worth eyeballing in the console summary.
SUMMARY = [
    "fw_version_major", "fw_version_minor", "fw_version_revision", "fw_version_unreleased",
    "hw_version_major", "hw_version_minor", "hw_version_variant",
    "user_config_loaded", "vbus_voltage", "ibus",
    "brake_resistor_armed", "brake_resistor_saturated",
    "axis0.current_state", "axis0.motor.is_calibrated", "axis0.encoder.is_ready",
    "axis0.motor.config.phase_resistance", "axis0.motor.config.phase_inductance",
    "axis0.motor.config.torque_constant", "axis0.motor.config.current_lim_margin",
    "axis0.motor.config.direction", "axis0.motor.effective_current_lim",
    "axis0.encoder.config.offset", "axis0.encoder.config.offset_float",
    "axis0.encoder.config.pre_calibrated", "axis0.encoder.config.calib_scan_distance",
    "axis0.encoder.calib_scan_response", "axis0.encoder.pos_abs", "axis0.encoder.pos_estimate",
    "axis0.controller.config.enable_overspeed_error", "axis0.controller.config.vel_limit_tolerance",
    "axis0.controller.config.anticogging.anticogging_enabled",
    "axis0.controller.config.anticogging.pre_calibrated",
    "axis0.config.can_node_id", "can.config.baud_rate",
    "axis0.fet_thermistor.temperature",
]


# Error/enum names: the v0.5.1 python package's table, or enums_v056.py (generated from the
# firmware's odrive-interface.yaml with ODrive's tools/enums_template.j2) for v0.5.2+ firmware, which
# reuses some error bits under new names. connect() picks the table from the board's version.
ENUMS = enums


def select_enums(dev):
    global ENUMS
    if (dev.fw_version_major, dev.fw_version_minor, dev.fw_version_revision) >= (0, 5, 2):
        import enums_v056
        ENUMS = enums_v056
    else:
        ENUMS = enums
    return ENUMS


def connect(**kwargs):
    """odrive.find_any(**kwargs), then select the matching enum table for decoding."""
    dev = odrive.find_any(**kwargs)
    if dev is not None:
        select_enums(dev)
    return dev


def enum_names(prefix):
    return {k: v for k, v in vars(ENUMS).items() if k.startswith(prefix) and isinstance(v, int)}


def decode_bitmask(value, prefix):
    v = value & 0xFFFFFFFF  # int32 fields can come back negative if bit 31 is set
    flags = [k for k, bit in enum_names(prefix).items() if bit and v & bit == bit]
    known = 0
    for k in flags:
        known |= enum_names(prefix)[k]
    out = {"hex": f"0x{v:08X}", "flags": flags}
    if v & ~known:
        out["unknown_bits"] = f"0x{v & ~known:08X}"
    return out


def decode_enum(value, prefix):
    names = [k for k, v in enum_names(prefix).items() if v == value]
    return names[0] if names else f"<unknown {value}>"


def jsonable(v):
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    if isinstance(v, tuple):
        return [jsonable(x) for x in v]
    return v


def walk(obj, prefix, values, access, functions, failures):
    for name, attr in obj._remote_attributes.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(attr, ro.RemoteObject):
            walk(attr, path, values, access, functions, failures)
        elif isinstance(attr, ro.RemoteFunction):
            functions.append(path)  # listed, never called
        elif isinstance(attr, ro.RemoteProperty) and attr._can_read:
            try:
                values[path] = jsonable(attr.get_value())
                access[path] = "rw" if attr._can_write else "r"
            except Exception as ex:  # keep going; record what failed
                failures[path] = repr(ex)


def config_only(values, access):
    """Nested dict of writable `.config.` values, in the shape odrivetool restore-config reads.

    Read-only config fields (e.g. can.config.baud_rate) and endpoint refs are
    left out: restore-config would try to write them back.
    """
    out = {}
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
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds to wait for the board on USB")
    ap.add_argument("--compare", help='settings file to diff the board against ({"settings": {path: value}}, '
                                      'the format set_config.py --file takes); nothing is written')
    args = ap.parse_args()

    print(f"Searching for an ODrive on USB (timeout {args.timeout:.0f} s)...")
    dev = connect(timeout=args.timeout)
    if dev is None:
        print("No board found. Is the PSU output on and the USB cable in?")
        return 1

    t_host = datetime.datetime.now().astimezone()
    t0 = time.monotonic()
    values, access, functions, failures = {}, {}, [], {}
    walk(dev, "", values, access, functions, failures)
    read_s = time.monotonic() - t0

    serial = format(values.get("serial_number", 0), "X")
    errors = {}
    enums_decoded = {}
    for path, v in values.items():
        if not isinstance(v, int):
            continue
        for pat, prefix in BITMASK_FIELDS:
            if re.search(pat, path):
                errors[path] = decode_bitmask(v, prefix)
        for pat, prefix in ENUM_FIELDS:
            if re.search(pat, path):
                enums_decoded[path] = decode_enum(v, prefix)

    def get(k):  # v0.5.1 name, else its v0.5.6 name (sample.ALIASES)
        return values[k] if k in values else values.get(ALIASES.get(k), "<missing>")

    def same(actual, exp):
        if isinstance(actual, (int, float)) and isinstance(exp, (int, float)):
            return math.isclose(actual, exp, rel_tol=1e-4, abs_tol=1e-6)
        return actual == exp

    expected = json.loads(pathlib.Path(args.compare).read_text())["settings"] if args.compare else {}
    diffs = {k: {"expected": exp, "actual": get(k)} for k, exp in expected.items() if not same(get(k), exp)}

    stamp = t_host.strftime("%Y%m%d-%H%M%S")
    stem = f"{stamp}_{serial}" + (f"_{args.label}" if args.label else "")
    LOGS.mkdir(exist_ok=True)
    dump_path = LOGS / f"{stem}_dump.json"
    backup_path = LOGS / f"{stem}_config-backup.json"

    dump = {
        "meta": {
            "host_time": t_host.isoformat(),
            "read_duration_s": round(read_s, 3),
            "serial": serial,
            "odrive_python": odrive.__version__,
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
        kk = k if k in values else ALIASES.get(k)
        if kk in values:
            extra = f"  ({enums_decoded[kk]})" if kk in enums_decoded else ""
            print(f"  {kk} = {values[kk]}{extra}")
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
    print(f"\nWrote {dump_path.relative_to(WORKDIR)}\n      {backup_path.relative_to(WORKDIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
