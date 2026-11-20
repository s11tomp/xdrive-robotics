"""docs/cansimple.dbc against the host codecs: the impedance command and a float message encode to the same
bytes, and decode to the same values, through the DBC and through the codec the firmware is tested with."""
import pathlib
import random
import struct
import sys

import cantools
import pytest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import impedance_frame as f  # noqa: E402

DB = cantools.database.load_file(TOOLS.parent / "docs" / "cansimple.dbc")
R = f.Ranges()
NODE = 3


def test_ids_follow_node_and_command():
    assert DB.get_message_by_name(f"Node{NODE}_Impedance").frame_id == f.arbitration_id(NODE)
    assert DB.get_message_by_name(f"Node{NODE}_Heartbeat").frame_id == NODE << 5 | 0x001


@pytest.mark.parametrize("seed", range(200))
def test_impedance_command_matches_codec(seed):
    rnd = random.Random(seed)
    cmd = dict(pos=rnd.uniform(-R.pos, R.pos), vel=rnd.uniform(-R.vel, R.vel), kp=rnd.uniform(0, R.kp),
               kd=rnd.uniform(0, R.kd), torque=rnd.uniform(-R.torque, R.torque))
    raw = f.encode_command(R, **cmd)
    msg = DB.get_message_by_name(f"Node{NODE}_Impedance")
    decoded = msg.decode(raw)
    lsb = dict(pos=R.pos / 32767, vel=R.vel / 2047, kp=R.kp / 4095, kd=R.kd / 4095, torque=R.torque / 2047)
    for k, v in cmd.items():
        assert decoded[f"Imp_{k.capitalize()}"] == pytest.approx(v, abs=lsb[k] / 2 + 1e-9)
    assert msg.encode({f"Imp_{k.capitalize()}": v for k, v in cmd.items()}) == raw


def test_set_input_pos_layout():
    raw = struct.pack("<fhh", 1.25, 500, -250)  # pos float, vel_ff and torque_ff in thousandths
    assert DB.decode_message(f"Node{NODE}_Set_Input_Pos", raw) == pytest.approx(
        {"Input_Pos": 1.25, "Vel_FF": 0.5, "Torque_FF": -0.25})
