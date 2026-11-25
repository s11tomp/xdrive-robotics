#!/usr/bin/env python3
"""Reboot the board and watch the startup sequence.  *** THE MOTOR MAY MOVE ***
(saved startup flags run encoder offset calibration and enter closed loop).

Prints each axis0 state transition until it settles (closed loop, or idle with an
error), then the offset-calibration result vs the expected scan, and decoded errors.
Logged to logs/actions.jsonl.

Usage:  python tools/reboot_watch.py [--timeout 40]
"""
import argparse
import datetime
import math
import sys
import time

from logfiles import log_action
from xdrive import report, usb
from xdrive.enums import AxisState
from xdrive.errors import LinkError
from xdrive.props import odrv



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=40.0)
    args = ap.parse_args()

    try:
        b = usb.connect()
    except LinkError as ex:
        print(ex)
        return 1
    serial = format(b.get(odrv.serial_number), "X")
    t_req = datetime.datetime.now().astimezone()
    t0 = time.monotonic()
    b.reboot()          # returns once the board answers again, with a reset uptime
    print(f"reconnected after {time.monotonic() - t0:.1f} s")

    ax, last, transitions = odrv.axis0, None, []
    while time.monotonic() - t0 < args.timeout:
        s = b.get(ax.current_state)
        if s != last:
            transitions.append((round(time.monotonic() - t0, 2), s.name))
            print(f"  t={transitions[-1][0]:5.2f}s  {transitions[-1][1]}")
            last = s
        if s is AxisState.CLOSED_LOOP_CONTROL or (s is AxisState.IDLE and b.get(ax.error)):
            break
        time.sleep(0.05)

    enc, ec = ax.encoder, ax.encoder.config
    pp, cpr, dist = b.get(ax.motor.config.pole_pairs), b.get(ec.cpr), b.get(ec.calib_scan_distance)
    expected = dist / (pp * 2 * math.pi / cpr)
    resp = b.get(enc.calib_scan_response)
    errs = report.errors(b)
    mismatch, calib_range = (resp - expected) / expected, b.get(ec.calib_range)
    kt, bw = b.get(ax.motor.config.torque_constant), b.get(ec.bandwidth)
    vel_limit, trap_vel = b.get(ax.controller.config.vel_limit), b.get(ax.trap_traj.config.vel_limit)
    result = {
        "transitions": transitions,
        "calib_scan_response": resp,
        "expected": round(expected, 1),
        "mismatch": round(mismatch, 4),
        "calib_range": calib_range,
        "encoder_bandwidth": bw,
        "torque_constant": kt,
        "vel_limit": vel_limit,
        "trap_vel_limit": trap_vel,
        "errors": {k: report.jsonable(v) for k, v in errs.items()},
    }
    b.close()
    print(f"offset calibration: scan response {resp:.0f} vs expected {expected:.0f} counts "
          f"({mismatch * 100:+.1f} %, allowed ±{calib_range * 100:.0f} %)")
    print(f"live config: torque_constant {kt:.4f}, encoder bandwidth {bw:.0f}, vel_limit {vel_limit:.1f}, "
          f"trap vel {trap_vel:.1f}")
    for k, v in errs.items():
        print(f"  {k:10s} {report.line(v)}")
    log_action({"t": t_req.isoformat(), "action": "reboot", "serial": serial, **result})
    return 0 if last is AxisState.CLOSED_LOOP_CONTROL else 2


if __name__ == "__main__":
    sys.exit(main())
