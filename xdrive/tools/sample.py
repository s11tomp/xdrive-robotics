#!/usr/bin/env python3
"""Read-only high-rate sampler for axis0 (ODrive fw v0.5.1 / MKS XDRIVE Mini).

Polls a fixed set of live values over USB as fast as it can for --duration
seconds, writes a CSV to logs/, and prints summary statistics. Only reads
properties: it never writes or calls functions, so it does not change what
the motor is doing.

Usage:  python xdrive/tools/sample.py --duration 10 --label hold
"""
import argparse
import csv
import datetime
import math
import pathlib
import statistics as st
import sys
import time

import odrive

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"

FIELDS = [
    "vbus_voltage",
    "ibus",
    "axis0.current_state",
    "axis0.error",
    "axis0.motor.error",
    "axis0.encoder.error",
    "axis0.controller.error",
    "axis0.motor.current_control.Iq_setpoint",
    "axis0.motor.current_control.Iq_measured",
    "axis0.motor.current_control.Id_measured",
    "axis0.encoder.pos_abs",
    "axis0.encoder.shadow_count",
    "axis0.encoder.pos_estimate",
    "axis0.encoder.vel_estimate",
    "axis0.controller.input_pos",
    "axis0.controller.pos_setpoint",
    "axis0.controller.vel_setpoint",
    "axis0.controller.vel_integrator_torque",
    "axis0.fet_thermistor.temperature",
]


# Properties renamed in ODrive v0.5.6, which this firmware is based on. The scripts
# keep the v0.5.1 names, so CSV columns and JSON keys stay comparable across firmware versions;
# resolve() and the dump fall back to the new name when the old one doesn't exist.
ALIASES = {
    "axis0.fet_thermistor.temperature": "axis0.motor.fet_thermistor.temperature",
    "axis0.motor.current_control.Ibus": "axis0.motor.I_bus",
    "axis0.motor.gate_driver.drv_fault": "axis0.last_drv_fault",
    "axis0.motor.config.direction": "axis0.encoder.config.direction",
    "axis0.encoder.config.offset": "axis0.encoder.config.phase_offset",
    "axis0.encoder.config.offset_float": "axis0.encoder.config.phase_offset_float",
    "axis0.config.can_node_id": "axis0.config.can.node_id",
    "axis1.config.can_node_id": "axis1.config.can.node_id",
    "axis0.controller.config.enable_current_mode_vel_limit": "axis0.controller.config.enable_torque_mode_vel_limit",
}


def _resolve(dev, path):
    obj = dev
    *parents, leaf = path.split(".")
    for p in parents:
        obj = obj._remote_attributes[p]
    return obj._remote_attributes[leaf]


def resolve(dev, path):
    """Return the RemoteProperty object for a dotted path (so reads skip attribute lookup).

    Falls back to the v0.5.6 name (ALIASES) when a v0.5.1 path doesn't exist on the board."""
    try:
        return _resolve(dev, path)
    except KeyError:
        if path in ALIASES:
            return _resolve(dev, ALIASES[path])
        raise


def stats(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]
    if not xs:
        return {}
    return {"mean": st.fmean(xs), "std": st.pstdev(xs), "min": min(xs), "max": max(xs)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--label", default="sample")
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args()

    from dump_board import connect  # here, not at the top: dump_board imports this module
    dev = connect(timeout=args.timeout)
    if dev is None:
        print("No board found on USB.")
        return 1
    props = [resolve(dev, f) for f in FIELDS]
    serial = format(dev.serial_number, "X")

    stamp = datetime.datetime.now().astimezone()
    LOGS.mkdir(exist_ok=True)
    path = LOGS / f"{stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}.csv"

    rows = []
    t0 = time.monotonic()
    while (t := time.monotonic() - t0) < args.duration:
        rows.append([t] + [p.get_value() for p in props])

    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# host_start", stamp.isoformat(), "serial", serial, "script", "sample.py (read-only)"])
        w.writerow(["t"] + FIELDS)
        w.writerows(rows)

    n = len(rows)
    col = {name: [r[i + 1] for r in rows] for i, name in enumerate(FIELDS)}
    print(f"{n} samples in {args.duration:.1f} s ({n / args.duration:.0f} Hz) -> {path.relative_to(WORKDIR)}")
    for name in ["vbus_voltage", "ibus", "axis0.motor.current_control.Iq_setpoint",
                 "axis0.motor.current_control.Iq_measured", "axis0.motor.current_control.Id_measured",
                 "axis0.encoder.vel_estimate", "axis0.controller.vel_integrator_torque",
                 "axis0.fet_thermistor.temperature"]:
        s = stats(col[name])
        print(f"  {name:45s} mean {s['mean']:+9.4f}  std {s['std']:8.4f}  min {s['min']:+9.4f}  max {s['max']:+9.4f}")
    pos_counts = [p * 16384 for p in col["axis0.encoder.pos_estimate"]]
    s = stats(pos_counts)
    print(f"  {'pos_estimate (counts)':45s} mean {s['mean']:+9.1f}  std {s['std']:8.2f}  span {s['max'] - s['min']:.1f}")
    raw = col["axis0.encoder.pos_abs"]
    jumps = [abs(((b - a + 8192) % 16384) - 8192) for a, b in zip(raw, raw[1:])]
    print(f"  {'pos_abs sample-to-sample |delta| (counts)':45s} max {max(jumps)}  "
          f"mean {st.fmean(jumps):.2f}  >50: {sum(j > 50 for j in jumps)}")
    errs = {f: sorted({v for v in col[f] if v}) for f in FIELDS if f.endswith("error")}
    states = sorted(set(col["axis0.current_state"]))
    print(f"  states seen {states}; nonzero errors: {({k: [hex(x) for x in v] for k, v in errs.items() if v}) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
