#!/usr/bin/env python3
"""Move the rotor to a fractional-turn angle, then leave the axis IDLE.  *** THIS MOVES THE MOTOR. ***

One trap move (the board's trap_traj limits) to the nearest position whose fractional turn is F,
at most half a turn away; holds 0.5 s, then IDLE. Needs input_mode TRAP_TRAJ and no errors. Cogging
makes hold and disturbance results depend on the rotor angle, so regress.py uses this to test at a
fixed angle.

Usage (from the repo root):  python xdrive/tools/move_to.py 0.912
"""
import argparse
import sys
import time

from dump_board import connect

AXIS_STATE_IDLE, AXIS_STATE_CLOSED_LOOP_CONTROL, INPUT_MODE_TRAP_TRAJ = 1, 8, 5


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fraction", type=float, help="fractional turn, 0..1")
    args = ap.parse_args()
    dev = connect(timeout=10)
    if dev is None:
        print("No board found on USB.")
        return 1
    ax = dev.axis0

    def errors():
        return {n: e for n, e in (("axis", ax.error), ("motor", ax.motor.error), ("encoder", ax.encoder.error),
                                  ("controller", ax.controller.error)) if e}

    if errors():
        print(f"Not moving: errors {errors()}")
        return 2
    if ax.controller.config.input_mode != INPUT_MODE_TRAP_TRAJ:
        print(f"Not moving: needs input_mode TRAP_TRAJ ({INPUT_MODE_TRAP_TRAJ}), not {ax.controller.config.input_mode}")
        return 2
    pos = ax.encoder.pos_estimate
    target = pos + (args.fraction - pos) % 1.0
    if target - pos > 0.5:
        target -= 1.0
    try:
        ax.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
        t0 = time.monotonic()
        while ax.current_state != AXIS_STATE_CLOSED_LOOP_CONTROL:
            if errors() or time.monotonic() - t0 > 3.0:
                print(f"Closed loop not reached: state {ax.current_state}, errors {errors()}")
                return 3
            time.sleep(0.02)
        ax.controller.input_pos = target
        time.sleep(0.1)
        t0 = time.monotonic()
        while not ax.controller.trajectory_done:
            if errors() or time.monotonic() - t0 > 5.0:
                print(f"Move to {target:.4f} failed: errors {errors()}")
                return 3
            time.sleep(0.02)
        time.sleep(0.5)
        reached = ax.encoder.pos_estimate
    finally:
        ax.requested_state = AXIS_STATE_IDLE
    print(f"rotor moved {pos:.4f} -> {reached:.4f} turn (target {target:.4f}); axis IDLE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
