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
  python tools/disturb_test.py --torque 0.2 --label dist-base
  python tools/disturb_test.py --torque 0.2 --vel-int-gain 2.5 --label dist-ki2.5
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

import numpy as np

from logfiles import log_action, logs_dir, rel
from move_test import IX, SETTINGS, Abort, Recorder, error_problems
from xdrive import paths, report, usb
from xdrive.enums import AxisState, ControlMode, InputMode
from xdrive.errors import LinkError
from xdrive.props import odrv

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

    try:
        b = usb.connect()
    except LinkError as ex:
        print(ex)
        return 1
    ax = odrv.axis0
    serial = format(b.get(odrv.serial_number), "X")
    problems = []
    if (state := b.get(ax.current_state)) is not AxisState.IDLE:
        problems.append(f"axis not IDLE (state {state.name})")
    if not (b.get(ax.motor.is_calibrated) and b.get(ax.encoder.is_ready)):
        problems.append("motor/encoder not ready")
    if b.get(ax.controller.config.control_mode) is not ControlMode.POSITION_CONTROL:
        problems.append("control_mode is not POSITION")
    problems += error_problems(b)
    if problems:
        print("Not starting:\n  " + "\n  ".join(problems))
        return 2

    # RAM-only changes, remembered for restore
    changed = {}
    for opt, path in SETTINGS.items():
        val = getattr(args, opt)
        if val is not None:
            changed[path] = paths.get(b, path)
            paths.set(b, path, val)
    changed["axis0.controller.config.input_mode"] = paths.get(b, "axis0.controller.config.input_mode")
    b.set(ax.controller.input_torque, 0.0)
    b.set(ax.controller.input_vel, 0.0)
    b.set(ax.controller.config.input_mode, InputMode.PASSTHROUGH)
    applied = {p: paths.get(b, p) for p in changed}
    gains = {k: paths.get(b, f"axis0.controller.config.{k}")
             for k in ("pos_gain", "vel_gain", "vel_integrator_gain", "inertia")}
    start_stamp = datetime.datetime.now().astimezone()

    rec = Recorder(b)
    rec.max_vel = args.max_vel
    steps, abort_reason, final_errors, hold_pos = [], None, {}, None
    plan = [("hold", 0.0, 1.0), (f"torque {args.torque:+g}", args.torque, args.step_s), ("torque 0", 0.0, args.step_s),
            (f"torque {-args.torque:+g}", -args.torque, args.step_s), ("torque 0 (end)", 0.0, args.step_s)]
    try:
        rec.event = "closed_loop_request"
        rec.enter_closed_loop()  # firmware sets input_pos = pos_estimate on entry
        hold_pos = b.get(ax.controller.input_pos)
        for name, torque, dur in plan:
            rec.event = name
            i0 = len(rec.rows)
            b.set(ax.controller.input_torque, torque)
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
            b.set(ax.requested_state, AxisState.IDLE)
        except Exception as ex:
            print(f"!!! Could not command IDLE ({ex!r}). Press OUT on the PSU.")
        try:
            time.sleep(0.1)
            b.set(ax.controller.input_torque, 0.0)
            final_errors = {name: report.jsonable(err) for name, err in report.errors(b).items()}
            for path, old in changed.items():
                paths.set(b, path, old)
        except Exception as ex:
            print(f"Post-run read/restore failed: {ex!r}")

    stem = logs_dir() / f"{start_stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}"
    rec.write_csv(f"{stem}.csv", start_stamp, serial, "disturb_test.py")
    meta = {"host_start": start_stamp.isoformat(), "serial": serial, "argv": sys.argv[1:], "gains": gains,
            "torque_Nm": args.torque, "settings_applied_ram_only": applied, "previous_values_restored": changed,
            "hold_pos": hold_pos, "steps": steps, "abort_reason": abort_reason, "final_errors": final_errors,
            "samples": len(rec.rows)}
    pathlib.Path(f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n")
    log_action({"t": start_stamp.isoformat(), "action": "disturb_test", "argv": sys.argv[1:],
                "abort_reason": abort_reason, "log": f"{stem.name}.csv"})
    print(f"\n{len(rec.rows)} samples -> {rel(stem)}.csv/.json")
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
