#!/usr/bin/env python3
"""Bench test of the firmware safety features.  *** THIS MOVES THE MOTOR. ***

Tests (each starts from IDLE, uses RAM-only settings, ends IDLE; settings restored at the end):
  watchdog   DISARM: a missed feed while holding disarms with WATCHDOG_TIMER_EXPIRED.
             DECEL_HOLD: a missed feed during a 5 turn/s trap move ramps to a stop at
             watchdog_decel and holds; inputs are ignored; feed + clear_errors() resumes from
             the hold position. Repeated with watchdog_torque_lim = 0.1 Nm.
  limits     pos_min/pos_max = start -/+ 2 turn: a trap move to +5 stops at +2; velocity control
             stops at the limit and may move back; torque control (not clamped) drives past and
             faults POS_LIMIT_VIOLATION; closed loop entered outside the limits faults at once.
  following  max_pos_error 0.05 turn / max_vel_error 2 turn/s: a normal 6 turn/s move passes; a
             move too fast for a 1 A current limit trips POS_FOLLOWING_ERROR, then VEL_FOLLOWING_ERROR.

Every sample is logged (~150 Hz) to logs/<stamp>_<serial>_safety-<test>.csv; the checks and their
results go to logs/<stamp>_<serial>_safety.json. Exit code 1 if any check fails.

Usage (from the repo root):  python tools/safety_test.py [--tests watchdog,limits,following]
"""
import argparse
import csv
import datetime
import json
import math
import pathlib
import sys
import time

from dump_board import connect, decode_bitmask
from move_test import FIELDS as MOVE_FIELDS
from sample import resolve

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
FIELDS = MOVE_FIELDS + ["axis0.controller.timeout_active", "axis0.controller.torque_setpoint"]
IX = {f: i for i, f in enumerate(FIELDS)}
CLOSED_LOOP, IDLE = 8, 1
POS, VEL, TORQUE = 3, 2, 1                  # ControlMode
PASSTHROUGH, VEL_RAMP, TRAP = 1, 2, 5       # InputMode
DISARM, DECEL_HOLD = 0, 1                   # WatchdogAction
RUNAWAY = 12.0                              # turn/s: IDLE immediately above this

SETTINGS = [  # every path a test may change; restored at the end
    "axis0.config.enable_watchdog", "axis0.config.watchdog_timeout", "axis0.config.watchdog_action",
    "axis0.config.watchdog_decel", "axis0.config.watchdog_torque_lim",
    "axis0.controller.config.control_mode", "axis0.controller.config.input_mode",
    "axis0.controller.config.pos_min", "axis0.controller.config.pos_max", "axis0.controller.config.pos_limit_margin",
    "axis0.controller.config.max_pos_error", "axis0.controller.config.max_vel_error",
    "axis0.controller.config.vel_ramp_rate", "axis0.motor.config.current_lim",
    "axis0.trap_traj.config.vel_limit", "axis0.trap_traj.config.accel_limit", "axis0.trap_traj.config.decel_limit",
]


class Unexpected(Exception):
    pass


class Bench:
    def __init__(self, dev, stamp, serial, prefix="safety"):
        self.dev, self.ax = dev, dev.axis0
        self.prefix = prefix
        self.props = [resolve(dev, f) for f in FIELDS]
        self.stamp, self.serial = stamp, serial
        self.rows, self.event, self.t0 = [], "", time.monotonic()
        self.checks = []

    # --- sampling -------------------------------------------------------------------------------
    def sample(self):
        row = [time.monotonic() - self.t0] + [p.get_value() for p in self.props] + [self.event]
        self.event = ""
        self.rows.append(row)
        if abs(row[1 + IX["axis0.encoder.vel_estimate"]]) > RUNAWAY:
            raise Unexpected(f"runaway guard: |vel| > {RUNAWAY} turn/s")
        return row

    def v(self, row, field):
        return row[1 + IX[field]]

    def run(self, seconds, feed=False, until=None):
        """Sample for `seconds` (feeding the watchdog if asked); stop early when until(row) is true."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if feed:
                self.ax.watchdog_feed()
            row = self.sample()
            if until and until(row):
                return row
        return None

    def log(self, name):
        path = LOGS / f"{self.stamp}_{self.serial}_{self.prefix}-{name}.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t"] + FIELDS + ["event"])
            w.writerows(self.rows)
        self.rows = []
        return path

    def check(self, name, ok, detail):
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # --- board helpers --------------------------------------------------------------------------
    def set(self, path, value):
        resolve(self.dev, path).set_value(value)

    def get(self, path):
        return resolve(self.dev, path).get_value()

    def errors(self):
        return {"axis": self.ax.error, "motor": self.ax.motor.error, "encoder": self.ax.encoder.error,
                "controller": self.ax.controller.error}

    def controller_flags(self):
        return decode_bitmask(self.ax.controller.error, "CONTROLLER_ERROR_")["flags"]

    def idle_and_settle(self):
        """IDLE, wait for the rotor to coast below 0.5 turn/s, then clear errors."""
        self.ax.requested_state = IDLE
        t = time.monotonic()
        while abs(self.ax.encoder.vel_estimate) > 0.5 and time.monotonic() - t < 20:
            self.sample()
        self.dev.clear_errors()

    def closed_loop(self, control_mode, input_mode):
        self.set("axis0.controller.config.control_mode", control_mode)
        self.set("axis0.controller.config.input_mode", input_mode)
        self.event = "closed_loop"
        # An enabled watchdog also counts down in IDLE and latches its error there: feed, then clear.
        self.ax.watchdog_feed()
        self.dev.clear_errors()
        self.ax.requested_state = CLOSED_LOOP
        self.run(0.4, feed=True)
        if self.ax.current_state != CLOSED_LOOP:
            raise Unexpected(f"did not enter closed loop: state {self.ax.current_state}, errors {self.errors()}")


def test_watchdog(b):
    print("watchdog")
    b.set("axis0.config.watchdog_timeout", 0.2)
    # DISARM: holding, stop feeding -> limp with the error.
    b.set("axis0.config.watchdog_action", DISARM)
    b.set("axis0.config.enable_watchdog", True)
    b.closed_loop(POS, PASSTHROUGH)
    b.event = "stop_feeding"
    row = b.run(1.0, until=lambda r: b.v(r, "axis0.current_state") != CLOSED_LOOP)
    b.check("DISARM disarms with WATCHDOG_TIMER_EXPIRED",
            row is not None and "AXIS_ERROR_WATCHDOG_TIMER_EXPIRED" in decode_bitmask(b.ax.error, "AXIS_ERROR_")["flags"],
            f"state {b.ax.current_state}, axis error {b.ax.error:#x}")
    b.idle_and_settle()

    for cap in (math.inf, 0.1):
        tag = "torque cap 0.1 Nm" if cap == 0.1 else "no torque cap"
        b.set("axis0.config.watchdog_action", DECEL_HOLD)
        b.set("axis0.config.watchdog_decel", 10.0)
        b.set("axis0.config.watchdog_torque_lim", cap)
        b.set("axis0.trap_traj.config.vel_limit", 5.0)
        b.set("axis0.trap_traj.config.accel_limit", 10.0)
        b.set("axis0.trap_traj.config.decel_limit", 10.0)
        b.closed_loop(POS, TRAP)
        b.ax.controller.input_pos = b.ax.encoder.pos_estimate + 20.0
        b.event = "move"
        b.run(1.3, feed=True)                      # 0.5 s ramp + 0.8 s cruise at 5 turn/s
        b.event = "stop_feeding"
        t_stop = b.rows[-1][0]
        row = b.run(1.0, until=lambda r: b.v(r, "axis0.controller.timeout_active"))
        if row is None:
            b.check(f"DECEL_HOLD ({tag}) enters timeout", False, "timeout_active never set")
            b.idle_and_settle()
            continue
        t_to = row[0]
        v0, p0 = b.v(row, "axis0.encoder.vel_estimate"), b.v(row, "axis0.encoder.pos_estimate")
        b.run(1.5)                                 # 0.5 s decel + 1 s hold
        dec = [r for r in b.rows if r[0] >= t_to]
        stopped = next((r for r in dec if abs(b.v(r, "axis0.controller.vel_setpoint")) < 1e-6), None)
        b.check(f"DECEL_HOLD ({tag}) timeout after the last feed", 0.15 <= t_to - t_stop <= 0.35,
                f"{t_to - t_stop:.3f} s (watchdog_timeout 0.2 s + sampling)")
        b.check(f"DECEL_HOLD ({tag}) stays armed", all(b.v(r, "axis0.current_state") == CLOSED_LOOP for r in dec),
                f"errors {b.errors()}")
        if stopped:
            t_dec = stopped[0] - t_to
            b.check(f"DECEL_HOLD ({tag}) setpoint stop time ≈ v0/decel", abs(t_dec - abs(v0) / 10.0) < 0.06,
                    f"{t_dec:.3f} s vs {abs(v0) / 10.0:.3f} s from {v0:.2f} turn/s")
        p_end = b.v(dec[-1], "axis0.encoder.pos_estimate")
        b.check(f"DECEL_HOLD ({tag}) stop distance ≈ v0²/(2·decel)", abs(abs(p_end - p0) - v0 * v0 / 20.0) < 0.15,
                f"{p_end - p0:+.3f} turn vs {v0 * v0 / 20.0:.3f}")
        tail = [b.v(r, "axis0.encoder.pos_estimate") for r in dec if r[0] > dec[-1][0] - 0.8]
        b.check(f"DECEL_HOLD ({tag}) holds still", max(tail) - min(tail) < 0.01,
                f"spread {max(tail) - min(tail):.4f} turn over the last 0.8 s")
        if cap == 0.1:
            tq = max(abs(b.v(r, "axis0.motor.current_control.Iq_setpoint")) for r in dec) * b.get("axis0.motor.config.torque_constant")
            b.check("DECEL_HOLD torque stays under watchdog_torque_lim", tq <= 0.1 + 1e-3, f"peak {tq:.3f} N·m")
        # Inputs ignored during the timeout.
        hold = b.ax.encoder.pos_estimate
        b.ax.controller.input_pos = hold + 3.0
        b.event = "input_during_timeout"
        b.run(0.6)
        moved = abs(b.ax.encoder.pos_estimate - hold)
        b.check(f"DECEL_HOLD ({tag}) ignores input_pos", moved < 0.01, f"moved {moved:.4f} turn")
        # Resume: feed, clear_errors -> timeout ends, inputs at the hold position, no jump.
        b.ax.watchdog_feed()
        b.dev.clear_errors()
        b.event = "cleared"
        b.run(0.6, feed=True)
        moved = abs(b.ax.encoder.pos_estimate - hold)
        b.check(f"DECEL_HOLD ({tag}) resumes without a jump",
                not b.ax.controller.timeout_active and b.ax.current_state == CLOSED_LOOP and moved < 0.01
                and abs(b.ax.controller.input_pos - hold) < 0.02,
                f"timeout_active {b.ax.controller.timeout_active}, moved {moved:.4f} turn, "
                f"input_pos - hold {b.ax.controller.input_pos - hold:+.4f}")
        b.ax.requested_state = IDLE
        b.idle_and_settle()
    b.set("axis0.config.enable_watchdog", False)
    return b.log("watchdog")


def test_limits(b):
    print("limits")
    start = b.ax.encoder.pos_estimate
    lo, hi = start - 2.0, start + 2.0
    b.set("axis0.controller.config.pos_min", lo)
    b.set("axis0.controller.config.pos_max", hi)
    b.set("axis0.controller.config.pos_limit_margin", 0.1)
    b.set("axis0.trap_traj.config.vel_limit", 4.0)
    b.set("axis0.trap_traj.config.accel_limit", 10.0)
    b.set("axis0.trap_traj.config.decel_limit", 10.0)

    b.closed_loop(POS, TRAP)
    b.ax.controller.input_pos = start + 5.0
    b.event = "trap_to_+5"
    b.run(3.0)
    p = b.ax.encoder.pos_estimate
    b.check("trap move to +5 stops at pos_max", abs(p - hi) < 0.02 and b.ax.current_state == CLOSED_LOOP,
            f"pos - pos_max {p - hi:+.4f} turn, errors {b.errors()}")
    b.ax.requested_state = IDLE
    b.idle_and_settle()

    b.set("axis0.controller.config.vel_ramp_rate", 20.0)
    b.closed_loop(VEL, VEL_RAMP)
    b.ax.controller.input_vel = -2.0
    b.event = "vel_-2"
    b.run(3.0)
    p = b.ax.encoder.pos_estimate
    b.check("velocity control stops at pos_min", lo - 0.1 < p <= lo + 0.01 and b.ax.current_state == CLOSED_LOOP,
            f"pos - pos_min {p - lo:+.4f} turn, errors {b.errors()}")
    b.ax.controller.input_vel = 2.0
    b.event = "vel_+2"
    b.run(0.5)
    b.check("velocity control may move back inside", b.ax.encoder.pos_estimate > p + 0.3,
            f"moved {b.ax.encoder.pos_estimate - p:+.3f} turn in 0.5 s")
    b.ax.controller.input_vel = 0.0
    b.ax.requested_state = IDLE
    b.idle_and_settle()

    b.closed_loop(TORQUE, PASSTHROUGH)
    b.ax.controller.input_torque = 0.15
    b.event = "torque_+0.15"
    row = b.run(6.0, until=lambda r: b.v(r, "axis0.current_state") != CLOSED_LOOP)
    b.ax.controller.input_torque = 0.0
    flags = b.controller_flags()
    b.check("torque control past pos_max faults POS_LIMIT_VIOLATION",
            row is not None and "CONTROLLER_ERROR_POS_LIMIT_VIOLATION" in flags,
            f"flags {flags}, fault at pos - pos_max {b.v(row, 'axis0.encoder.pos_estimate') - hi:+.3f} turn"
            if row else "no fault within 6 s")
    b.idle_and_settle()

    outside = b.ax.encoder.pos_estimate
    b.event = "closed_loop_outside"
    b.set("axis0.controller.config.control_mode", POS)
    b.set("axis0.controller.config.input_mode", PASSTHROUGH)
    b.ax.requested_state = CLOSED_LOOP
    b.run(0.5)
    flags = b.controller_flags()
    # A one-period torque kick on entry (125 us) is too short for this ~150 Hz sampler, and
    # Iq_setpoint is computed while disarmed too, so neither can show one.
    b.check("closed loop outside the limits faults at once",
            b.ax.current_state != CLOSED_LOOP and "CONTROLLER_ERROR_POS_LIMIT_VIOLATION" in flags,
            f"start {outside - hi:+.3f} turn past pos_max, state {b.ax.current_state}, flags {flags}, "
            f"moved {b.ax.encoder.pos_estimate - outside:+.4f} turn")
    b.idle_and_settle()
    b.set("axis0.controller.config.pos_min", -math.inf)
    b.set("axis0.controller.config.pos_max", math.inf)
    return b.log("limits")


def test_following(b):
    print("following")
    b.set("axis0.controller.config.max_pos_error", 0.05)
    b.set("axis0.controller.config.max_vel_error", 2.0)
    b.set("axis0.trap_traj.config.vel_limit", 6.0)
    b.set("axis0.trap_traj.config.accel_limit", 5.0)
    b.set("axis0.trap_traj.config.decel_limit", 5.0)
    b.closed_loop(POS, TRAP)
    b.ax.controller.input_pos = b.ax.encoder.pos_estimate + 10.0
    b.event = "normal_move"
    b.run(3.5)
    b.check("normal 6 turn/s move does not trip", b.ax.current_state == CLOSED_LOOP and not b.ax.controller.error,
            f"errors {b.errors()}")
    b.ax.requested_state = IDLE
    b.idle_and_settle()

    for name, pos_lim, vel_lim, flag in (("position", 0.05, math.inf, "CONTROLLER_ERROR_POS_FOLLOWING_ERROR"),
                                         ("velocity", math.inf, 2.0, "CONTROLLER_ERROR_VEL_FOLLOWING_ERROR")):
        b.set("axis0.controller.config.max_pos_error", pos_lim)
        b.set("axis0.controller.config.max_vel_error", vel_lim)
        b.set("axis0.motor.config.current_lim", 1.0)
        b.set("axis0.trap_traj.config.vel_limit", 8.0)
        b.set("axis0.trap_traj.config.accel_limit", 60.0)
        b.set("axis0.trap_traj.config.decel_limit", 60.0)
        b.closed_loop(POS, TRAP)
        b.ax.controller.input_pos = b.ax.encoder.pos_estimate + 10.0
        b.event = f"fast_move_{name}"
        row = b.run(3.0, until=lambda r: b.v(r, "axis0.current_state") != CLOSED_LOOP)
        flags = b.controller_flags()
        b.check(f"{name} following error trips", row is not None and flag in flags, f"flags {flags}")
        b.idle_and_settle()
        b.set("axis0.motor.config.current_lim", 15.0)
    b.set("axis0.controller.config.max_pos_error", math.inf)
    b.set("axis0.controller.config.max_vel_error", math.inf)
    return b.log("following")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tests", default="watchdog,limits,following")
    args = ap.parse_args()
    dev = connect(timeout=10)
    serial = format(dev.serial_number, "X")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    b = Bench(dev, stamp, serial)
    saved = {p: b.get(p) for p in SETTINGS}
    tests = {"watchdog": test_watchdog, "limits": test_limits, "following": test_following}
    logs, abort = [], None
    try:
        b.ax.requested_state = IDLE
        b.idle_and_settle()
        for name in args.tests.split(","):
            logs.append(str(tests[name](b).relative_to(WORKDIR)))
    except (Unexpected, KeyboardInterrupt) as ex:
        abort = repr(ex)
        print(f"ABORT: {abort}")
    finally:
        try:
            b.ax.requested_state = IDLE
            t = time.monotonic()
            while abs(b.ax.encoder.vel_estimate) > 0.5 and time.monotonic() - t < 20:
                time.sleep(0.05)
            for p, val in saved.items():
                b.set(p, val)
            if b.rows:
                logs.append(str(b.log("abort").relative_to(WORKDIR)))
        except Exception as ex:  # USB gone: the only stop left is the PSU
            print(f"!!! Post-run IDLE/restore failed ({ex!r}). Press OUT on the PSU if the motor is driven.")
    out = {"t": datetime.datetime.now().astimezone().isoformat(), "serial": serial, "tests": args.tests,
           "abort": abort, "checks": b.checks, "logs": logs}
    path = LOGS / f"{stamp}_{serial}_safety.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    failed = [c for c in b.checks if not c["ok"]]
    print(f"{len(b.checks) - len(failed)}/{len(b.checks)} checks passed; axis IDLE; settings restored -> {path.relative_to(WORKDIR)}")
    return 1 if failed or abort else 0


if __name__ == "__main__":
    sys.exit(main())
