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
import csv
import datetime
import json
import pathlib
import sys
import time

import numpy as np
import odrive
from odrive.enums import AXIS_STATE_CLOSED_LOOP_CONTROL, AXIS_STATE_IDLE

from dump_board import decode_bitmask, connect
from move_test import FIELDS, IX, SETTINGS, Abort, Recorder
from sample import resolve

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"


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

    dev = connect(timeout=10)
    if dev is None:
        print("No board found on USB.")
        return 1
    ax = dev.axis0
    serial = format(dev.serial_number, "X")
    problems = []
    if not (ax.motor.is_calibrated and ax.encoder.is_ready):
        problems.append("motor/encoder not ready")
    if (dev.fw_version_major, dev.fw_version_minor, dev.fw_version_revision) < (0, 5, 2) and dev.axis1.error & 0x8:
        problems.append("axis1 CURRENT_MEASUREMENT_TIMEOUT: reboot first (fw 0.5.1 after save_configuration())")
    for name, prefix in [("axis0.error", "AXIS_ERROR_"), ("axis0.motor.error", "MOTOR_ERROR_"),
                         ("axis0.encoder.error", "ENCODER_ERROR_"), ("axis0.controller.error", "CONTROLLER_ERROR_")]:
        v = resolve(dev, name).get_value()
        if v:
            problems.append(f"{name} = {decode_bitmask(v, prefix)}")
    if problems:
        print("Not starting:\n  " + "\n  ".join(problems))
        return 2

    touched = {SETTINGS[k] for _, s in variants for k in s}
    original = {p: resolve(dev, p).get_value() for p in touched}
    start_stamp = datetime.datetime.now().astimezone()
    rec = Recorder(dev)
    rec.max_vel = 1.0  # holding only: any real motion is a fault
    results, abort_reason, t0 = [], None, time.monotonic()
    try:
        for label, settings in variants:
            rec.expect_closed_loop = False
            ax.requested_state = AXIS_STATE_IDLE
            rec.run_for(0.3)
            for p, v in original.items():          # start each variant from the original values
                resolve(dev, p).set_value(v)
            for k, v in settings.items():
                resolve(dev, SETTINGS[k]).set_value(v)
            rec.event = f"enter {label}"
            ax.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
            deadline = time.monotonic() + 1.0
            while rec.sample()[1 + IX["axis0.current_state"]] != AXIS_STATE_CLOSED_LOOP_CONTROL:
                if time.monotonic() > deadline:
                    raise Abort("did not enter closed loop within 1 s")
            rec.expect_closed_loop = True
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
            ax.requested_state = AXIS_STATE_IDLE
        except Exception as ex:
            print(f"!!! Could not command IDLE ({ex!r}). Press OUT on the PSU.")
        try:
            for p, v in original.items():
                resolve(dev, p).set_value(v)
        except Exception as ex:
            print(f"Restore failed: {ex!r}")

    LOGS.mkdir(exist_ok=True)
    stem = LOGS / f"{start_stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}"
    with open(f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# host_start", start_stamp.isoformat(), "serial", serial, "script", "hold_ab.py"])
        w.writerow(["t"] + FIELDS + ["event"])
        w.writerows(rec.rows)
    pathlib.Path(f"{stem}.json").write_text(json.dumps(
        {"host_start": start_stamp.isoformat(), "serial": serial, "argv": sys.argv[1:], "original": original,
         "results": results, "abort_reason": abort_reason}, indent=2) + "\n")
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": start_stamp.isoformat(), "action": "hold_ab", "argv": sys.argv[1:],
                            "abort_reason": abort_reason, "log": f"{stem.name}.csv"}) + "\n")
    print(f"\n-> {stem.relative_to(WORKDIR)}.csv/.json")
    print(f"Result: {'ABORTED: ' + abort_reason if abort_reason else 'completed'}; axis left IDLE; "
          f"restored: {list(original)}")
    return 3 if abort_reason else 0


if __name__ == "__main__":
    sys.exit(main())
