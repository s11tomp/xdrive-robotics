#!/usr/bin/env python3
"""Continuous run-in at constant speed, reversing at a fixed interval.  *** THE MOTOR RUNS CONTINUOUSLY. ***

Runs axis0 in velocity control (VEL_RAMP, RAM only) at --speed turn/s for --minutes, reversing every
--reverse-every seconds, so both directions of a gearbox's teeth see the same running time. Samples as fast
as USB allows for the guards and writes one summary row per second: mean speed, mean and peak |Iq| over
the cruise samples (|vel_setpoint| at speed), bus current and voltage, FET temperature.

Stops early, to IDLE, on:
  - any error flag, leaving closed loop, a runaway speed or current not following (the move_test guards);
  - a stall: |vel_estimate - vel_setpoint| above --stall-frac x speed for 0.5 s at cruise;
  - rising drag: a second of cruise whose mean |Iq| exceeds --max-drag;
  - FET temperature above --max-fet;
  - the file logs/STOP appearing (touch it from another shell: the run decelerates, then goes IDLE).
Ctrl-C also stops it. Another process cannot reach the board over USB while this one runs, so the STOP
file and the PSU's output switch are the ways to stop it from outside.

Always ends in IDLE with every touched setting restored (after the rotor has slowed below 1 turn/s, so a
lower restored vel_limit cannot latch an overspeed error). Nothing is saved.

Usage:
  python tools/runin.py --speed 10 --minutes 10 --reverse-every 60 --accel 5 --current-lim 5 --label runin
"""
import argparse
import csv
import datetime
import json
import math
import pathlib
import sys
import time

import numpy as np

from move_test import CLOSED_LOOP, FIELDS, IX, Abort, Recorder, error_problems
from xdrive import paths, usb
from xdrive.enums import AxisState, ControlMode, InputMode
from xdrive.errors import LinkError
from xdrive.props import odrv

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
STOP = LOGS / "STOP"
COLUMNS = ["t", "direction", "cruise_samples", "vel_mean", "Iq_mean_abs", "Iq_peak_abs", "ibus_mean", "vbus_mean",
           "fet_temp"]


class Stop(Exception):
    """A requested stop (STOP file, end of run): decelerate before IDLE."""


def second_summary(rows, t, direction, speed):
    a = np.array([r[1:1 + len(FIELDS)] for r in rows], dtype=float)
    col = lambda f: a[:, IX[f]]
    cruise = np.abs(col("axis0.controller.vel_setpoint")) >= 0.98 * speed
    iq = np.abs(col("axis0.motor.current_control.Iq_measured"))
    return {"t": round(t, 1), "direction": direction, "cruise_samples": int(cruise.sum()),
            "vel_mean": round(float(col("axis0.encoder.vel_estimate").mean()), 3),
            "Iq_mean_abs": round(float(iq[cruise].mean()), 3) if cruise.any() else None,
            "Iq_peak_abs": round(float(iq.max()), 3),
            "ibus_mean": round(float(col("ibus").mean()), 4),
            "vbus_mean": round(float(col("vbus_voltage").mean()), 2),
            "fet_temp": round(float(col("axis0.motor.fet_thermistor.temperature").max()), 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--speed", type=float, required=True, help="turn/s")
    ap.add_argument("--minutes", type=float, required=True)
    ap.add_argument("--reverse-every", type=float, default=60.0, help="seconds per direction")
    ap.add_argument("--accel", type=float, default=5.0, help="turn/s² (vel_ramp_rate)")
    ap.add_argument("--current-lim", type=float, help="A (RAM only; default: the board's)")
    ap.add_argument("--max-drag", type=float, default=2.5, help="stop when a second of cruise averages above this |Iq|")
    ap.add_argument("--max-fet", type=float, default=80.0, help="stop above this FET temperature, °C")
    ap.add_argument("--stall-frac", type=float, default=0.3)
    ap.add_argument("--label", default="runin")
    args = ap.parse_args()
    if not 0 < args.speed <= 20 or args.minutes <= 0 or args.reverse_every < 2 * args.speed / args.accel:
        raise SystemExit("need 0 < --speed <= 20, --minutes > 0, and --reverse-every longer than two speed ramps")

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
    if STOP.exists():
        STOP.unlink()
        print(f"removed a leftover {STOP.relative_to(WORKDIR)}")

    cfg = ax.controller.config
    orig_control_mode, orig_input_mode = b.get(cfg.control_mode), b.get(cfg.input_mode)
    orig_ramp, orig_vel_limit = b.get(cfg.vel_ramp_rate), b.get(cfg.vel_limit)
    orig_current_lim = b.get(ax.motor.config.current_lim)
    original = {"control_mode": orig_control_mode.name, "input_mode": orig_input_mode.name,
                "vel_ramp_rate": orig_ramp, "vel_limit": orig_vel_limit, "current_lim": orig_current_lim}
    b.set(ax.controller.input_vel, 0.0)
    b.set(cfg.control_mode, ControlMode.VELOCITY_CONTROL)
    b.set(cfg.input_mode, InputMode.VEL_RAMP)
    b.set(cfg.vel_ramp_rate, args.accel)
    b.set(cfg.vel_limit, args.speed + 3.0)
    if args.current_lim is not None:
        b.set(ax.motor.config.current_lim, args.current_lim)

    start_stamp = datetime.datetime.now().astimezone()
    rec = Recorder(b)
    rec.max_vel = 1.3 * args.speed + 2.0
    rec.max_follow = math.inf  # velocity control: pos_setpoint does not follow the rotor
    seconds, abort_reason, direction = [], None, +1
    run_s = args.minutes * 60.0
    print(f"{args.speed:g} turn/s for {args.minutes:g} min, reversing every {args.reverse_every:g} s; "
          f"stop: touch {STOP.relative_to(WORKDIR)}")
    try:
        try:
            b.set(ax.requested_state, AxisState.CLOSED_LOOP_CONTROL)
            deadline = time.monotonic() + 1.0
            while rec.sample()[1 + IX["axis0.current_state"]] != CLOSED_LOOP:
                if time.monotonic() > deadline:
                    raise Abort("did not enter closed loop within 1 s")
            rec.expect_closed_loop = True
            t_start = time.monotonic()
            b.set(ax.controller.input_vel, direction * args.speed)
            t_reverse, t_second, stall_since = t_start + args.reverse_every, t_start + 1.0, None
            rec.rows = []
            while True:
                row = rec.sample()
                now = time.monotonic()
                vsp = row[1 + IX["axis0.controller.vel_setpoint"]]
                vel = row[1 + IX["axis0.encoder.vel_estimate"]]
                if abs(vsp) >= 0.98 * args.speed and abs(vel - vsp) > args.stall_frac * args.speed:
                    stall_since = stall_since or now
                    if now - stall_since > 0.5:
                        raise Abort(f"stall: vel_estimate {vel:.2f} against setpoint {vsp:.2f} turn/s for 0.5 s")
                else:
                    stall_since = None
                if now >= t_second:
                    s = second_summary(rec.rows, now - t_start, direction, args.speed)
                    seconds.append(s)
                    rec.rows = []
                    t_second += 1.0
                    if s["Iq_mean_abs"] is not None and s["Iq_mean_abs"] > args.max_drag:
                        raise Abort(f"drag: cruise |Iq| {s['Iq_mean_abs']:.2f} A > {args.max_drag} A")
                    if s["fet_temp"] > args.max_fet:
                        raise Abort(f"FET {s['fet_temp']:.1f} °C > {args.max_fet} °C")
                    if len(seconds) % 30 == 0:
                        recent = [x["Iq_mean_abs"] for x in seconds[-30:] if x["Iq_mean_abs"] is not None]
                        print(f"  t {s['t']:6.0f} s  dir {direction:+d}  cruise |Iq| "
                              f"{np.mean(recent) if recent else float('nan'):.3f} A (last 30 s)  "
                              f"ibus {s['ibus_mean']:.3f} A  FET {s['fet_temp']:.1f} °C", flush=True)
                    if STOP.exists():
                        raise Stop("stop file")
                    if now - t_start >= run_s:
                        raise Stop("completed")
                if now >= t_reverse:
                    direction = -direction
                    b.set(ax.controller.input_vel, direction * args.speed)
                    t_reverse += args.reverse_every
        except Stop as ex:
            if str(ex) != "completed":
                abort_reason = str(ex)
            b.set(ax.controller.input_vel, 0.0)
            t_slow = time.monotonic()
            while abs(rec.sample()[1 + IX["axis0.encoder.vel_estimate"]]) > 0.2:
                if time.monotonic() - t_slow > args.speed / args.accel + 5.0:
                    raise Abort("did not slow down after the stop")
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
            t_coast = time.monotonic()
            while time.monotonic() - t_coast < 30.0:
                coast_vel: float = b.get(ax.encoder.vel_estimate)
                if abs(coast_vel) <= 1.0:
                    break
                time.sleep(0.1)
            b.set(ax.controller.input_vel, 0.0)
            b.set(cfg.control_mode, orig_control_mode)
            b.set(cfg.input_mode, orig_input_mode)
            b.set(cfg.vel_ramp_rate, orig_ramp)
            b.set(cfg.vel_limit, orig_vel_limit)
            b.set(ax.motor.config.current_lim, orig_current_lim)
        except Exception as ex:
            print(f"Restore failed: {ex!r}")

    per_minute = []
    for m in range(int(math.ceil(len(seconds) / 60))):
        chunk = seconds[m * 60:(m + 1) * 60]
        for d in (+1, -1):
            v = [x["Iq_mean_abs"] for x in chunk if x["direction"] == d and x["Iq_mean_abs"] is not None]
            if v:
                per_minute.append({"minute": m + 1, "direction": d, "Iq_mean_abs": round(float(np.mean(v)), 3),
                                   "fet_temp_max": max(x["fet_temp"] for x in chunk)})
    motor_turns = sum(abs(x["vel_mean"]) for x in seconds)

    LOGS.mkdir(exist_ok=True)
    stem = LOGS / f"{start_stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}"
    with open(f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# host_start", start_stamp.isoformat(), "serial", serial, "script", "runin.py"])
        w.writerow(COLUMNS)
        w.writerows([[s[c] for c in COLUMNS] for s in seconds])
    pathlib.Path(f"{stem}.json").write_text(json.dumps(
        {"host_start": start_stamp.isoformat(), "serial": serial, "argv": sys.argv[1:],
         "previous_values_restored": original,
         "seconds_run": len(seconds), "motor_turns": round(motor_turns, 1), "per_minute": per_minute,
         "abort_reason": abort_reason}, indent=2) + "\n")
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": start_stamp.isoformat(), "action": "runin", "argv": sys.argv[1:],
                            "seconds_run": len(seconds), "abort_reason": abort_reason,
                            "log": f"{stem.name}.csv"}) + "\n")
    print("\nminute  dir   cruise |Iq|   FET max")
    for r in per_minute:
        print(f"  {r['minute']:4d}  {r['direction']:+d}   {r['Iq_mean_abs']:7.3f} A   {r['fet_temp_max']:5.1f} °C")
    print(f"\n{len(seconds)} s, about {motor_turns:.0f} motor turns -> {stem.relative_to(WORKDIR)}.csv/.json")
    print(f"Result: {'STOPPED: ' + abort_reason if abort_reason else 'completed'}; axis left IDLE; "
          f"restored: {list(original)}")
    return 3 if abort_reason else 0


if __name__ == "__main__":
    sys.exit(main())
