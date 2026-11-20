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
import json
import math
import pathlib
import sys
import time

import odrive
from odrive.enums import AXIS_STATE_CLOSED_LOOP_CONTROL, AXIS_STATE_IDLE

from dump_board import decode_bitmask, decode_enum, connect

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=40.0)
    args = ap.parse_args()

    dev = connect(timeout=10)
    if dev is None:
        print("No board found on USB.")
        return 1
    serial = format(dev.serial_number, "X")
    t_req = datetime.datetime.now().astimezone()
    try:
        dev.reboot()
    except Exception:
        pass  # USB drops mid-call on reboot; expected
    t0 = time.monotonic()
    time.sleep(1.0)

    dev = connect(serial_number=serial, timeout=15)
    if dev is None:
        print("Board did not come back on USB within 15 s. Check the PSU.")
        return 1
    print(f"reconnected after {time.monotonic() - t0:.1f} s")

    ax, last, transitions = dev.axis0, None, []
    while time.monotonic() - t0 < args.timeout:
        s = ax.current_state
        if s != last:
            transitions.append((round(time.monotonic() - t0, 2), decode_enum(s, "AXIS_STATE_")))
            print(f"  t={transitions[-1][0]:5.2f}s  {transitions[-1][1]}")
            last = s
        if s == AXIS_STATE_CLOSED_LOOP_CONTROL or (s == AXIS_STATE_IDLE and ax.error):
            break
        time.sleep(0.05)

    enc = ax.encoder
    pp, cpr, dist = ax.motor.config.pole_pairs, enc.config.cpr, enc.config.calib_scan_distance
    expected = dist / (pp * 2 * math.pi / cpr)
    resp = enc.calib_scan_response
    result = {
        "transitions": transitions,
        "calib_scan_response": resp,
        "expected": round(expected, 1),
        "mismatch": round((resp - expected) / expected, 4),
        "calib_range": enc.config.calib_range,
        "encoder_bandwidth": enc.config.bandwidth,
        "torque_constant": ax.motor.config.torque_constant,
        "vel_limit": ax.controller.config.vel_limit,
        "trap_vel_limit": ax.trap_traj.config.vel_limit,
        "errors": {
            "axis": decode_bitmask(ax.error, "AXIS_ERROR_"),
            "motor": decode_bitmask(ax.motor.error, "MOTOR_ERROR_"),
            "encoder": decode_bitmask(ax.encoder.error, "ENCODER_ERROR_"),
            "controller": decode_bitmask(ax.controller.error, "CONTROLLER_ERROR_"),
        },
    }
    print(f"offset calibration: scan response {resp:.0f} vs expected {expected:.0f} counts "
          f"({result['mismatch'] * 100:+.1f} %, allowed ±{result['calib_range'] * 100:.0f} %)")
    print(f"live config: torque_constant {result['torque_constant']:.4f}, encoder bandwidth "
          f"{result['encoder_bandwidth']:.0f}, vel_limit {result['vel_limit']:.1f}, trap vel {result['trap_vel_limit']:.1f}")
    for k, d in result["errors"].items():
        print(f"  {k:10s} {d['hex']} {' | '.join(d['flags'])}")
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": t_req.isoformat(), "action": "reboot", "serial": serial, **result}) + "\n")
    return 0 if last == AXIS_STATE_CLOSED_LOOP_CONTROL else 2


if __name__ == "__main__":
    sys.exit(main())
