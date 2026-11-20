#!/usr/bin/env python3
"""Disturbance-rejection ("virtual weight") test on axis0.  *** THE ROTOR MOVES SLIGHTLY ***

Holds position in closed loop and applies torque steps through input_torque
(+T, 0, -T, 0), like a load suddenly hanging off the joint. Measures how far the
rotor is pushed and how fast the position loop pulls it back. Expected
deflection is about a degree for T = 0.2 Nm. A speed guard aborts on anything
bigger.

- input_mode is switched to PASSTHROUGH in RAM for the test (trap-traj mode
  ignores input_torque) and is restored afterwards, as are any gain overrides.
  Nothing is saved.
- Any error, a state change, |vel| > --max-vel, or Ctrl-C → IDLE.

Usage:
  python xdrive/tools/disturb_test.py --torque 0.2 --label dist-base
  python xdrive/tools/disturb_test.py --torque 0.2 --vel-int-gain 2.5 --label dist-ki2.5
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
from odrive.enums import (AXIS_STATE_CLOSED_LOOP_CONTROL, AXIS_STATE_IDLE,
                          CONTROL_MODE_POSITION_CONTROL, INPUT_MODE_PASSTHROUGH)

from dump_board import decode_bitmask, connect
from move_test import FIELDS, IX, SETTINGS, Abort, Recorder
from sample import resolve

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
CPR = 16384


def step_metrics(rows, hold_pos, band):
    t = np.array([r[0] for r in rows])
    t = t - t[0]
    pos = np.array([r[1 + IX["axis0.encoder.pos_estimate"]] for r in rows])
    iq = np.array([r[1 + IX["axis0.motor.current_control.Iq_measured"]] for r in rows])
    e = (pos - hold_pos) * CPR
    k = int(np.argmax(np.abs(e)))
    if abs(e[k]) <= band:
        recover = 0.0                                   # never left the band (e.g. the quiet hold step)
    else:
        last = k + np.nonzero(np.abs(e[k:]) > band)[0][-1] + 1
        recover = t[last] if last < len(t) else float("nan")   # nan: still outside the band at the end
    tail = t > t[-1] - 0.3
    return {"peak_deflection_counts": round(float(e[k]), 1), "peak_deflection_deg": round(float(e[k]) * 360 / CPR, 3),
            "t_peak_s": round(float(t[k]), 3), "recovered_within_band_s": round(float(recover), 3),
            "final_error_counts": round(float(np.mean(e[tail])), 1), "peak_abs_Iq_meas_A": round(float(np.max(np.abs(iq))), 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--torque", type=float, default=0.2, help="step size in Nm (max 0.5)")
    ap.add_argument("--step-s", type=float, default=2.0, help="seconds per step")
    ap.add_argument("--band", type=float, default=10.0, help="recovery band in counts")
    ap.add_argument("--max-vel", type=float, default=2.0, help="abort if |vel_estimate| exceeds this (turn/s)")
    ap.add_argument("--label", default="disturb")
    for opt in SETTINGS:
        ap.add_argument("--" + opt.replace("_", "-"), type=float, dest=opt)
    args = ap.parse_args()
    if not 0 < abs(args.torque) <= 0.5:
        ap.error("--torque must be within (0, 0.5] Nm")

    dev = connect(timeout=10)
    if dev is None:
        print("No board found on USB.")
        return 1
    ax = dev.axis0
    serial = format(dev.serial_number, "X")
    problems = []
    if ax.current_state != AXIS_STATE_IDLE:
        problems.append(f"axis not IDLE (state {ax.current_state})")
    if not (ax.motor.is_calibrated and ax.encoder.is_ready):
        problems.append("motor/encoder not ready")
    if ax.controller.config.control_mode != CONTROL_MODE_POSITION_CONTROL:
        problems.append("control_mode is not POSITION")
    for name, prefix in [("axis0.error", "AXIS_ERROR_"), ("axis0.motor.error", "MOTOR_ERROR_"),
                         ("axis0.encoder.error", "ENCODER_ERROR_"), ("axis0.controller.error", "CONTROLLER_ERROR_")]:
        v = resolve(dev, name).get_value()
        if v:
            problems.append(f"{name} = {decode_bitmask(v, prefix)}")
    if (dev.fw_version_major, dev.fw_version_minor, dev.fw_version_revision) < (0, 5, 2) and dev.axis1.error & 0x8:
        problems.append("axis1 has CURRENT_MEASUREMENT_TIMEOUT: PWM/ADC timing disrupted "
                        "(fw 0.5.1 after save_configuration()); reboot first (reboot_watch.py)")
    if problems:
        print("Not starting:\n  " + "\n  ".join(problems))
        return 2

    # RAM-only changes, remembered for restore
    changed = {}
    for opt, path in SETTINGS.items():
        val = getattr(args, opt)
        if val is not None:
            prop = resolve(dev, path)
            changed[path] = prop.get_value()
            prop.set_value(val)
    im = resolve(dev, "axis0.controller.config.input_mode")
    changed["axis0.controller.config.input_mode"] = im.get_value()
    ax.controller.input_torque = 0.0
    ax.controller.input_vel = 0.0
    im.set_value(INPUT_MODE_PASSTHROUGH)
    applied = {p: resolve(dev, p).get_value() for p in changed}
    gains = {k: resolve(dev, f"axis0.controller.config.{k}").get_value()
             for k in ("pos_gain", "vel_gain", "vel_integrator_gain", "inertia")}
    start_stamp = datetime.datetime.now().astimezone()

    rec = Recorder(dev)
    rec.max_vel = args.max_vel
    steps, abort_reason, final_errors, hold_pos = [], None, {}, None
    plan = [("hold", 0.0, 1.0), (f"torque {args.torque:+g}", args.torque, args.step_s), ("torque 0", 0.0, args.step_s),
            (f"torque {-args.torque:+g}", -args.torque, args.step_s), ("torque 0 (end)", 0.0, args.step_s)]
    try:
        rec.event = "closed_loop_request"
        ax.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL  # firmware sets input_pos = pos_estimate on entry
        deadline = time.monotonic() + 1.0
        while rec.sample()[1 + IX["axis0.current_state"]] != AXIS_STATE_CLOSED_LOOP_CONTROL:
            if time.monotonic() > deadline:
                raise Abort("did not enter closed loop within 1 s")
        rec.expect_closed_loop = True
        hold_pos = ax.controller.input_pos
        for name, torque, dur in plan:
            rec.event = name
            i0 = len(rec.rows)
            ax.controller.input_torque = torque
            rec.run_for(dur)
            m = step_metrics(rec.rows[i0:], hold_pos, args.band)
            steps.append({"step": name, "torque_Nm": torque, **m})
            print(f"  {name:>15}: peak {m['peak_deflection_counts']:+7.1f} counts ({m['peak_deflection_deg']:+.2f}°) "
                  f"at {m['t_peak_s']:.3f}s, back within ±{args.band:g} by {m['recovered_within_band_s']:.3f}s, "
                  f"final {m['final_error_counts']:+.1f}, |Iq| pk {m['peak_abs_Iq_meas_A']:.2f} A")
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
            time.sleep(0.1)
            ax.controller.input_torque = 0.0
            for name, prefix in [("axis0.error", "AXIS_ERROR_"), ("axis0.motor.error", "MOTOR_ERROR_"),
                                 ("axis0.encoder.error", "ENCODER_ERROR_"), ("axis0.controller.error", "CONTROLLER_ERROR_")]:
                final_errors[name] = decode_bitmask(resolve(dev, name).get_value(), prefix)
            for path, old in changed.items():
                resolve(dev, path).set_value(old)
        except Exception as ex:
            print(f"Post-run read/restore failed: {ex!r}")

    LOGS.mkdir(exist_ok=True)
    stem = LOGS / f"{start_stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}"
    with open(f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# host_start", start_stamp.isoformat(), "serial", serial, "script", "disturb_test.py"])
        w.writerow(["t"] + FIELDS + ["event"])
        w.writerows(rec.rows)
    meta = {"host_start": start_stamp.isoformat(), "serial": serial, "argv": sys.argv[1:], "gains": gains,
            "torque_Nm": args.torque, "settings_applied_ram_only": applied, "previous_values_restored": changed,
            "hold_pos": hold_pos, "steps": steps, "abort_reason": abort_reason, "final_errors": final_errors,
            "samples": len(rec.rows)}
    pathlib.Path(f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n")
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": start_stamp.isoformat(), "action": "disturb_test", "argv": sys.argv[1:],
                            "abort_reason": abort_reason, "log": f"{stem.name}.csv"}) + "\n")
    print(f"\n{len(rec.rows)} samples -> {stem.relative_to(WORKDIR)}.csv/.json")
    print(f"gains: pos {gains['pos_gain']:g}, vel {gains['vel_gain']:g}, vel_int {gains['vel_integrator_gain']:g}, "
          f"inertia {gains['inertia']:g}")
    print(f"Result: {'ABORTED: ' + abort_reason if abort_reason else 'completed'}; axis left IDLE; "
          f"RAM settings restored: {list(changed)}")
    for name, d in final_errors.items():
        if d["flags"]:
            print(f"  {name} = {d['hex']}  {' | '.join(d['flags'])}")
    return 3 if abort_reason else 0


if __name__ == "__main__":
    sys.exit(main())
