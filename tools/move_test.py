#!/usr/bin/env python3
"""Logged trap-trajectory move test on axis0.  *** THIS MOVES THE MOTOR. ***

1. Checks preconditions (calibrated, encoder ready, position + trap-traj mode,
   no errors, sane bus voltage). Aborts without touching anything if they fail.
2. Applies the test settings given on the command line in RAM only. It never
   calls save_configuration(), so a power cycle restores the saved config.
3. Enters closed loop, which holds the current position (the firmware sets
   input_pos = pos_estimate on entry), then runs out-and-back moves.
4. Samples ~275 Hz the whole time. Any error, unexpected state, timeout or
   Ctrl-C → requested_state = IDLE immediately.
5. Always finishes in IDLE, then puts the changed settings back to their
   previous RAM values.

Output: logs/<stamp>_<serial>_<label>.csv (+ "event" column) and a .json sidecar
with settings, per-move summary, abort reason and decoded errors.

Usage:
  python tools/move_test.py --moves 1,2,5,10 --current-lim 5 --trap-vel 5 --label ladder-low
"""
import argparse
import csv
import datetime
import json
import math
import pathlib
import sys
import time

from sample import FIELDS as BASE_FIELDS
from xdrive import paths, report, usb
from xdrive.enums import AxisState, ControlMode, InputMode
from xdrive.errors import LinkError
from xdrive.props import odrv

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"

FIELDS = BASE_FIELDS + ["axis0.controller.trajectory_done", "axis0.motor.I_bus"]
IX = {f: i for i, f in enumerate(FIELDS)}
ERROR_FIELDS = [f for f in FIELDS if f.endswith("error")]

# CLI option -> board path. Only the ones given on the command line are changed.
SETTINGS = {
    "current_lim": "axis0.motor.config.current_lim",
    "trap_vel": "axis0.trap_traj.config.vel_limit",
    "vel_limit": "axis0.controller.config.vel_limit",  # turn/s; overspeed error at vel_limit * vel_limit_tolerance
    "trap_accel": "axis0.trap_traj.config.accel_limit",
    "trap_decel": "axis0.trap_traj.config.decel_limit",
    "pos_gain": "axis0.controller.config.pos_gain",
    "vel_gain": "axis0.controller.config.vel_gain",
    "vel_int_gain": "axis0.controller.config.vel_integrator_gain",
    "enc_bw": "axis0.encoder.config.bandwidth",  # rad/s; setter recomputes the PLL gains live
    "current_bw": "axis0.motor.config.current_control_bandwidth",  # rad/s; setter recomputes p_gain/i_gain live
    "inertia": "axis0.controller.config.inertia",  # Nm per turn/s² (= J·2π); trap-traj accel feedforward
    "dc_max_pos": "config.dc_max_positive_current",
    "dc_max_neg": "config.dc_max_negative_current",
}


class Abort(Exception):
    pass


def trap_time(dist, v, a, d):
    """Duration of a trapezoidal (or triangular) profile."""
    if dist >= v * v / (2 * a) + v * v / (2 * d):
        return dist / v + v / (2 * a) + v / (2 * d)
    vp = math.sqrt(2 * dist * a * d / (a + d))
    return vp / a + vp / d


CLOSED_LOOP = AxisState.CLOSED_LOOP_CONTROL.value


def error_problems(b):
    """One line per non-zero axis0 error flag set, for a precondition check."""
    return [f"{name} error {report.line(err)}" for name, err in report.errors(b).items() if err]


class Recorder:
    def __init__(self, b):
        self.b = b
        self.props = [paths.prop(f) for f in FIELDS]
        self.t0 = time.monotonic()
        self.rows = []
        self.event = ""
        self.expect_closed_loop = False
        self.max_vel = math.inf
        self.max_follow = 0.25    # turns: abort if pos_estimate falls this far from pos_setpoint
        self.no_current_n = 0     # consecutive samples with big Iq command but ~no measured current

    def sample(self):
        row = [time.monotonic() - self.t0] + paths.read(self.b, self.props) + [self.event]
        self.event = ""
        self.rows.append(row)
        errs = {f: row[1 + IX[f]] for f in ERROR_FIELDS if row[1 + IX[f]]}
        if errs:
            raise Abort("error: " + ", ".join(f"{k}={v:#x}" for k, v in errs.items()))
        vel = row[1 + IX["axis0.encoder.vel_estimate"]]
        if abs(vel) > self.max_vel:
            raise Abort(f"runaway guard: |vel_estimate| {abs(vel):.1f} > {self.max_vel:.1f} turn/s")
        if self.expect_closed_loop:
            follow = abs(row[1 + IX["axis0.encoder.pos_estimate"]] - row[1 + IX["axis0.controller.pos_setpoint"]])
            if follow > self.max_follow:
                raise Abort(f"following error {follow:.3f} turn > {self.max_follow} (rotor not following setpoint)")
            iq_sp = row[1 + IX["axis0.motor.current_control.Iq_setpoint"]]
            iq_m = row[1 + IX["axis0.motor.current_control.Iq_measured"]]
            self.no_current_n = self.no_current_n + 1 if (abs(iq_sp) > 3.0 and abs(iq_m) < 0.25 * abs(iq_sp)) else 0
            if self.no_current_n >= 20:
                raise Abort(f"current not following command (Iq_sp {iq_sp:.1f} A, Iq_meas {iq_m:.2f} A for 20 samples)"
                            " - power stage not driving the motor; reboot after save_configuration?")
        if self.expect_closed_loop and row[1 + IX["axis0.current_state"]] != CLOSED_LOOP:
            raise Abort(f"left closed loop: state={row[1 + IX['axis0.current_state']]}")
        return row

    def run_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.sample()


def segment_summary(rows, name):
    def c(f):
        return [r[1 + IX[f]] for r in rows]
    track = [abs(p - s) for p, s in zip(c("axis0.encoder.pos_estimate"), c("axis0.controller.pos_setpoint"))]
    return {
        "segment": name,
        "t_start": round(rows[0][0], 3),
        "duration_s": round(rows[-1][0] - rows[0][0], 3),
        "samples": len(rows),
        "peak_abs_Iq_setpoint_A": round(max(abs(x) for x in c("axis0.motor.current_control.Iq_setpoint")), 3),
        "peak_abs_Iq_measured_A": round(max(abs(x) for x in c("axis0.motor.current_control.Iq_measured")), 3),
        "peak_abs_vel_turn_s": round(max(abs(x) for x in c("axis0.encoder.vel_estimate")), 3),
        "peak_ibus_A": round(max(c("ibus")), 3),
        "min_ibus_A": round(min(c("ibus")), 3),
        "vbus_min_V": round(min(c("vbus_voltage")), 3),
        "vbus_max_V": round(max(c("vbus_voltage")), 3),
        "max_tracking_error_turn": round(max(track), 4),
        "final_error_turn": round(track[-1], 4),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--moves", required=True, help="comma-separated move sizes in turns, each run out and back")
    ap.add_argument("--settle", type=float, default=1.0, help="seconds to keep logging after each move ends")
    ap.add_argument("--label", default="move-test")
    ap.add_argument("--max-vel", type=float, default=None,
                    help="abort to IDLE if |vel_estimate| exceeds this (turn/s); default 1.5 x expected peak + 2")
    for opt in SETTINGS:
        ap.add_argument("--" + opt.replace("_", "-"), type=float, dest=opt)
    args = ap.parse_args()
    moves = [float(m) for m in args.moves.split(",")]

    try:
        b = usb.connect()
    except LinkError as ex:
        print(ex)
        return 1
    ax = odrv.axis0
    serial = format(b.get(odrv.serial_number), "X")

    # --- Preconditions (read-only) ---
    problems = []
    if not b.get(ax.motor.is_calibrated):
        problems.append("motor not calibrated")
    if not b.get(ax.encoder.is_ready):
        problems.append("encoder not ready")
    if (mode := b.get(ax.controller.config.control_mode)) is not ControlMode.POSITION_CONTROL:
        problems.append(f"control_mode is {mode.name}, not POSITION_CONTROL")
    if (imode := b.get(ax.controller.config.input_mode)) is not InputMode.TRAP_TRAJ:
        problems.append(f"input_mode is {imode.name}, not TRAP_TRAJ")
    problems += error_problems(b)
    vbus = b.get(odrv.vbus_voltage)
    if not 20.0 <= vbus <= 28.0:
        problems.append(f"vbus {vbus:.2f} V outside 20–28 V")
    if problems:
        print("Not starting:\n  " + "\n  ".join(problems))
        return 2

    # --- Apply RAM-only settings ---
    changed = {}  # path -> previous value
    for opt, path in SETTINGS.items():
        val = getattr(args, opt)
        if val is not None:
            changed[path] = paths.get(b, path)
            paths.set(b, path, val)
    trap = {k: paths.get(b, f"axis0.trap_traj.config.{k}") for k in ("vel_limit", "accel_limit", "decel_limit")}
    applied = {path: paths.get(b, path) for path in changed}
    if "axis0.motor.config.current_control_bandwidth" in changed:
        print(f"current loop: bandwidth {b.get(ax.motor.config.current_control_bandwidth):g} rad/s -> "
              f"p_gain {b.get(ax.motor.current_control.p_gain):.4f}, i_gain {b.get(ax.motor.current_control.i_gain):.1f}")
    start_stamp = datetime.datetime.now().astimezone()

    peak = max(min(trap["vel_limit"], math.sqrt(2 * abs(m) * trap["accel_limit"] * trap["decel_limit"]
                                                / (trap["accel_limit"] + trap["decel_limit"]))) for m in moves)
    rec = Recorder(b)
    rec.max_vel = args.max_vel if args.max_vel is not None else 1.5 * peak + 2.0
    print(f"expected peak speed {peak:.2f} turn/s; runaway guard at {rec.max_vel:.1f} turn/s")
    segments, abort_reason, final_errors = [], None, {}
    current = ("closed_loop_entry", 0)  # (segment name, first row) of the segment in progress
    try:
        rec.event = "closed_loop_request"
        b.set(ax.requested_state, AxisState.CLOSED_LOOP_CONTROL)
        deadline = time.monotonic() + 1.0
        while rec.sample()[1 + IX["axis0.current_state"]] != CLOSED_LOOP:
            if time.monotonic() > deadline:
                raise Abort("did not enter closed loop within 1 s")
        rec.expect_closed_loop = True
        home = b.get(ax.controller.input_pos)
        rec.event = "hold"
        i0 = len(rec.rows)
        rec.run_for(1.0)
        segments.append(segment_summary(rec.rows[i0:], "hold"))

        for size in moves:
            for target, name in ((home + size, f"out {size:+g}"), (home, f"back {-size:+g}")):
                rec.event = name
                i0 = len(rec.rows)
                current = (name, i0)
                t_cmd = time.monotonic()
                b.set(ax.controller.input_pos, target)
                limit = trap_time(abs(size), trap["vel_limit"], trap["accel_limit"], trap["decel_limit"]) + 3.0
                done_at = None
                while True:
                    row = rec.sample()
                    now = time.monotonic()
                    if done_at is None and now - t_cmd > 0.05 and row[1 + IX["axis0.controller.trajectory_done"]]:
                        done_at = now
                    if done_at is not None and now - done_at >= args.settle:
                        break
                    if now - t_cmd > limit + args.settle:
                        raise Abort(f"{name}: trajectory not done after {limit:.1f} s")
                segments.append(segment_summary(rec.rows[i0:], name))
                s = segments[-1]
                print(f"  {name:>10}: {s['duration_s']:5.2f} s  |Iq| sp {s['peak_abs_Iq_setpoint_A']:5.2f} / meas "
                      f"{s['peak_abs_Iq_measured_A']:5.2f} A  |vel| {s['peak_abs_vel_turn_s']:5.2f} t/s  "
                      f"ibus {s['min_ibus_A']:+.2f}..{s['peak_ibus_A']:+.2f} A  vbus {s['vbus_min_V']:.2f}-"
                      f"{s['vbus_max_V']:.2f} V  track {s['max_tracking_error_turn']:.4f} t")
    except Abort as ex:
        abort_reason = str(ex)
    except KeyboardInterrupt:
        abort_reason = "Ctrl-C"
    finally:
        try:
            b.set(ax.requested_state, AxisState.IDLE)
        except Exception as ex:  # USB gone: the only stop left is the PSU
            print(f"!!! Could not command IDLE ({ex!r}). Press OUT on the PSU.")
        try:
            time.sleep(0.1)
            rec.event = "idle"
            rec.expect_closed_loop = False
            try:
                rec.sample()
            except Abort:
                pass
            final_errors = {name: report.jsonable(err) for name, err in report.errors(b).items()}
            final_errors["last_drv_fault"] = {"hex": f"0x{b.get(ax.last_drv_fault):08X}", "flags": []}
            # The overspeed check runs in IDLE too: restoring a lower vel_limit while the rotor still
            # coasts (after an abort at speed) latches CONTROLLER_ERROR_OVERSPEED. Wait for it to slow.
            t_coast = time.monotonic()
            while abs(paths.get(b, "axis0.encoder.vel_estimate")) > 1.0 and time.monotonic() - t_coast < 30.0:
                time.sleep(0.1)
            for path, old in changed.items():
                paths.set(b, path, old)
        except Exception as ex:
            print(f"Post-run read/restore failed: {ex!r}")

    # Summarize the segment that was in progress when the test aborted (the interesting one)
    if abort_reason and len(rec.rows) > current[1]:
        segments.append(segment_summary(rec.rows[current[1]:], current[0] + " (aborted)"))
        print(f"  {segments[-1]['segment']}: " +
              ", ".join(f"{k}={v}" for k, v in segments[-1].items() if k != "segment"))

    LOGS.mkdir(exist_ok=True)
    stem = LOGS / f"{start_stamp:%Y%m%d-%H%M%S}_{serial}_{args.label}"
    with open(f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# host_start", start_stamp.isoformat(), "serial", serial, "script", "move_test.py"])
        w.writerow(["t"] + FIELDS + ["event"])
        w.writerows(rec.rows)
    meta = {
        "host_start": start_stamp.isoformat(), "serial": serial, "argv": sys.argv[1:],
        "moves": moves, "expected_peak_vel": round(peak, 3), "runaway_guard_vel": round(rec.max_vel, 3),
        "settings_applied_ram_only": applied, "previous_values_restored": changed,
        "trap_traj": trap, "abort_reason": abort_reason, "final_errors": final_errors, "segments": segments,
        "samples": len(rec.rows), "rate_hz": round(len(rec.rows) / max(rec.rows[-1][0], 1e-9), 1) if rec.rows else 0,
    }
    pathlib.Path(f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n")
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": start_stamp.isoformat(), "action": "move_test", "argv": sys.argv[1:],
                            "abort_reason": abort_reason, "log": f"{stem.name}.csv"}) + "\n")

    print(f"\n{len(rec.rows)} samples ({meta['rate_hz']} Hz) -> {stem.relative_to(WORKDIR)}.csv/.json")
    print(f"Result: {'ABORTED: ' + abort_reason if abort_reason else 'completed'}; axis left IDLE; "
          f"RAM settings restored: {list(changed) or 'none changed'}")
    for name, d in final_errors.items():
        if d["flags"] or d.get("unknown_bits"):
            print(f"  {name} = {d['hex']}  {' | '.join(d['flags'])}")
    return 3 if abort_reason else 0


if __name__ == "__main__":
    sys.exit(main())
