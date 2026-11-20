#!/usr/bin/env python3
"""Bench test of CONTROL_MODE_IMPEDANCE_CONTROL over USB.  *** MOTOR MOVES (about 25 s, a few turns) ***

The law under test: torque = input_kp * (pos_setpoint - pos) + input_kd * (vel_setpoint - vel) + input_torque.
  stiffness   a feed-forward torque T deflects the rotor by T / kp (kp 20 and 80 Nm/turn, T = +/-0.5 Nm).
              Cogging (about 0.09 Nm on the 10018) shifts the deflection by up to 0.09 / T of itself, so
              T = 0.5 Nm keeps it inside the 25 % tolerance at every rotor angle.
  tracking    a 0.1 turn setpoint step settles on the target (kp 50, kd 0.5: the position-mode gains' equivalent)
  trap        a trap-traj move ends on target and the axis stays in impedance control
  damping     kp = 0, kd = 0.2, input_vel = 1 turn/s: the rotor runs near 1 turn/s with torque = kd * vel error,
              no position following error although max_pos_error is 0.05, and it stays where it stops
  watchdog    a missed feed in impedance control starts the decelerate-and-hold; feed + clear_errors() resumes
              impedance control
RAM-only settings, restored at the end; ends IDLE. Logs: logs/<stamp>_<serial>_impedance-test.csv + .json.

Usage (from the repo root):  python xdrive/tools/impedance_test.py
"""
import datetime
import json
import math
import sys
import time

from dump_board import connect
from safety_test import CLOSED_LOOP, DECEL_HOLD, IDLE, LOGS, PASSTHROUGH, WORKDIR, SETTINGS, TRAP, Bench, Unexpected

IMPEDANCE = 4  # ControlMode
POS = "axis0.encoder.pos_estimate"
VEL = "axis0.encoder.vel_estimate"
IQ_SP = "axis0.motor.current_control.Iq_setpoint"


def window(b, seconds, last, field, feed=False):
    """Sample for `seconds`; return the mean of `field` over the final `last` seconds."""
    start = len(b.rows)
    b.run(seconds, feed=feed)
    rows = b.rows[start:]
    t_end = rows[-1][0]
    vals = [b.v(r, field) for r in rows if r[0] >= t_end - last]
    return sum(vals) / len(vals)


def gains(b, kp, kd, vel=0.0, torque=0.0, pos=None):
    c = b.ax.controller
    if pos is not None:
        c.input_pos = pos
    c.input_vel, c.input_torque, c.input_kp, c.input_kd = vel, torque, kp, kd


def test_impedance(b):
    kt = b.get("axis0.motor.config.torque_constant")
    direction = b.get("axis0.encoder.config.direction")
    for p in ("axis0.controller.input_pos", "axis0.controller.input_vel", "axis0.controller.input_torque"):
        b.set(p, 0.0)
    gains(b, 20.0, 0.3)
    b.closed_loop(IMPEDANCE, PASSTHROUGH)

    print("stiffness")
    for kp, torques in ((20.0, (0.5, -0.5)), (80.0, (0.5,))):
        gains(b, kp, 0.3, pos=b.ax.encoder.pos_estimate)
        b.event = f"kp{kp:g}_T0"
        p0 = window(b, 1.0, 0.5, POS)
        for t in torques:
            b.ax.controller.input_torque = t
            b.event = f"kp{kp:g}_T{t:+g}"
            dp = window(b, 1.5, 0.5, POS) - p0
            want = t / kp
            b.check(f"kp {kp:g}: T {t:+g} Nm deflects T/kp", abs(dp - want) <= 0.25 * abs(want),
                    f"{dp:+.5f} turn vs {want:+.5f}")
        b.ax.controller.input_torque = 0.0

    print("tracking")
    gains(b, 50.0, 0.5, pos=b.ax.encoder.pos_estimate)
    window(b, 0.5, 0.1, POS)
    target = b.ax.controller.input_pos + 0.1
    b.ax.controller.input_pos = target
    b.event = "step_0.1"
    err = window(b, 1.5, 0.3, POS) - target
    b.check("0.1 turn step settles on target", abs(err) < 0.003, f"final error {err:+.5f} turn")

    print("trap")
    b.set("axis0.trap_traj.config.vel_limit", 2.0)
    b.set("axis0.trap_traj.config.accel_limit", 5.0)
    b.set("axis0.trap_traj.config.decel_limit", 5.0)
    b.set("axis0.controller.config.input_mode", TRAP)
    target = b.ax.encoder.pos_estimate + 2.0
    b.ax.controller.input_pos = target
    b.event = "trap_2"
    b.run(4.0, until=lambda r: b.v(r, "axis0.controller.trajectory_done") and abs(b.v(r, POS) - target) < 0.01)
    err = window(b, 0.5, 0.3, POS) - target
    mode = b.get("axis0.controller.config.control_mode")
    b.check("trap move ends on target in impedance control", abs(err) < 0.003 and mode == IMPEDANCE,
            f"final error {err:+.5f} turn, control_mode {mode}")
    b.set("axis0.controller.config.input_mode", PASSTHROUGH)

    print("damping")
    b.set("axis0.controller.config.max_pos_error", 0.05)
    gains(b, 0.0, 0.2, vel=1.0)
    b.event = "damping_vel1"
    start = len(b.rows)
    v = window(b, 2.5, 1.0, VEL)
    tail = [r for r in b.rows[start:] if r[0] >= b.rows[-1][0] - 1.0]
    torque = sum(b.v(r, IQ_SP) for r in tail) / len(tail) * kt * direction
    b.check("damping only: runs near input_vel", 0.7 <= v <= 1.05 and b.ax.current_state == CLOSED_LOOP,
            f"{v:.3f} turn/s, controller error {b.ax.controller.error:#x}")
    b.check("damping only: torque = kd * vel error", abs(torque - 0.2 * (1.0 - v)) < 0.02,
            f"{torque:+.4f} Nm vs {0.2 * (1.0 - v):+.4f}")
    b.ax.controller.input_vel = 0.0
    b.event = "damping_stop"
    b.run(1.0)
    p_stop = b.ax.encoder.pos_estimate
    b.run(1.0)
    drift = b.ax.encoder.pos_estimate - p_stop
    b.check("damping only: no spring, no position fault", abs(drift) < 0.05 and not b.ax.controller.error
            and b.ax.current_state == CLOSED_LOOP, f"drift {drift:+.4f} turn, controller error {b.ax.controller.error:#x}")
    b.set("axis0.controller.config.max_pos_error", math.inf)

    print("watchdog")
    gains(b, 20.0, 0.3, pos=b.ax.encoder.pos_estimate)
    b.set("axis0.config.watchdog_timeout", 0.2)
    b.set("axis0.config.watchdog_action", DECEL_HOLD)
    b.set("axis0.config.watchdog_decel", 10.0)
    b.set("axis0.config.watchdog_torque_lim", math.inf)
    b.ax.watchdog_feed()
    b.set("axis0.config.enable_watchdog", True)
    b.run(0.5, feed=True)
    p_hold = b.ax.encoder.pos_estimate
    b.event = "stop_feeding"
    row = b.run(1.0, until=lambda r: b.v(r, "axis0.controller.timeout_active"))
    b.run(0.5)
    drift = b.ax.encoder.pos_estimate - p_hold
    b.check("missed feed starts the hold", row is not None and b.ax.current_state == CLOSED_LOOP and abs(drift) < 0.01,
            f"timeout_active {row is not None}, drift {drift:+.4f} turn")
    b.ax.watchdog_feed()
    b.dev.clear_errors()
    b.event = "resume"
    b.run(0.3, feed=True)
    mode = b.get("axis0.controller.config.control_mode")
    b.check("feed + clear_errors resumes impedance control", not b.ax.controller.timeout_active and mode == IMPEDANCE
            and b.ax.current_state == CLOSED_LOOP, f"timeout_active {b.ax.controller.timeout_active}, control_mode {mode}")
    b.set("axis0.config.enable_watchdog", False)
    b.ax.requested_state = IDLE
    return b.log("test")


def main():
    dev = connect(timeout=10)
    serial = format(dev.serial_number, "X")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    b = Bench(dev, stamp, serial, prefix="impedance")
    saved = {p: b.get(p) for p in SETTINGS}
    logs, abort = [], None
    try:
        b.ax.requested_state = IDLE
        b.idle_and_settle()
        logs.append(str(test_impedance(b).relative_to(WORKDIR)))
    except (Unexpected, KeyboardInterrupt) as ex:
        abort = repr(ex)
        print(f"ABORT: {abort}")
    finally:
        try:
            b.ax.requested_state = IDLE
            b.set("axis0.config.enable_watchdog", False)
            t = time.monotonic()
            while abs(b.ax.encoder.vel_estimate) > 0.5 and time.monotonic() - t < 20:
                time.sleep(0.05)
            gains(b, 0.0, 0.0)
            for p, val in saved.items():
                b.set(p, val)
            if b.rows:
                logs.append(str(b.log("abort").relative_to(WORKDIR)))
        except Exception as ex:  # USB gone: the only stop left is the PSU
            print(f"!!! Post-run IDLE/restore failed ({ex!r}). Press OUT on the PSU if the motor is driven.")
    out = {"t": datetime.datetime.now().astimezone().isoformat(), "serial": serial, "abort": abort,
           "checks": b.checks, "logs": logs}
    path = LOGS / f"{stamp}_{serial}_impedance-test.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    failed = [c for c in b.checks if not c["ok"]]
    print(f"{len(b.checks) - len(failed)}/{len(b.checks)} checks passed; axis IDLE; settings restored -> {path.relative_to(WORKDIR)}")
    return 1 if failed or abort else 0


if __name__ == "__main__":
    sys.exit(main())
