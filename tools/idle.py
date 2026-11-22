#!/usr/bin/env python3
"""Put axis0 into AXIS_STATE_IDLE (motor goes limp; PWM off) and report state + errors.

This is the "stop" command: it never moves the motor. It does not clear errors
or save anything. Each call is appended to logs/actions.jsonl.

Usage:  python tools/idle.py
"""
import datetime
import json
import pathlib
import sys
import time

from xdrive import report, usb
from xdrive.enums import AxisState
from xdrive.errors import LinkError
from xdrive.props import odrv

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"


def main() -> int:
    try:
        board = usb.connect()
    except LinkError as ex:
        print(f"{ex}. To stop the motor, press OUT on the PSU.")
        return 1
    with board:
        ax = odrv.axis0
        before = board.get(ax.current_state)
        board.set(ax.requested_state, AxisState.IDLE)
        time.sleep(0.2)
        after = board.get(ax.current_state)
        errs = report.errors(board)
        serial = format(board.get(odrv.serial_number), "X")
    print(f"state {before.name} -> {after.name}")
    for k, v in errs.items():
        print(f"  {k:10s} {report.line(v)}")
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps({"t": datetime.datetime.now().astimezone().isoformat(), "action": "idle",
                            "serial": serial, "state_before": before.value, "state_after": after.value,
                            "errors": {k: report.jsonable(v) for k, v in errs.items()}}) + "\n")
    return 0 if after is AxisState.IDLE else 2


if __name__ == "__main__":
    sys.exit(main())
