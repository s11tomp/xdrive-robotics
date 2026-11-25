#!/usr/bin/env python3
"""Drives one board over CAN with python-can and docs/cansimple.dbc. Motor moves: closed loop, then a
slow +/-0.25 turn sine on input_pos for 10 s, then IDLE.

Needs a configured, calibrated board on the bus (default node ID 0) and a SocketCAN interface (Linux),
set to the board's baud rate (`ip link set can0 up type can bitrate 250000`):
    pip install python-can cantools
    python examples/can_dbc.py --channel can0 --node 0

This example has no bench test against a board; tools/can_test.py is the tested CAN client.
"""
import argparse
import math
import pathlib
import time

import can
import cantools

DB = cantools.database.load_file(pathlib.Path(__file__).resolve().parents[1] / "docs" / "cansimple.dbc")


def send(bus, node, name, **signals):
    msg = DB.get_message_by_name(f"Node{node}_{name}")
    bus.send(can.Message(arbitration_id=msg.frame_id, data=msg.encode(signals), is_extended_id=False))


def heartbeat(bus, node, timeout=1.0):
    frame_id = DB.get_message_by_name(f"Node{node}_Heartbeat").frame_id
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = bus.recv(timeout=deadline - time.monotonic())
        if msg is not None and msg.arbitration_id == frame_id:
            return DB.decode_message(frame_id, msg.data)
    raise TimeoutError(f"no heartbeat from node {node}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--node", type=int, default=0)
    args = ap.parse_args()
    with can.Bus(interface="socketcan", channel=args.channel) as bus:
        print("heartbeat:", heartbeat(bus, args.node))
        send(bus, args.node, "Set_Axis_State", Axis_Requested_State="CLOSED_LOOP_CONTROL")
        time.sleep(0.2)
        state = heartbeat(bus, args.node)
        if str(state["Axis_State"]) != "CLOSED_LOOP_CONTROL":
            raise SystemExit(f"axis did not enter closed loop: {state}")
        try:
            t0 = time.monotonic()
            while time.monotonic() - t0 < 10.0:
                send(bus, args.node, "Set_Input_Pos", Input_Pos=0.25 * math.sin(time.monotonic() - t0),
                     Vel_FF=0.0, Torque_FF=0.0)
                time.sleep(0.01)
        finally:
            send(bus, args.node, "Set_Axis_State", Axis_Requested_State="IDLE")
        print("heartbeat:", heartbeat(bus, args.node))


if __name__ == "__main__":
    main()
