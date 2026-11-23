#!/usr/bin/env python3
"""Bench test of input_torque as torque feed-forward in the planning input modes.  *** MOTOR MOVES (about 20 s, a few turns) ***

With controller.config.inertia = J, each mode's torque setpoint is J x planned acceleration + input_torque (T = 0.1 Nm):
  trap        position control, then impedance control: a 2 turn trap move at 5 turn/s^2 peaks at T + 5 J while
              accelerating and dips to T - 5 J while decelerating; T stays once the move is done, and a new
              input_torque after the move takes effect
  filter      position control, position filter: a 0.2 turn step rides on T and settles back to T
  ramp        velocity control, velocity ramp: ramping at 5 turn/s^2 gives T + 5 J, cruising and stopped give T
The checks read controller.torque_setpoint over USB (~150 Hz), so they test the setpoint the torque loop gets.
RAM-only settings, restored at the end; ends IDLE. Logs: logs/<stamp>_<serial>_feedforward-test.csv + .json.

Usage (from the repo root):  python tools/feedforward_test.py
"""
import datetime
import json
import sys
import time

from xdrive import usb
from xdrive.props import odrv

from safety_test import IDLE, LOGS, PASSTHROUGH, POS, SETTINGS, TRAP, VEL, VEL_RAMP, WORKDIR, Bench, Unexpected

IMPEDANCE = 4                # ControlMode
POS_FILTER = 3               # InputMode
T = 0.1                      # Nm, input_torque
J = 0.01                     # Nm/(turn/s^2), controller.config.inertia
ACCEL = 5.0                  # turn/s^2: trap accel/decel limits and the velocity ramp rate
TS = "axis0.controller.torque_setpoint"
EXTRA = ["axis0.controller.config.inertia", "axis0.controller.config.input_filter_bandwidth",
         "axis0.controller.input_torque", "axis0.controller.input_vel", "axis0.controller.input_kp",
         "axis0.controller.input_kd"]


def torques(b, start):
    return [b.v(r, TS) for r in b.rows[start:]]


def settled(b, seconds, label, want):
    """Samples for `seconds`; checks every torque setpoint sample equals `want`."""
    start = len(b.rows)
    b.run(seconds)
    ts = torques(b, start)
    worst = max(abs(t - want) for t in ts)
    b.check(label, worst < 1e-3, f"{min(ts):+.4f} to {max(ts):+.4f} Nm vs {want:+.4f}")


def test_trap(b, control_mode, name):
    print(f"trap ({name})")
    b.set("axis0.trap_traj.config.vel_limit", 2.0)
    b.set("axis0.trap_traj.config.accel_limit", ACCEL)
    b.set("axis0.trap_traj.config.decel_limit", ACCEL)
    b.set("axis0.controller.input_kp", 20.0)
    b.set("axis0.controller.input_kd", 0.3)
    b.closed_loop(control_mode, TRAP)
    b.set("axis0.controller.input_torque", T)
    b.event = "torque_ff"
    settled(b, 0.3, f"trap ({name}): T applies before any move", T)
    target = b.get("axis0.encoder.pos_estimate") + 2.0
    b.set("axis0.controller.input_pos", target)
    b.event = "trap_2"
    start = len(b.rows)
    b.run(3.0, until=lambda r: b.v(r, "axis0.controller.trajectory_done") and abs(b.v(r, "axis0.encoder.pos_estimate") - target) < 0.01)
    ts = torques(b, start)
    b.check(f"trap ({name}): accelerating gives T + J a", abs(max(ts) - (T + J * ACCEL)) < 0.005,
            f"peak {max(ts):+.4f} Nm vs {T + J * ACCEL:+.4f}")
    b.check(f"trap ({name}): decelerating gives T - J a", abs(min(ts) - (T - J * ACCEL)) < 0.005,
            f"low {min(ts):+.4f} Nm vs {T - J * ACCEL:+.4f}")
    settled(b, 0.5, f"trap ({name}): T stays after the move", T)
    b.set("axis0.controller.input_torque", -T)
    b.event = "torque_ff_after"
    b.run(0.05)
    settled(b, 0.3, f"trap ({name}): a new input_torque after the move applies", -T)
    b.set("axis0.controller.input_torque", 0.0)
    b.set("axis0.requested_state", IDLE)
    b.idle_and_settle()


def test_filter(b):
    print("filter")
    b.set("axis0.controller.config.input_filter_bandwidth", 10.0)
    b.closed_loop(POS, POS_FILTER)
    b.set("axis0.controller.input_torque", T)
    b.run(0.3)
    b.set("axis0.controller.input_pos", b.get("axis0.encoder.pos_estimate") + 0.2)
    b.event = "step_0.2"
    start = len(b.rows)
    b.run(1.5)
    ts = torques(b, start)
    b.check("filter: the step's acceleration rides on T", max(ts) > T + 0.05 and min(ts) < T,
            f"{min(ts):+.4f} to {max(ts):+.4f} Nm around {T:+.4f}")
    settled(b, 0.3, "filter: settles to T", T)
    b.set("axis0.controller.input_torque", 0.0)
    b.set("axis0.requested_state", IDLE)
    b.idle_and_settle()


def test_ramp(b):
    print("ramp")
    b.set("axis0.controller.config.vel_ramp_rate", ACCEL)
    b.set("axis0.controller.input_vel", 0.0)
    b.closed_loop(VEL, VEL_RAMP)
    b.set("axis0.controller.input_torque", T)
    b.set("axis0.controller.input_vel", 1.0)
    b.event = "vel_1"
    start = len(b.rows)
    b.run(0.2)
    ts = torques(b, start)
    b.check("ramp: ramping up gives T + J a", abs(max(ts) - (T + J * ACCEL)) < 0.005,
            f"peak {max(ts):+.4f} Nm vs {T + J * ACCEL:+.4f}")
    b.run(0.3)
    settled(b, 0.5, "ramp: cruising gives T", T)
    b.set("axis0.controller.input_vel", 0.0)
    b.event = "vel_0"
    b.run(0.6)
    settled(b, 0.3, "ramp: stopped gives T", T)
    b.set("axis0.controller.input_torque", 0.0)
    b.set("axis0.requested_state", IDLE)
    b.idle_and_settle()


def main():
    board = usb.connect()
    serial = format(board.get(odrv.serial_number), "X")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    b = Bench(board, stamp, serial, prefix="feedforward")
    saved = {p: b.get(p) for p in SETTINGS + EXTRA}
    logs, abort = [], None
    try:
        b.set("axis0.requested_state", IDLE)
        b.idle_and_settle()
        b.set("axis0.controller.config.inertia", J)
        test_trap(b, POS, "position control")
        test_trap(b, IMPEDANCE, "impedance control")
        test_filter(b)
        test_ramp(b)
        logs.append(str(b.log("test").relative_to(WORKDIR)))
    except (Unexpected, KeyboardInterrupt) as ex:
        abort = repr(ex)
        print(f"ABORT: {abort}")
    finally:
        try:
            b.set("axis0.requested_state", IDLE)
            t = time.monotonic()
            while abs(b.get("axis0.encoder.vel_estimate")) > 0.5 and time.monotonic() - t < 20:
                time.sleep(0.05)
            for p, val in saved.items():
                b.set(p, val)
            if b.rows:
                logs.append(str(b.log("abort").relative_to(WORKDIR)))
        except Exception as ex:  # USB gone: the only stop left is the PSU
            print(f"!!! Post-run IDLE/restore failed ({ex!r}). Press OUT on the PSU if the motor is driven.")
    out = {"t": datetime.datetime.now().astimezone().isoformat(), "serial": serial, "abort": abort,
           "checks": b.checks, "logs": logs}
    path = LOGS / f"{stamp}_{serial}_feedforward-test.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    failed = [c for c in b.checks if not c["ok"]]
    print(f"{len(b.checks) - len(failed)}/{len(b.checks)} checks passed; axis IDLE; settings restored -> {path.relative_to(WORKDIR)}")
    return 1 if failed or abort else 0


if __name__ == "__main__":
    sys.exit(main())
