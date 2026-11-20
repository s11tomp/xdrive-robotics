#!/usr/bin/env python3
"""Writes docs/cansimple.dbc: the CANSimple protocol as this firmware speaks it, for cantools,
SavvyCAN and other DBC readers.

Each message is defined once per node ID 0 to 7 (Node<n>_<message>, arbitration ID n << 5 | command),
with the layouts of src/communication/can/can_simple.cpp. Error and state values come from
tools/enums_v056.py. The impedance command's scales assume the default axis.config.can.impedance_*
ranges (tools/impedance_frame.py Ranges); the node answers it on the same ID with a reply a DBC
can't also describe (see the message's comment).

Usage: `make generate` (runs this with the repo's .venv).
"""
import pathlib

from cantools.database import dump_file
from cantools.database.can import Bus, Database, Message, Node, Signal
from cantools.database.conversion import BaseConversion

import enums_v056 as e
import impedance_frame

OUTPUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "cansimple.dbc"
NODES = range(8)
HOST = "Host"


def sig(name, start, length, *, receiver, signed=False, is_float=False, scale=1.0, unit=None, choices=None,
        big_endian=False):
    conversion = BaseConversion.factory(scale=scale, choices=choices, is_float=is_float)
    return Signal(name, start, length, byte_order="big_endian" if big_endian else "little_endian",
                  is_signed=signed, conversion=conversion, unit=unit, receivers=[receiver])


def f32(name, start, receiver, unit=None):
    return sig(name, start, 32, receiver=receiver, signed=True, is_float=True, unit=unit)


def names(enum_type):
    return {m.value: m.name for m in enum_type}


def node_messages(node):
    """(command ID, name, length, signals, sender, comment) for one node."""
    n = f"Node{node}"
    r = impedance_frame.Ranges()
    return [
        (0x001, "Heartbeat", 8, [
            sig("Axis_Error", 0, 32, receiver=HOST, choices=names(e.AxisError)),
            sig("Axis_State", 32, 8, receiver=HOST, choices=names(e.AxisState)),
            sig("Motor_Error_Flag", 40, 1, receiver=HOST),
            sig("Encoder_Error_Flag", 48, 1, receiver=HOST),
            sig("Controller_Error_Flag", 56, 1, receiver=HOST),
            sig("Trajectory_Done_Flag", 63, 1, receiver=HOST)], n, None),
        (0x002, "Estop", 0, [], HOST, None),
        (0x003, "Get_Motor_Error", 8, [sig("Motor_Error", 0, 64, receiver=HOST, choices=names(e.MotorError))], n, None),
        (0x004, "Get_Encoder_Error", 8,
         [sig("Encoder_Error", 0, 32, receiver=HOST, choices=names(e.EncoderError))], n, None),
        (0x005, "Get_Sensorless_Error", 8,
         [sig("Sensorless_Error", 0, 32, receiver=HOST, choices=names(e.SensorlessEstimatorError))], n, None),
        (0x006, "Set_Axis_Node_ID", 8, [sig("Axis_Node_ID", 0, 32, receiver=n)], HOST, None),
        (0x007, "Set_Axis_State", 8,
         [sig("Axis_Requested_State", 0, 32, receiver=n, choices=names(e.AxisState))], HOST, None),
        (0x009, "Get_Encoder_Estimates", 8,
         [f32("Pos_Estimate", 0, HOST, "turn"), f32("Vel_Estimate", 32, HOST, "turn/s")], n, None),
        (0x00A, "Get_Encoder_Count", 8, [
            sig("Shadow_Count", 0, 32, receiver=HOST, signed=True, unit="counts"),
            sig("Count_In_CPR", 32, 32, receiver=HOST, signed=True, unit="counts")], n, None),
        (0x00B, "Set_Controller_Mode", 8, [
            sig("Control_Mode", 0, 32, receiver=n, choices=names(e.ControlMode)),
            sig("Input_Mode", 32, 32, receiver=n, choices=names(e.InputMode))], HOST, None),
        (0x00C, "Set_Input_Pos", 8, [
            f32("Input_Pos", 0, n, "turn"),
            sig("Vel_FF", 32, 16, receiver=n, signed=True, scale=0.001, unit="turn/s"),
            sig("Torque_FF", 48, 16, receiver=n, signed=True, scale=0.001, unit="Nm")], HOST, None),
        (0x00D, "Set_Input_Vel", 8, [f32("Input_Vel", 0, n, "turn/s"), f32("Input_Torque_FF", 32, n, "Nm")], HOST, None),
        (0x00E, "Set_Input_Torque", 8, [f32("Input_Torque", 0, n, "Nm")], HOST, None),
        (0x00F, "Set_Limits", 8, [f32("Velocity_Limit", 0, n, "turn/s"), f32("Current_Limit", 32, n, "A")], HOST, None),
        (0x010, "Start_Anticogging", 0, [], HOST, None),
        (0x011, "Set_Traj_Vel_Limit", 8, [f32("Traj_Vel_Limit", 0, n, "turn/s")], HOST, None),
        (0x012, "Set_Traj_Accel_Limits", 8,
         [f32("Traj_Accel_Limit", 0, n, "turn/s^2"), f32("Traj_Decel_Limit", 32, n, "turn/s^2")], HOST, None),
        (0x013, "Set_Traj_Inertia", 8, [f32("Traj_Inertia", 0, n, "Nm/(turn/s^2)")], HOST, None),
        (0x014, "Get_Iq", 8, [f32("Iq_Setpoint", 0, HOST, "A"), f32("Iq_Measured", 32, HOST, "A")], n, None),
        (0x015, "Get_Sensorless_Estimates", 8,
         [f32("Sensorless_Pos_Estimate", 0, HOST, "turn"), f32("Sensorless_Vel_Estimate", 32, HOST, "turn/s")], n, None),
        (0x016, "Reboot", 0, [], HOST, None),
        (0x017, "Get_Bus_Voltage_Current", 8, [f32("Bus_Voltage", 0, HOST, "V"), f32("Bus_Current", 32, HOST, "A")],
         n, None),
        (0x018, "Clear_Errors", 0, [], HOST, None),
        (0x019, "Set_Linear_Count", 8, [sig("Position", 0, 32, receiver=n, signed=True, unit="counts")], HOST, None),
        (0x01A, "Set_Pos_Gain", 8, [f32("Pos_Gain", 0, n, "(turn/s)/turn")], HOST, None),
        (0x01B, "Set_Vel_Gains", 8,
         [f32("Vel_Gain", 0, n, "Nm/(turn/s)"), f32("Vel_Integrator_Gain", 32, n, "Nm/turn")], HOST, None),
        (0x01C, "Get_ADC_Voltage", 8, [f32("ADC_Voltage", 0, HOST, "V")], n,
         "Reply. The request carries the GPIO number in byte 0."),
        (0x01D, "Get_Controller_Error", 8,
         [sig("Controller_Error", 0, 32, receiver=HOST, choices=names(e.ControllerError))], n, None),
        (impedance_frame.MSG_IMPEDANCE, "Impedance", 8, [
            sig("Imp_Pos", 7, 16, receiver=n, signed=True, scale=r.pos / 32767, unit="turn", big_endian=True),
            sig("Imp_Vel", 23, 12, receiver=n, signed=True, scale=r.vel / 2047, unit="turn/s", big_endian=True),
            sig("Imp_Kp", 27, 12, receiver=n, scale=r.kp / 4095, unit="Nm/turn", big_endian=True),
            sig("Imp_Kd", 47, 12, receiver=n, scale=r.kd / 4095, unit="Nm/(turn/s)", big_endian=True),
            sig("Imp_Torque", 51, 12, receiver=n, signed=True, scale=r.torque / 2047, unit="Nm", big_endian=True)],
         HOST,
         "Impedance command, with scales for the default axis.config.can.impedance_* ranges. The node answers "
         "on the same ID: pos 16 | vel 12 | torque 12 | flags 8 | FET temperature 8 (degC) | bus voltage 8 "
         "(0.25 V), big-endian; tools/impedance_frame.py decodes it."),
    ]


def database():
    messages = []
    for node in NODES:
        for cmd, name, length, signals, sender, comment in node_messages(node):
            messages.append(Message(node << 5 | cmd, f"Node{node}_{name}", length, signals, senders=[sender],
                                    comment=comment))
    nodes = [Node(HOST)] + [Node(f"Node{node}") for node in NODES]
    return Database(messages, nodes, [Bus("CAN", baudrate=250000)])


def main():
    dump_file(database(), OUTPUT)
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[1])}")


if __name__ == "__main__":
    main()
