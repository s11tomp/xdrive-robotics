#!/usr/bin/env python3
"""Holding current and position error over a span of rotor angles.  *** THE MOTOR MOVES (small moves). ***

Holds the rotor at --points evenly spaced positions across --span turns, starting at --start (default:
where the rotor is). Each point is approached twice, from below and from above (a trap move to
point - --approach or point + --approach, then to the point), and held for --hold seconds after a
--settle wait. Per point and direction it reports the mean holding current, the position error
(pos_estimate - pos_setpoint, in counts: its mean, standard deviation and largest value) and the current
noise.

What the two directions separate: after a move the rotor stops against friction, so the holding current
approached from below sits at the top of the friction band and the one approached from above at the bottom.
Their mean is the position-dependent torque the rotor is held against (a gearbox's detents, the motor's
cogging); half their difference, unsigned, is the static friction.

pos_estimate counts from boot, so a later run with the same --start holds at the same rotor angles only
while the board has not rebooted. A --start up to 100 turns away is reached with a trap move first.

Uses the move_test guards (errors, following error, current not following, speed) and the board's
current trap-trajectory settings unless given on the command line (RAM only). Always ends in IDLE with every
touched setting restored. Nothing is saved.

Usage:
  python tools/hold_sweep.py --span 0.155 --points 16 --hold 2 --label hold-sweep
  python tools/hold_sweep.py --start 0.0444 --span 0.155 --points 16 --label hold-sweep-after
"""
import argparse
import csv
import datetime
import json
import pathlib
import sys
import time

import numpy as np

from move_test import CLOSED_LOOP, FIELDS, IX, SETTINGS, Abort, Recorder, error_problems, trap_time
from xdrive import paths, usb
from xdrive.enums import AxisState, ControlMode, InputMode
from xdrive.errors import LinkError
from xdrive.props import odrv

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
CPR = 16384
P = "axis0.motor.current_control."


def go_to(b, rec, target, trap):
    """Trap move to target; returns once the trajectory is done. Raises Abort on a timeout."""
    dist = abs(target - b.get(odrv.axis0.controller.input_pos))
    timeout = trap_time(dist, trap["vel_limit"], trap["accel_limit"], trap["decel_limit"]) + 3.0
    b.set(odrv.axis0.controller.input_pos, target)
    t_cmd = time.monotonic()
    while True:
        row = rec.sample()
        if time.monotonic() - t_cmd > 0.05 and row[1 + IX["axis0.controller.trajectory_done"]]:
            return
        if time.monotonic() - t_cmd > timeout:
            raise Abort(f"move to {target:.4f} not done after {timeout:.1f} s")


def hold_stats(rows):
    a = np.array([r[1:1 + len(FIELDS)] for r in rows], dtype=float)
    col = lambda f: a[:, IX[f]]
    err = (col("axis0.encoder.pos_estimate") - col("axis0.controller.pos_setpoint")) * CPR
    return {"samples": len(rows),
            "Iq_mean_A": round(float(col(P + "Iq_measured").mean()), 3),
            "Iq_std_A": round(float(col(P + "Iq_measured").std()), 3),
            "err_mean_counts": round(float(err.mean()), 2),
            "err_std_counts": round(float(err.std()), 2),
            "err_max_counts": round(float(np.abs(err).max()), 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=float, help="first point, in pos_estimate turns (default: the current position)")
    ap.add_argument("--span", type=float, required=True, help="turns covered by the points")
    ap.add_argument("--points", type=int, default=16)
    ap.add_argument("--approach", type=float, default=0.02, help="turns past the point to approach from")
    ap.add_argument("--settle", type=float, default=0.5, help="seconds after a move before measuring")
    ap.add_argument("--hold", type=float, default=2.0, help="seconds measured per point and direction")
    ap.add_argument("--label", default="hold-sweep")
    for opt in SETTINGS:
        ap.add_argument("--" + opt.replace("_", "-"), type=float, dest=opt)
    args = ap.parse_args()
    if not 0 < args.span <= 1.0 or args.points < 1 or not 0 < args.approach <= 0.1:
        raise SystemExit("need 0 < --span <= 1, --points >= 1 and 0 < --approach <= 0.1")

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
    if b.get(ax.controller.config.control_mode) is not ControlMode.POSITION_CONTROL:
        problems.append("control_mode is not POSITION_CONTROL")
    if b.get(ax.controller.config.input_mode) is not InputMode.TRAP_TRAJ:
        problems.append("input_mode is not TRAP_TRAJ")
    problems += error_problems(b)
    if problems:
        print("Not starting:\n  " + "\n  ".join(problems))
        return 2

    changed = {}
    for opt, path in SETTINGS.items():
        if (val := getattr(args, opt)) is not None:
            changed[path] = paths.get(b, path)
            paths.set(b, path, val)
    applied = {path: paths.get(b, path) for path in changed}
    start_stamp = datetime.datetime.now().astimezone()
    rec = Recorder(b)
    trap = {k: paths.get(b, f"axis0.trap_traj.config.{k}") for k in ("vel_limit", "accel_limit", "decel_limit")}
    rec.max_vel = trap["vel_limit"] * 1.5 + 1.0
    results, abort_reason, start = [], None, args.start
    try:
        b.set(ax.requested_state, AxisState.CLOSED_LOOP_CONTROL)
        deadline = time.monotonic() + 1.0
        while rec.sample()[1 + IX["axis0.current_state"]] != CLOSED_LOOP:
            if time.monotonic() > deadline:
                raise Abort("did not enter closed loop within 1 s")
        rec.expect_closed_loop = True
        home = b.get(ax.controller.input_pos)
        if start is None:
            start = home
        if abs(start - home) > 100.0:
            raise Abort(f"--start {start:.4f} is more than 100 turns from the rotor ({home:.4f})")
        step = args.span / args.points
        print(f"start {start:.4f} turn, {args.points} points {step:.5f} turn apart, approach ±{args.approach:g}")
        print("  point      pos   dir   Iq mean   Iq σ   err mean   err σ  err max (counts)")
        for k in range(args.points):
            point = start + k * step
            for direction, sign in (("up", -1), ("down", +1)):
                rec.event = f"approach {k} {direction}"
                go_to(b, rec, point + sign * args.approach, trap)
                go_to(b, rec, point, trap)
                rec.run_for(args.settle)
                rec.event = f"hold {k} {direction}"
                i0 = len(rec.rows)
                rec.run_for(args.hold)
                s = {"point": k, "pos_turn": round(point, 5), "approach": direction, **hold_stats(rec.rows[i0:])}
                results.append(s)
                print(f"  {k:5d}  {point:8.4f}  {direction:>4}  {s['Iq_mean_A']:+7.3f}  {s['Iq_std_A']:6.3f}  "
                      f"{s['err_mean_counts']:+8.2f}  {s['err_std_counts']:6.2f}  {s['err_max_counts']:6.2f}", flush=True)
        rec.event = "return"
        go_to(b, rec, home, trap)
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
            for path, old in changed.items():
                paths.set(b, path, old)
        except Exception as ex:
            print(f"Restore failed: {ex!r}")

    summary = {}
    up = {r["point"]: r["Iq_mean_A"] for r in results if r["approach"] == "up"}
    down = {r["point"]: r["Iq_mean_A"] for r in results if r["approach"] == "down"}
    both = sorted(set(up) & set(down))
    if both:
        detent = [(up[k] + down[k]) / 2 for k in both]
        friction = [abs(up[k] - down[k]) / 2 for k in both]  # unsigned: the current's sign depends on the encoder direction
        summary = {"detent_Iq_A_min": round(min(detent), 3), "detent_Iq_A_max": round(max(detent), 3),
                   "friction_Iq_A_mean": round(float(np.mean(friction)), 3),
                   "friction_Iq_A_max": round(max(friction), 3),
                   "holding_Iq_A_peak": round(max(abs(r["Iq_mean_A"]) for r in results), 3),
                   "err_max_counts": max(r["err_max_counts"] for r in results),
                   "err_std_counts_max": max(r["err_std_counts"] for r in results)}
        print("\nper point: mean of the two directions (the held-against torque), half their difference (friction, unsigned)")
        for k, d, f in zip(both, detent, friction):
            print(f"  {k:5d}  {d:+7.3f} A  {f:+7.3f} A")
        print("summary: " + ", ".join(f"{k} {v}" for k, v in summary.items()))

    LOGS.mkdir(exist_ok=True)
    stem = LOGS / f"{start_stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}"
    with open(f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# host_start", start_stamp.isoformat(), "serial", serial, "script", "hold_sweep.py"])
        w.writerow(["t"] + FIELDS + ["event"])
        w.writerows(rec.rows)
    pathlib.Path(f"{stem}.json").write_text(json.dumps(
        {"host_start": start_stamp.isoformat(), "serial": serial, "argv": sys.argv[1:], "start_turn": start,
         "settings_applied_ram_only": applied,
         "previous_values_restored": changed, "results": results, "summary": summary,
         "abort_reason": abort_reason}, indent=2) + "\n")
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": start_stamp.isoformat(), "action": "hold_sweep", "argv": sys.argv[1:],
                            "start_turn": start, "abort_reason": abort_reason, "log": f"{stem.name}.csv"}) + "\n")
    print(f"\n-> {stem.relative_to(WORKDIR)}.csv/.json")
    print(f"Result: {'ABORTED: ' + abort_reason if abort_reason else 'completed'}; axis left IDLE; "
          f"restored: {list(changed) or 'none changed'}")
    return 3 if abort_reason else 0


if __name__ == "__main__":
    sys.exit(main())
