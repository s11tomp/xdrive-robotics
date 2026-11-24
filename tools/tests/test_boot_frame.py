"""The host codec (xdrive/boot_frame.py) against the bootloader's boot_protocol.hpp, compiled with clang++
and run against the fake flash in boot_protocol_cli.cpp.

Run from the repo root: python -m pytest -q tools/tests
"""
from __future__ import annotations

import pathlib
import random
import struct
import subprocess
import sys
from typing import Sequence

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from xdrive import boot_frame as bf  # noqa: E402

FIRMWARE = HERE.parents[1] / "src"
SERIAL = 0x0123456789AB
S = bf.Status


@pytest.fixture(scope="module")
def cli(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    exe = tmp_path_factory.mktemp("cli") / "boot_protocol_cli"
    subprocess.run(["clang++", "-std=c++17", "-O1", "-Wall", "-Werror", "-I", str(FIRMWARE),
                    str(HERE / "boot_protocol_cli.cpp"), "-o", str(exe)], check=True)
    return exe


def make_image(length: int, seed: int = 1, hw: int = bf.HW_XDRIVE_MINI) -> bytes:
    """A sealed application image: random bytes with a header at HEADER_OFFSET."""
    rng = random.Random(seed)
    image = bytearray(rng.getrandbits(8) for _ in range(length))
    bf.HEADER.pack_into(image, bf.HEADER_OFFSET, bf.IMAGE_MAGIC, bf.HEADER_VERSION, 0, 0, hw, bytes([1, 0, 0, 0]))
    return bf.seal(bytes(image))


def run(cli: pathlib.Path, lines: Sequence[str | tuple[int, bytes]], image: bytes | None = None, node: int = 5,
        requested: bool = False, tmp: pathlib.Path | None = None) -> list[tuple[int, bytes, bool] | None]:
    """Feeds frames (and '!' directives) to one fake board; returns each frame's answer
    (ID, data, start) or None."""
    path = "-"
    if image is not None:
        assert tmp is not None
        (tmp / "image.bin").write_bytes(image)
        path = str(tmp / "image.bin")
    text = "".join((ln if isinstance(ln, str) else f"{ln[0]:08x} {ln[1].hex() or '-'}") + "\n" for ln in lines)
    out = subprocess.run([str(cli), path, str(node), "1" if requested else "0"], input=text,
                         capture_output=True, text=True, check=True)
    answers: list[tuple[int, bytes, bool] | None] = []
    for line in out.stdout.splitlines():
        if line == "-":
            answers.append(None)
        else:
            parts = line.split()
            answers.append((int(parts[0], 16), bytes.fromhex(parts[1]), len(parts) > 2 and parts[2] == "start"))
    assert len(answers) == sum(1 for ln in lines if not isinstance(ln, str))
    return answers


def flash_frames(image: bytes, block: int = bf.BLOCK_MAX) -> list[str | tuple[int, bytes]]:
    frames: list[str | tuple[int, bytes]] = [bf.erase(SERIAL, len(image))]
    for off in range(0, len(image), block):
        frames += bf.block(SERIAL, off, image[off:off + block])
    return frames


def answers_of(answers: list[tuple[int, bytes, bool] | None]) -> list[tuple[int, bytes, bool]]:
    return [a for a in answers if a is not None]


def test_id_layout() -> None:
    assert bf.make_id(False, bf.Cmd.DISCOVER, bf.BROADCAST) == 0x160FFFFF
    assert bf.make_id(True, bf.Cmd.BLOCK_END, SERIAL) == 0x174789AB
    i = bf.parse_id(0x174789AB)
    assert (i.ours, i.from_board, i.cmd, i.serial20) == (True, True, bf.Cmd.BLOCK_END, 0x789AB)
    assert not bf.parse_id(0x07FF).ours            # a CANSimple ID


def test_discover_answers_with_serial_node_and_flags(cli: pathlib.Path) -> None:
    (aid, data, start), = answers_of(run(cli, [bf.discover()], requested=True))
    assert aid == bf.make_id(True, bf.Cmd.DISCOVER, SERIAL) and not start
    d = bf.decode_discover(data)
    assert (d.serial, d.node_id, d.image_valid, d.requested, d.protocol_version) == (SERIAL, 5, False, True, 1)
    (_, data, _), = answers_of(run(cli, [bf.discover(SERIAL)], node=bf.NODE_UNKNOWN))
    assert bf.decode_discover(data).node_id is None


def test_ignores_other_boards_and_its_own_kind(cli: pathlib.Path) -> None:
    other = SERIAL ^ 1
    answers = run(cli, [bf.discover(other), bf.verify(other),
                        (bf.make_id(True, bf.Cmd.DISCOVER, bf.BROADCAST), b""),   # another board's answer
                        (bf.make_id(False, bf.Cmd.VERIFY, bf.BROADCAST), b""),    # only DISCOVER broadcasts
                        (0x0001, bytes(8))])                                     # CANSimple
    assert answers == [None] * 5


def test_full_update_then_start(cli: pathlib.Path) -> None:
    image = make_image(5000)
    answers = run(cli, flash_frames(image) + [bf.verify(SERIAL), bf.discover(SERIAL), bf.start_app(SERIAL)])
    got = answers_of(answers)
    assert bf.status(got[0][1]) is S.OK                                   # erase
    ends = got[1:-3]
    assert [bf.decode_block_end(d) for _, d, _ in ends] == [(S.OK, o) for o in range(0, 5000, 1024)]
    assert bf.decode_verify(got[-3][1]) == (S.OK, 5000)
    assert bf.decode_discover(got[-2][1]).image_valid
    assert bf.status(got[-1][1]) is S.OK and got[-1][2]                   # start


def test_header_checks_match_the_bootloader(cli: pathlib.Path, tmp_path: pathlib.Path) -> None:
    good = make_image(3000)
    assert bf.header_valid(good)
    corrupt = bytearray(good)
    corrupt[2999] ^= 0x40
    wrong_hw = make_image(3000, hw=0x00030624)
    for image, valid in ((good, True), (bytes(corrupt), False), (wrong_hw, False)):
        assert bf.header_valid(image) is valid
        (_, data, _), = answers_of(run(cli, [bf.verify(SERIAL)], image=image, tmp=tmp_path))
        assert bf.decode_verify(data)[0] is (S.OK if valid else S.NO_VALID_IMAGE)


def test_interrupted_update_leaves_no_valid_image_and_a_rerun_completes(cli: pathlib.Path, tmp_path: pathlib.Path) -> None:
    old, new = make_image(4096, seed=1), make_image(6000, seed=2)
    half = flash_frames(new)[:1 + 3 * 130]          # the erase and about three of six blocks
    got = answers_of(run(cli, half + [bf.verify(SERIAL), bf.start_app(SERIAL)], image=old, tmp=tmp_path))
    assert bf.decode_verify(got[-2][1])[0] is S.NO_VALID_IMAGE
    assert bf.status(got[-1][1]) is S.NO_VALID_IMAGE and not got[-1][2]
    got = answers_of(run(cli, half + flash_frames(new) + [bf.verify(SERIAL)], image=old, tmp=tmp_path))
    assert bf.decode_verify(got[-1][1]) == (S.OK, 6000)


def test_block_errors(cli: pathlib.Path) -> None:
    data = bytes(range(64))
    frames = bf.block(SERIAL, 0, data)
    bad_crc = frames[:-1] + [(frames[-1][0], struct.pack("<I", 0))]
    dropped = frames[:3] + frames[4:]                        # one DATA frame lost
    s20 = bf.serial20(SERIAL)
    start = bf.make_id(False, bf.Cmd.BLOCK_START, s20)
    end = bf.make_id(False, bf.Cmd.BLOCK_END, s20)
    cases: list[tuple[Sequence[str | tuple[int, bytes]], S]] = [
        (bad_crc, S.BAD_CRC),
        (dropped, S.BAD_LENGTH),
        ([(start, struct.pack("<II", 2, 8)), (end, bytes(4))], S.BAD_LENGTH),               # misaligned
        ([(start, struct.pack("<II", 0, 2000)), (end, bytes(4))], S.BAD_LENGTH),            # over BLOCK_MAX
        ([(start, struct.pack("<II", bf.APP_SIZE - 4, 8)), (end, bytes(4))], S.OUT_OF_RANGE),
        ([(end, bytes(4))], S.NO_BLOCK),
        ([(start, b"\x00")] + frames[1:], S.BAD_COMMAND),                                  # short BLOCK_START
        (["!fail_program", *frames], S.FLASH_ERROR),
    ]
    for lines, want in cases:
        (_, d, _), = answers_of(run(cli, lines))
        assert bf.decode_block_end(d)[0] is want, (lines, want)
    # Programming over data that isn't erased fails the read-back check.
    got = answers_of(run(cli, frames + bf.block(SERIAL, 0, bytes(64 * [0xA5]))))
    assert [bf.decode_block_end(d)[0] for _, d, _ in got] == [S.OK, S.FLASH_ERROR]


def test_erase_checks(cli: pathlib.Path) -> None:
    got = answers_of(run(cli, [bf.erase(SERIAL, 0), bf.erase(SERIAL, bf.APP_SIZE + 4), "!fail_erase",
                               bf.erase(SERIAL, 100), bf.erase(SERIAL, bf.APP_SIZE),
                               (bf.make_id(False, bf.Cmd.ERASE, bf.serial20(SERIAL)), b"\x01")]))
    assert [bf.status(d) for _, d, _ in got] == [S.OUT_OF_RANGE, S.OUT_OF_RANGE, S.FLASH_ERROR, S.OK, S.BAD_COMMAND]


def test_unknown_command(cli: pathlib.Path) -> None:
    (_, d, _), = answers_of(run(cli, [(bf.make_id(False, 9, bf.serial20(SERIAL)), b"")]))
    assert bf.status(d) is S.BAD_COMMAND
