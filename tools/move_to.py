#!/usr/bin/env python3
"""Move the rotor to a fractional-turn angle, then leave the axis IDLE.  *** THIS MOVES THE MOTOR. ***

One trap move (the board's trap_traj limits) to the nearest position whose fractional turn is F,
at most half a turn away; holds 0.5 s, then IDLE. Needs input_mode TRAP_TRAJ and no errors. Cogging
makes hold and disturbance results depend on the rotor angle, so regress.py uses this to test at a
fixed angle.

Usage (from the repo root):  python tools/move_to.py 0.912
"""
import argparse
import sys
import time

from xdrive import report, usb
from xdrive.enums import AxisState, InputMode
from xdrive.errors import LinkError
from xdrive.props import odrv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fraction", type=float, help="fractional turn, 0..1")
    args = ap.parse_args()
    try:
        b = usb.connect()
    except LinkError as ex:
        print(ex)
        return 1
    ax = odrv.axis0

    def errors():
        return {n: report.line(e) for n, e in report.errors(b).items() if e}

    if errors():
        print(f"Not moving: errors {errors()}")
        return 2
    mode = b.get(ax.controller.config.input_mode)
    if mode is not InputMode.TRAP_TRAJ:
        print(f"Not moving: needs input_mode TRAP_TRAJ, not {mode.name}")
        return 2
    pos = b.get(ax.encoder.pos_estimate)
    target = pos + (args.fraction - pos) % 1.0
    if target - pos > 0.5:
        target -= 1.0
    try:
        b.set(ax.requested_state, AxisState.CLOSED_LOOP_CONTROL)
        t0 = time.monotonic()
        while b.get(ax.current_state) is not AxisState.CLOSED_LOOP_CONTROL:
            if errors() or time.monotonic() - t0 > 3.0:
                print(f"Closed loop not reached: state {b.get(ax.current_state).name}, errors {errors()}")
                return 3
            time.sleep(0.02)
        b.set(ax.controller.input_pos, target)
        time.sleep(0.1)
        t0 = time.monotonic()
        while not b.get(ax.controller.trajectory_done):
            if errors() or time.monotonic() - t0 > 5.0:
                print(f"Move to {target:.4f} failed: errors {errors()}")
                return 3
            time.sleep(0.02)
        time.sleep(0.5)
        reached = b.get(ax.encoder.pos_estimate)
    finally:
        b.set(ax.requested_state, AxisState.IDLE)
    print(f"rotor moved {pos:.4f} -> {reached:.4f} turn (target {target:.4f}); axis IDLE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
