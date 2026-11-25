#!/usr/bin/env python3
"""A/B listening test: hold position under several RAM-only settings in turn.  *** MOTOR HOLDS (tiny motion) ***

For each variant: IDLE -> apply settings (RAM only) -> closed loop (holds the
current position) -> log for --hold seconds -> next. Prints noise stats per
variant so what you hear can be matched to numbers. Uses the move_test guards
(errors, following error, current-not-following, speed). Always ends in IDLE
with every touched setting restored. Nothing is saved.

Usage:
  python tools/hold_ab.py --hold 15 --variant "A:current_bw=1000" \\
      --variant "B:current_bw=2000" --variant "C:current_bw=2000,enc_bw=500" --label hum-ab
Variant keys are move_test SETTINGS names (current_bw, enc_bw, vel_gain, vel_int_gain, pos_gain, ...).
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

import numpy as np

from logfiles import log_action, logs_dir, rel
from move_test import FIELDS, IX, SETTINGS, Abort, Recorder, error_problems
from xdrive import paths, usb
from xdrive.enums import AxisState
from xdrive.errors import LinkError
from xdrive.props import odrv



def parse_variant(text):
    label, _, body = text.partition(":")
    out = {}
    for kv in filter(None, body.split(",")):
        k, _, v = kv.partition("=")
        if k.strip() not in SETTINGS:
            raise SystemExit(f"unknown setting {k!r}; known: {', '.join(SETTINGS)}")
        out[k.strip()] = float(v)
    return label.strip(), out


def stats(rows):
    a = np.array([r[1:1 + len(FIELDS)] for r in rows], dtype=float)
    col = lambda f: a[:, IX[f]]
    P = "axis0.motor.current_control."
    return {"samples": len(rows),
            "Iq_sp_std": round(float(col(P + "Iq_setpoint").std()), 4),
            "Iq_meas_std": round(float(col(P + "Iq_measured").std()), 4),
            "Id_std": round(float(col(P + "Id_measured").std()), 4),
            "Iq_meas_mean": round(float(col(P + "Iq_measured").mean()), 3),
            "vel_std": round(float(col("axis0.encoder.vel_estimate").std()), 4),
            "pos_std_counts": round(float(col("axis0.encoder.pos_estimate").std() * 16384), 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", action="append", required=True, help='"LABEL:key=val,key=val"')
    ap.add_argument("--hold", type=float, default=15.0, help="seconds per variant")
    ap.add_argument("--label", default="hold-ab")
    args = ap.parse_args()
    variants = [parse_variant(v) for v in args.variant]

    try:
        b = usb.connect()
    except LinkError as ex:
        print(ex)
        return 1
    ax = odrv.axis0
    serial = format(b.get(odrv.serial_number), "X")
    problems = []
    if not (b.get(ax.motor.is_calibrated) and b.get(ax.encoder.is_ready)):
        problems.append("motor/encoder not ready")
    problems += error_problems(b)
    if problems:
        print("Not starting:\n  " + "\n  ".join(problems))
        return 2

    touched = {SETTINGS[k] for _, s in variants for k in s}
    original = {p: paths.get(b, p) for p in touched}
    start_stamp = datetime.datetime.now().astimezone()
    rec = Recorder(b)
    rec.max_vel = 1.0  # holding only: any real motion is a fault
    results, abort_reason, t0 = [], None, time.monotonic()
    try:
        for label, settings in variants:
            rec.expect_closed_loop = False
            b.set(ax.requested_state, AxisState.IDLE)
            rec.run_for(0.3)
            for p, v in original.items():          # start each variant from the original values
                paths.set(b, p, v)
            for k, v in settings.items():
                paths.set(b, SETTINGS[k], v)
            rec.event = f"enter {label}"
            rec.enter_closed_loop()
            rec.run_for(0.5)                            # let the integrator settle before measuring
            rec.event = f"variant {label}"
            i0 = len(rec.rows)
            t_start = time.monotonic() - t0
            rec.run_for(args.hold)
            s = {"variant": label, "settings": settings, "t_start_s": round(t_start, 1), **stats(rec.rows[i0:])}
            results.append(s)
            print(f"  {label:>3} (t={t_start:5.1f}s) {settings}: Iq_sp σ {s['Iq_sp_std']:.3f}  Iq_meas σ {s['Iq_meas_std']:.3f}  "
                  f"Id σ {s['Id_std']:.3f}  vel σ {s['vel_std']:.4f}  pos σ {s['pos_std_counts']:.2f} cnt  "
                  f"(hold current {s['Iq_meas_mean']:+.2f} A)", flush=True)
    except Abort as ex:
        abort_reason = str(ex)
    except KeyboardInterrupt:
        abort_reason = "Ctrl-C"
    finally:
        try:
            b.set(ax.requested_state, AxisState.IDLE)
        except Exception as ex:
            print(f"!!! Could not command IDLE ({ex!r}). Press OUT on the PSU.")
        try:
            for p, v in original.items():
                paths.set(b, p, v)
        except Exception as ex:
            print(f"Restore failed: {ex!r}")

    stem = logs_dir() / f"{start_stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}"
    rec.write_csv(f"{stem}.csv", start_stamp, serial, "hold_ab.py")
    pathlib.Path(f"{stem}.json").write_text(json.dumps(
        {"host_start": start_stamp.isoformat(), "serial": serial, "argv": sys.argv[1:], "original": original,
         "results": results, "abort_reason": abort_reason}, indent=2) + "\n")
    log_action({"t": start_stamp.isoformat(), "action": "hold_ab", "argv": sys.argv[1:],
                "abort_reason": abort_reason, "log": f"{stem.name}.csv"})
    print(f"\n-> {rel(stem)}.csv/.json")
    print(f"Result: {'ABORTED: ' + abort_reason if abort_reason else 'completed'}; axis left IDLE; "
          f"restored: {list(original)}")
    return 3 if abort_reason else 0


if __name__ == "__main__":
    sys.exit(main())
