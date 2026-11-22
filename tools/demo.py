#!/usr/bin/env python3
"""Demo for an audience: moves and a sine sweep in a loop, or a spring to twist by hand.  *** MOTOR MOVES ***

Without --spring, each loop runs two segments, about 25 s in all, from the angle the rotor is at:
  moves   trapezoidal moves out and back at 2, 4 and 7 turn/s (0.5, 2 and 5 turns), then quick quarter-turn snaps
  sine    input_pos swings out and back along a cosine, starting and ending at rest: 1 turn at 0.5 Hz,
          then 0.5 turn at 1.5 Hz. The host writes it at about 230 Hz; the board's position filter
          (INPUT_MODE_POS_FILTER, 50 rad/s) smooths those steps, which costs at most about 3 % of the swing at 1.5 Hz
Keep hands off the rotor: the loop starts moving again without warning.

With --spring, it runs only the spring, never the loop, so nobody's hands are on the rotor when a loop starts:
  spring  impedance control around the start angle (kp 2 Nm/turn, kd 0.1 Nm/(turn/s), torque capped at about
          0.4 Nm by current_lim 4 A): twist the rotor and it pulls back. Twisted past 0.25 turn, the spring's
          anchor follows the rotor, which bounds how hard it snaps back when let go (2.7 turn/s from a
          0.25 turn twist on the 10018 stand). --spring S ends after S seconds, easing back to within about
          0.05 turn of the start angle (friction and cogging against kp); --spring alone runs until Ctrl-C,
          which leaves the rotor limp.

Speeds stay under the saved controller.config.vel_limit of the example settings (8 turn/s). Any error, a
drop out of closed loop, |vel| above 12 turn/s or Ctrl-C ends the demo with the axis IDLE. Settings are RAM
only and restored at the end. The latest loop's samples go to logs/<stamp>_<serial>_demo-last-loop.csv,
overwritten each loop (the spring's last minute or so to *_demo-spring.csv), and the run is recorded in
logs/actions.jsonl.

Needs a calibrated motor and a ready encoder (the example settings' startup does both).

Usage (from the repo root):
  python tools/demo.py [--loop N]     moves and sine; without --loop, until Ctrl-C
  python tools/demo.py --spring [S]   the spring only; without S, until Ctrl-C
"""
import argparse
import datetime
import itertools
import json
import math
import sys
import time

from impedance_test import IMPEDANCE, gains
from move_test import ERROR_FIELDS, error_problems, trap_time
from safety_test import CLOSED_LOOP, IDLE, IX, LOGS, PASSTHROUGH, POS, SETTINGS, TRAP, WORKDIR, Bench, Unexpected
from xdrive import usb
from xdrive.errors import LinkError
from xdrive.props import odrv

MOVES = [  # (turns out and back, trap vel turn/s, accel turn/s^2)
    (0.5, 2.0, 10.0),
    (2.0, 4.0, 10.0),
    (5.0, 7.0, 20.0),
] + [(0.25, 4.0, 40.0)] * 3
SINES = [(0.5, 0.5, 4.0), (0.25, 1.5, 4.0)]  # (amplitude turn, Hz, seconds: whole periods); swing = 2 x amplitude
SPRING_KP, SPRING_KD, SPRING_REACH = 2.0, 0.1, 0.25  # Nm/turn, Nm/(turn/s), turn
MOVE_CURRENT, SPRING_CURRENT = 8.0, 4.0  # A
PAUSE = 0.5  # s between moves
POS_FILTER, FILTER_BW = 3, 50.0  # InputMode; rad/s
FILTER_BW_PATH = "axis0.controller.config.input_filter_bandwidth"
KEEP_ROWS = 10000  # spring samples kept for the log (about a minute)


class DemoBench(Bench):
    """Bench that also stops on any error, or on leaving closed loop while a segment runs."""
    armed = False

    def sample(self):
        row = super().sample()
        errors = {f: row[1 + IX[f]] for f in ERROR_FIELDS if row[1 + IX[f]]}
        if errors:
            raise Unexpected("error: " + ", ".join(f"{k}={v:#x}" for k, v in errors.items()))
        if self.armed and row[1 + IX["axis0.current_state"]] != CLOSED_LOOP:
            raise Unexpected(f"left closed loop: state {row[1 + IX['axis0.current_state']]}")
        return row


def start(b, control_mode, input_mode, current_lim):
    """IDLE, then closed loop in the given modes, holding where the rotor is. Returns that position."""
    b.armed = False
    b.idle_and_settle()
    b.set("axis0.motor.config.current_lim", current_lim)
    b.closed_loop(control_mode, input_mode)
    b.armed = True
    return b.get("axis0.controller.input_pos")


def moves(b):
    print("  moves")
    home = start(b, POS, TRAP, MOVE_CURRENT)
    for size, vel, accel in MOVES:
        b.set("axis0.trap_traj.config.vel_limit", vel)
        b.set("axis0.trap_traj.config.accel_limit", accel)
        b.set("axis0.trap_traj.config.decel_limit", accel)
        for target in (home + size, home):
            b.event = f"move {target - home:+g}"
            b.set("axis0.controller.input_pos", target)
            limit = trap_time(size, vel, accel, accel) + 2.0
            b.run(0.05)
            if b.run(limit, until=lambda r: b.v(r, "axis0.controller.trajectory_done")) is None:
                raise Unexpected(f"move to {target - home:+g} turn not done after {limit:.1f} s")
            b.run(PAUSE)


def sine(b):
    print("  sine")
    b.set(FILTER_BW_PATH, FILTER_BW)
    home = start(b, POS, POS_FILTER, MOVE_CURRENT)
    for amp, freq, seconds in SINES:
        b.event = f"sine {amp:g} turn {freq:g} Hz"
        w = 2 * math.pi * freq
        t0 = time.monotonic()
        while (t := time.monotonic() - t0) < seconds:
            b.set("axis0.controller.input_vel", amp * w * math.sin(w * t))
            b.set("axis0.controller.input_pos", home + amp * (1.0 - math.cos(w * t)))
            b.sample()
        b.set("axis0.controller.input_vel", 0.0)
        b.set("axis0.controller.input_pos", home)
        b.run(PAUSE)


def spring(b, seconds):
    print(f"spring {'until Ctrl-C' if math.isinf(seconds) else f'for {seconds:g} s'}: twist the rotor by hand")
    home = start(b, IMPEDANCE, PASSTHROUGH, SPRING_CURRENT)
    anchor = home
    gains(b, SPRING_KP, SPRING_KD, pos=anchor)
    b.event = "spring"
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        pos = b.v(b.sample(), "axis0.encoder.pos_estimate")
        if len(b.rows) > 2 * KEEP_ROWS:
            del b.rows[:-KEEP_ROWS]
        if abs(pos - anchor) > SPRING_REACH:
            anchor = pos - math.copysign(SPRING_REACH, pos - anchor)
            b.set("axis0.controller.input_pos", anchor)
    # Ease back to the start angle without a snap: move the anchor at about 1 turn/s.
    b.event = "spring return"
    while abs(anchor - home) > 1e-3:
        anchor += max(-0.01, min(0.01, home - anchor))
        b.set("axis0.controller.input_pos", anchor)
        b.run(0.01)
    b.run(1.0)  # the rotor lags the anchor by about 0.1 turn at 1 turn/s: let the spring pull it in
    gains(b, 0.0, 0.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--loop", type=int, default=None, help="loops of moves and sine (default: until Ctrl-C)")
    mode.add_argument("--spring", type=float, nargs="?", const=math.inf, default=None, metavar="S",
                      help="run only the spring, for S seconds (without S: until Ctrl-C)")
    args = ap.parse_args()

    try:
        board = usb.connect()
    except LinkError as ex:
        print(ex)
        return 1
    serial = format(board.get(odrv.serial_number), "X")
    ax = odrv.axis0
    problems = [p for p, bad in (("motor not calibrated", not board.get(ax.motor.is_calibrated)),
                                 ("encoder not ready", not board.get(ax.encoder.is_ready))) if bad]
    problems += error_problems(board)
    if problems:
        print("Not starting:\n  " + "\n  ".join(problems))
        return 2

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    b = DemoBench(board, stamp, serial, prefix="demo")
    saved = {p: b.get(p) for p in SETTINGS + [FILTER_BW_PATH]}
    b.set("axis0.config.enable_watchdog", False)  # nothing feeds it here; restored with the rest
    LOGS.mkdir(exist_ok=True)
    loops, abort, log = 0, None, None
    name = "spring" if args.spring is not None else "last-loop"
    print(f"Demo on {serial}. Ctrl-C stops it (the motor goes limp).")
    try:
        if args.spring is not None:
            spring(b, args.spring)
        else:
            for n in itertools.count(1) if args.loop is None else range(1, args.loop + 1):
                print(f"loop {n}")
                moves(b)
                sine(b)
                loops = n
                log = b.log(name)
    except (Unexpected, KeyboardInterrupt) as ex:
        abort = "Ctrl-C" if isinstance(ex, KeyboardInterrupt) else str(ex)
    finally:
        try:
            b.armed = False
            b.set("axis0.requested_state", IDLE)
            t = time.monotonic()
            while abs(b.get("axis0.encoder.vel_estimate")) > 0.5 and time.monotonic() - t < 20:
                time.sleep(0.05)
            gains(b, 0.0, 0.0)
            for p, val in saved.items():
                b.set(p, val)
            if b.rows:
                log = b.log(name)
        except Exception as ex:  # USB gone: the only stop left is the PSU
            print(f"!!! Post-run IDLE/restore failed ({ex!r}). Press OUT on the PSU if the motor is driven.")
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": datetime.datetime.now().astimezone().isoformat(), "action": "demo",
                            "argv": sys.argv[1:], "loops_completed": loops, "abort": abort,
                            "log": log.name if log else None}) + "\n")
    done = "spring" if args.spring is not None else f"{loops} loop(s) completed"
    print(f"{done}; {'stopped: ' + abort if abort else 'done'}. Axis IDLE, settings restored.")
    if log:
        print(f"log -> {log.relative_to(WORKDIR)}")
    return 0 if abort in (None, "Ctrl-C") else 3


if __name__ == "__main__":
    sys.exit(main())
