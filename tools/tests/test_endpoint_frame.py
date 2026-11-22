"""The host codec (xdrive/endpoint_frame.py) against the firmware's endpoint_frame.hpp, compiled with clang++
and run against the fake endpoint table in endpoint_frame_cli.cpp.

Run from the repo root: python -m pytest -q tools/tests
"""
import math
import pathlib
import random
import struct
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from xdrive import endpoint_frame as f  # noqa: E402

FIRMWARE = HERE.parents[1] / "src"
S = f.Status


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    exe = tmp_path_factory.mktemp("cli") / "endpoint_frame_cli"
    subprocess.run(["clang++", "-std=c++17", "-O1", "-Wall", "-Werror", "-I", str(FIRMWARE),
                    str(HERE / "endpoint_frame_cli.cpp"), "-o", str(exe)], check=True)
    return exe


def run(cli, frames):
    """Sends the frames in order to one fake board; returns (Reply, call count) per frame."""
    out = subprocess.run([str(cli)], input="".join(bytes(fr).hex() + "\n" for fr in frames),
                         capture_output=True, text=True, check=True)
    results = []
    for line in out.stdout.splitlines():
        rep, calls = line.split()
        results.append((f.decode_reply(bytes.fromhex(rep)), int(calls)))
    assert len(results) == len(frames)
    return results


def one(cli, frame):
    return run(cli, [frame])[0][0]


def test_request_layout():
    assert f.write_request(0x1234, "float", 1.0) == bytes([2, 0x34, 0x12, 0]) + struct.pack("<f", 1.0)
    assert f.read_buffer_request(0, 0x01020304) == bytes([4, 0, 0, 0, 4, 3, 2, 1])
    assert f.write_request(5, "uint8", 200) == bytes([2, 5, 0, 0, 200, 0, 0, 0])
    with pytest.raises(struct.error):
        f.pack("uint8", 300)
    with pytest.raises(KeyError):
        f.pack("uint64", 1)


def test_read_echoes_and_pads(cli):
    r = one(cli, f.read_request(11))
    assert (r.op, r.endpoint_id, r.status, r.data) == (f.Op.READ, 11, S.OK, bytes([7, 0, 0, 0]))
    assert f.unpack("float", one(cli, f.read_request(10)).data) == 1.5


def test_write_then_read_back(cli):
    rnd = random.Random(1)
    values = [rnd.uniform(-1e6, 1e6) for _ in range(200)] + [0.0, -0.0, math.inf]
    frames = [fr for v in values for fr in (f.write_request(10, "float", v), f.read_request(10))]
    results = run(cli, frames)
    for v, (w, _), (r, _) in zip(values, results[0::2], results[1::2]):
        want = struct.unpack("<f", struct.pack("<f", v))[0]
        assert (w.status, r.status) == (S.OK, S.OK)
        assert f.unpack("float", w.data) == want == f.unpack("float", r.data)


def test_write_reply_is_the_value_after_the_write(cli):
    # Endpoint 16 clamps to 1000, as a property with a setter can: the reply shows what was stored.
    (w, _), (r, _) = run(cli, [f.write_request(16, "uint16", 4000), f.read_request(16)])
    assert w.status == S.OK and f.unpack("uint16", w.data) == 1000 == f.unpack("uint16", r.data)


def test_bool_round_trip(cli):
    results = run(cli, [f.write_request(12, "bool", True), f.read_request(12), f.write_request(12, "bool", False)])
    assert [f.unpack("bool", r.data) for r, _ in results] == [True, True, False]


def test_write_rejects_padding_past_the_property(cli):
    # A uint16 write carrying 3 value bytes (a host that packed the wrong type) changes nothing.
    (w, _), (r, _) = run(cli, [f.request(f.Op.WRITE, 16, bytes([1, 0, 1, 0])), f.read_request(16)])
    assert (w.status, w.data) == (S.BAD_VALUE, bytes(4))
    assert f.unpack("uint16", r.data) == 0


def test_kinds_are_enforced(cli):
    cases = [
        (f.read_request(14), S.WRONG_KIND),           # read of a function
        (f.write_request(14, "uint32", 1), S.WRONG_KIND),
        (f.call_request(10), S.WRONG_KIND),           # call of a property
        (f.write_request(11, "uint8", 1), S.WRONG_KIND),  # write of a read-only property
        (f.read_buffer_request(10, 0), S.WRONG_KIND),
        (f.read_request(0), S.WRONG_KIND),            # the JSON is a buffer
        (f.read_request(99), S.UNKNOWN_ENDPOINT),
        (f.call_request(99), S.UNKNOWN_ENDPOINT),
        (f.read_request(13), S.UNSUPPORTED_TYPE),     # uint64
        (f.write_request(17, "int32", 3), S.FAILED),  # the handler refused the write
        (f.call_request(15), S.FAILED),
        (f.read_buffer_request(f.CAPTURE_READOUT, 0), S.FAILED),
        (f.request(9, 10), S.BAD_OPCODE),
        (f.request(0, 10), S.BAD_OPCODE),
    ]
    results = run(cli, [fr for fr, _ in cases])
    for (frame, want), (r, calls) in zip(cases, results):
        assert (r.status, r.data, r.endpoint_id) == (want, bytes(4), struct.unpack_from("<H", frame, 1)[0]), frame.hex()
        assert calls == 0  # no request above runs function 14


def test_call_runs_the_function_once(cli):
    results = run(cli, [f.call_request(14), f.read_request(14), f.call_request(14)])
    assert [(r.status, calls) for r, calls in results] == [(S.OK, 1), (S.WRONG_KIND, 1), (S.OK, 2)]


def test_bad_length(cli):
    out = subprocess.run([str(cli)], input="010a0000\n\n" + f.read_request(11).hex() + "00\n",
                         capture_output=True, text=True, check=True).stdout.split("\n")
    for line in out[:3]:
        assert line.split()[0] == "0000000700000000"


def test_read_json_and_version(cli):
    frames = [f.read_buffer_request(0, o) for o in (0, 4, 8)] + [f.read_buffer_request(0, f.JSON_VERSION_OFFSET)]
    results = run(cli, frames)
    assert all(r.status == S.OK for r, _ in results)
    text = b"".join(r.data for r, _ in results[:3])
    assert text.rstrip(b"\0") == b'{"a":1}' and text.endswith(b"\0")
    assert struct.unpack("<I", results[3][0].data)[0] == 0x12345678


def test_decode_reply_rejects_requests():
    with pytest.raises(ValueError):
        f.decode_reply(f.read_request(10))
    with pytest.raises(ValueError):
        f.decode_reply(bytes(7))
