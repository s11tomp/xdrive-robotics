"""The host codec (impedance_frame.py) against the firmware's impedance_frame.hpp, compiled with clang++.

Run from the repo root: python -m pytest -q tools/tests
"""
import math
import pathlib
import random
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import impedance_frame as f  # noqa: E402

FIRMWARE = HERE.parents[1] / "src"
R = f.Ranges()


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    exe = tmp_path_factory.mktemp("cli") / "impedance_frame_cli"
    subprocess.run(["clang++", "-std=c++17", "-O1", "-I", str(FIRMWARE), str(HERE / "impedance_frame_cli.cpp"),
                    "-o", str(exe)], check=True)
    return exe


def run(cli, lines):
    out = subprocess.run([str(cli)], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True)
    return out.stdout.split("\n")[:len(lines)]


def ranges_args(r):
    return f"{r.pos} {r.vel} {r.kp} {r.kd} {r.torque}"


def test_command_known_bytes():
    assert f.encode_command(R, 0.0) == bytes(8)
    full = f.encode_command(R, R.pos, R.vel, R.kp, R.kd, R.torque)
    assert full == bytes([0x7F, 0xFF, 0x7F, 0xFF, 0xFF, 0xFF, 0xF7, 0xFF])
    neg = f.encode_command(R, -R.pos, -R.vel, 0, 0, -R.torque)
    assert neg == bytes([0x80, 0x01, 0x80, 0x10, 0x00, 0x00, 0x08, 0x01])


def test_saturation_and_nan():
    assert f.encode_command(R, 1e9, -1e9, 1e9, -5, math.nan) == f.encode_command(R, R.pos, -R.vel, R.kp, 0, 0)
    assert f.to_signed(1.0, 0.0, 12) == 0


def test_python_round_trip_resolution():
    rnd = random.Random(1)
    for _ in range(2000):
        vals = (rnd.uniform(-R.pos, R.pos), rnd.uniform(-R.vel, R.vel), rnd.uniform(0, R.kp),
                rnd.uniform(0, R.kd), rnd.uniform(-R.torque, R.torque))
        b = f.encode_command(R, *vals)
        p = b[0] << 8 | b[1]
        assert abs(f.from_signed(p, R.pos, 16) - vals[0]) <= R.pos / 32767 / 2 + 1e-9


def test_firmware_decodes_host_commands(cli):
    rnd = random.Random(2)
    ranges = [R, f.Ranges(pos=3.5, vel=10, kp=500, kd=5, torque=1.6)]
    cases, lines = [], []
    for r in ranges:
        for _ in range(500):
            vals = (rnd.uniform(-1.2, 1.2) * r.pos, rnd.uniform(-1.2, 1.2) * r.vel, rnd.uniform(-0.1, 1.2) * r.kp,
                    rnd.uniform(-0.1, 1.2) * r.kd, rnd.uniform(-1.2, 1.2) * r.torque)
            b = f.encode_command(r, *vals)
            cases.append((r, b))
            lines.append(f"cmd {b.hex()} {ranges_args(r)}")
    for (r, b), out in zip(cases, run(cli, lines)):
        got = [float(x) for x in out.split()]
        p, v = b[0] << 8 | b[1], b[2] << 4 | b[3] >> 4
        k, d, t = (b[3] & 0xF) << 8 | b[4], b[5] << 4 | b[6] >> 4, (b[6] & 0xF) << 8 | b[7]
        want = [f.from_signed(p, r.pos, 16), f.from_signed(v, r.vel, 12), f.from_unsigned(k, r.kp, 12),
                f.from_unsigned(d, r.kd, 12), f.from_signed(t, r.torque, 12)]
        assert got == pytest.approx(want, rel=1e-6, abs=1e-6)


def test_host_decodes_firmware_replies(cli):
    rnd = random.Random(3)
    cases, lines = [], []
    for _ in range(1000):
        pos, vel, torque = rnd.uniform(-20, 20), rnd.uniform(-40, 40), rnd.uniform(-5, 5)
        flags, temp, vbus = rnd.randrange(8), rnd.uniform(-10, 300), rnd.uniform(-1, 70)
        cases.append((pos, vel, torque, flags, temp, vbus))
        lines.append(f"reply {ranges_args(R)} {pos} {vel} {torque} {flags} {temp} {vbus}")
    for (pos, vel, torque, flags, temp, vbus), out in zip(cases, run(cli, lines)):
        r = f.decode_reply(R, bytes.fromhex(out))
        assert r.pos == pytest.approx(max(-R.pos, min(R.pos, pos)), abs=R.pos / 32767 / 2 + 1e-6)
        assert r.vel == pytest.approx(max(-R.vel, min(R.vel, vel)), abs=R.vel / 2047 / 2 + 1e-6)
        assert r.torque == pytest.approx(max(-R.torque, min(R.torque, torque)), abs=R.torque / 2047 / 2 + 1e-6)
        assert (r.armed, r.error, r.timeout) == (bool(flags & 1), bool(flags & 2), bool(flags & 4))
        assert r.fet_temp == max(0, min(255, round(temp)))
        assert r.vbus == pytest.approx(max(0, min(63.75, vbus)), abs=0.125 + 1e-6)
