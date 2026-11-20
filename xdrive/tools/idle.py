#!/usr/bin/env python3
"""Put axis0 into AXIS_STATE_IDLE (motor goes limp; PWM off) and report state + errors.

This is the "stop" command: it never moves the motor. It does not clear errors
or save anything. Each call is appended to logs/actions.jsonl.

Usage:  python xdrive/tools/idle.py
"""
import datetime
import json
import pathlib
import sys
import time

import odrive
from odrive.enums import AXIS_STATE_IDLE

from dump_board import decode_bitmask, decode_enum, connect

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"


def main():
    dev = connect(timeout=10)
    if dev is None:
        print("No board found on USB. To stop the motor, press OUT on the PSU.")
        return 1
    ax = dev.axis0
    before = ax.current_state
    ax.requested_state = AXIS_STATE_IDLE
    time.sleep(0.2)
    after = ax.current_state
    errs = {
        "axis": decode_bitmask(ax.error, "AXIS_ERROR_"),
        "motor": decode_bitmask(ax.motor.error, "MOTOR_ERROR_"),
        "encoder": decode_bitmask(ax.encoder.error, "ENCODER_ERROR_"),
        "controller": decode_bitmask(ax.controller.error, "CONTROLLER_ERROR_"),
    }
    print(f"state {decode_enum(before, 'AXIS_STATE_')} -> {decode_enum(after, 'AXIS_STATE_')}")
    for k, d in errs.items():
        print(f"  {k:10s} {d['hex']} {' | '.join(d['flags'])}")
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": datetime.datetime.now().astimezone().isoformat(), "action": "idle",
                            "serial": format(dev.serial_number, "X"), "state_before": before,
                            "state_after": after, "errors": errs}) + "\n")
    return 0 if after == AXIS_STATE_IDLE else 2


if __name__ == "__main__":
    sys.exit(main())
