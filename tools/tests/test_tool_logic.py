"""The host tools' logic that runs without a board, and their bench helpers against a fake board: the log files
(logfiles), value parsing (set_config), the config backup (dump_board), the correction table's harmonics, the
move logs as written (move_test.Recorder) and read back (analyze_settle), the capture readout, the bench tests'
end-of-run restore and report (safety_test.Bench), flash sector bookkeeping (swd_flash) and Intel HEX output
(seal_image).
"""
from __future__ import annotations

import datetime
import json
import math
import pathlib
import struct
import sys
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from test_can_test import BenchLink  # noqa: E402
from test_xdrive import FakeLink, cache, json_bytes  # noqa: E402,F401  (fixtures)

import analyze_settle  # noqa: E402
import capture  # noqa: E402
import correction_table  # noqa: E402
import dump_board  # noqa: E402
import logfiles  # noqa: E402
import move_test  # noqa: E402
import safety_test  # noqa: E402
import seal_image  # noqa: E402
import set_config  # noqa: E402
import swd_flash  # noqa: E402
from xdrive import paths  # noqa: E402
from xdrive.board import Board  # noqa: E402
from xdrive.enums import AxisState, ControlMode  # noqa: E402
from xdrive.errors import LinkLost  # noqa: E402

STAMP = datetime.datetime(2026, 1, 2, 3, 4, 5).astimezone()


# --- logfiles ------------------------------------------------------------------------------------
def test_log_action_creates_logs_and_appends(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    logfiles.log_action({"action": "a", "n": 1})
    logfiles.log_action({"action": "b"})
    lines = (tmp_path / "logs" / "actions.jsonl").read_text().splitlines()
    assert [json.loads(line)["action"] for line in lines] == ["a", "b"]
    assert logfiles.rel(tmp_path / "logs" / "x.csv") == "logs/x.csv"


def test_read_columns_skips_metadata_and_keeps_text(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "log.csv"
    path.write_text("# host_start,2026,serial,1\nt,flag,x,event\n0.0,True,1.5,hold\n0.1,False,-2,\n")
    d = logfiles.read_columns(path)
    assert d["t"].tolist() == [0.0, 0.1] and d["flag"].tolist() == [1.0, 0.0] and d["x"].tolist() == [1.5, -2.0]
    assert d["event"].tolist() == ["hold", ""]


# --- set_config ----------------------------------------------------------------------------------
def test_set_config_parses_text_and_json_by_the_property_type() -> None:
    def parse(path: str, value: Any) -> Any:
        return set_config.parse(paths.prop(path), value)

    assert parse("axis0.config.enable_watchdog", "true") is True
    assert parse("axis0.config.enable_watchdog", "1") is True
    assert parse("axis0.config.enable_watchdog", "0") is False
    assert parse("axis0.config.enable_watchdog", 1) is True                 # JSON number for a bool
    assert parse("axis0.controller.config.control_mode", "POSITION_CONTROL") is ControlMode.POSITION_CONTROL
    assert parse("axis0.controller.config.control_mode", "3") is ControlMode.POSITION_CONTROL
    assert parse("axis0.controller.config.control_mode", 3) is ControlMode.POSITION_CONTROL  # JSON number
    assert parse("axis0.config.can.node_id", "3.0") == 3
    assert parse("axis0.controller.config.vel_limit", "8") == 8.0
    assert parse("axis0.controller.config.vel_limit", 8) == 8.0 and isinstance(parse("axis0.controller.config.vel_limit", 8), float)
    with pytest.raises(ValueError):
        parse("axis0.config.enable_watchdog", "yes")


# --- dump_board ----------------------------------------------------------------------------------
def test_config_backup_keeps_only_writable_config() -> None:
    values = {"axis0.config.can.node_id": 1, "axis0.motor.config.pole_pairs": 21, "can.config.baud_rate": 250000,
              "axis0.encoder.pos_estimate": 0.5, "config.gpio3_analog_mapping.endpoint": [0, 0],
              "axis0.config.enable_watchdog": False}
    access = {"axis0.config.can.node_id": "rw", "axis0.motor.config.pole_pairs": "rw", "can.config.baud_rate": "r",
              "axis0.encoder.pos_estimate": "r", "config.gpio3_analog_mapping.endpoint": "rw",
              "axis0.config.enable_watchdog": "rw"}
    assert dump_board.config_only(values, access) == {
        "axis0": {"config": {"can": {"node_id": 1}, "enable_watchdog": False}, "motor": {"config": {"pole_pairs": 21}}}}


# --- correction_table ----------------------------------------------------------------------------
def test_harmonics_and_smoothing_separate_low_and_high_orders() -> None:
    n = correction_table.N
    angle = [2 * math.pi * (k + 0.5) / n for k in range(n)]
    low = [10.0 * math.cos(2 * a) + 4.0 * math.sin(5 * a) for a in angle]
    table = [v + 3.0 * math.cos(36 * a) for v, a in zip(low, angle)]
    h = {k: (c, s) for k, c, s in correction_table.harmonics(table, 40)}
    assert h[2] == pytest.approx((10.0, 0.0), abs=1e-9) and h[5] == pytest.approx((0.0, 4.0), abs=1e-9)
    assert h[36] == pytest.approx((3.0, 0.0), abs=1e-9) and math.hypot(*h[3]) < 1e-9
    assert correction_table.smooth(table, 12) == pytest.approx(low, abs=1e-9)


# --- move_test.Recorder and analyze_settle -------------------------------------------------------
@pytest.fixture
def bench_board(json_bytes: bytes) -> Board:  # noqa: F811
    return Board(BenchLink(json_bytes))


def test_recorder_enters_closed_loop_or_aborts(json_bytes: bytes, bench_board: Board) -> None:  # noqa: F811
    rec = move_test.Recorder(bench_board)
    rec.enter_closed_loop()
    assert rec.expect_closed_loop and rec.rows[-1][1 + move_test.IX["axis0.current_state"]] == 8

    stuck = Board(FakeLink(json_bytes))  # requested_state never reaches current_state
    rec = move_test.Recorder(stuck)
    with pytest.raises(move_test.Abort, match="did not enter closed loop"):
        rec.enter_closed_loop()
    assert not rec.expect_closed_loop


def move_rows(start: float, target: float, overshoot: float) -> list[list[Any]]:
    """A move_test row stream: a hold, then a move to target that overshoots by `overshoot` turn and settles."""
    ix = move_test.IX
    rows = []
    for k in range(60):
        t = k * 0.01
        if k < 20:          # trajectory running
            pos, done = start + (target - start) * k / 20, False
        elif k < 30:        # done, past the target
            pos, done = target + overshoot, True
        else:               # settled
            pos, done = target, True
        values: list[Any] = [0] * len(move_test.FIELDS)
        values[ix["axis0.encoder.pos_estimate"]] = pos
        values[ix["axis0.controller.input_pos"]] = target
        values[ix["axis0.controller.trajectory_done"]] = done
        values[ix["axis0.current_state"]] = 8
        rows.append([t] + values + ["out +1" if k == 0 else ""])
    return rows


def test_move_log_round_trip_through_analyze_settle(bench_board: Board, tmp_path: pathlib.Path) -> None:
    rec = move_test.Recorder(bench_board)
    hold: list[Any] = [0.0] + [0] * len(move_test.FIELDS) + ["hold"]
    rec.rows = [hold] + move_rows(0.0, 1.0, 20 / 16384)
    path = tmp_path / "move.csv"
    rec.write_csv(path, STAMP, "ABC", "move_test.py")
    assert path.read_text().splitlines()[0].startswith("# host_start,")

    (name, d), = analyze_settle.load(path)        # the hold segment is left out
    assert name == "out +1" and len(d["t"]) == 60
    m = analyze_settle.metrics(d, band=10.0)
    assert m["overshoot"] == pytest.approx(20.0)
    assert m["settle_s"] == pytest.approx(0.10)      # 10 samples past the band after trajectory_done
    assert m["residual"] == pytest.approx(0.0)


def test_trap_time_trapezoid_and_triangle() -> None:
    assert move_test.trap_time(1.0, 2.0, 10.0, 10.0) == pytest.approx(0.7)   # cruises at 2 turn/s
    assert move_test.trap_time(0.1, 2.0, 10.0, 10.0) == pytest.approx(0.2)   # peaks at 1 turn/s


# --- capture -------------------------------------------------------------------------------------
class CaptureLink(FakeLink):
    """FakeLink with a capture readout buffer behind capture.readout_endpoint."""

    def __init__(self, json_bytes: bytes, words: np.ndarray) -> None:
        super().__init__(json_bytes)
        self.buffer = words.astype("<u4").tobytes()
        self.put("capture.readout_endpoint", 0x7F00)

    def read_buffer(self, endpoint_id: int, offset: int) -> bytes:
        if endpoint_id != 0x7F00:
            return super().read_buffer(endpoint_id, offset)
        return self.buffer[offset:offset + 61]


@pytest.mark.parametrize("window", [None, (2, 3)])
def test_capture_read_decodes_channels_and_times_them_from_the_trigger(json_bytes: bytes,  # noqa: F811
                                                                       window: tuple[int, int] | None) -> None:
    n, trig = 10, 4
    f32 = np.arange(n, dtype=np.float32) * 0.5 - 1.0
    i32 = np.arange(n, dtype=np.int32) - 5
    u32 = np.arange(n, dtype=np.uint32) + 3_000_000_000
    words = np.column_stack([f32.view(np.uint32), i32.view(np.uint32), u32])
    link = CaptureLink(json_bytes, words)
    for name, value in (("capture.n_samples", n), ("capture.n_channels", 3), ("capture.decimation", 4),
                        ("capture.trigger_index", trig)):
        link.put(name, value)
    fields = ["vbus_voltage", "axis0.encoder.shadow_count", "n_evt_control_loop"]
    t, data, meta = capture.read(Board(link), fields, ["float", "int32", "uint32"], window)
    lo, hi = (0, n) if window is None else (trig - window[0], trig + window[1] + 1)
    assert data["vbus_voltage"].tolist() == f32[lo:hi].tolist()
    assert data["axis0.encoder.shadow_count"].tolist() == i32[lo:hi].tolist()
    assert data["n_evt_control_loop"].tolist() == u32[lo:hi].tolist()
    assert t.tolist() == pytest.approx([(k - trig) * 4 / 8000 for k in range(lo, hi)])
    assert meta["period_s"] == pytest.approx(4 / 8000) and meta["trigger_index"] == trig


def test_capture_trigger_syntax() -> None:
    assert capture.parse_trigger("axis0.motor.I_bus > 1.5") == ("axis0.motor.I_bus", capture.RISING, 1.5)
    assert capture.parse_trigger("vbus_voltage<-2") == ("vbus_voltage", capture.FALLING, -2.0)
    with pytest.raises(Exception, match="trigger must look like"):
        capture.parse_trigger("vbus_voltage=3")


# --- safety_test.Bench: the end of every bench test ----------------------------------------------
def test_bench_restore_and_report(json_bytes: bytes, tmp_path: pathlib.Path,  # noqa: F811
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    link = BenchLink(json_bytes)
    b = safety_test.Bench(Board(link), "20260102-030405", "ABC", prefix="unit")
    saved = {"axis0.controller.config.vel_limit": 8.0, "axis0.config.watchdog_timeout": 1.5}
    b.set("axis0.requested_state", int(AxisState.CLOSED_LOOP_CONTROL.value))
    b.set("axis0.config.enable_watchdog", True)
    b.set("axis0.controller.config.vel_limit", 20.0)
    b.sample()
    order: list[str] = []
    logs: list[str] = []
    b.restore(saved, logs, cleanup=lambda: order.append(f"cleanup, vel_limit {b.get('axis0.controller.config.vel_limit')}"))
    assert link.value("axis0.current_state") == 1 and not link.value("axis0.config.enable_watchdog")
    assert link.value("axis0.controller.config.vel_limit") == 8.0
    assert order == ["cleanup, vel_limit 8.0"]                       # after the settings are back
    assert logs == ["logs/20260102-030405_ABC_unit-abort.csv"] and not b.rows

    b.check("a check", True, "")
    assert b.report("unit-test", None, logs, extra=1) == 0
    out = json.loads((tmp_path / "logs" / "20260102-030405_ABC_unit-test.json").read_text())
    assert out["serial"] == "ABC" and out["extra"] == 1 and out["abort"] is None and out["logs"] == logs
    b.check("another", False, "")
    assert b.report("unit-test", None, logs) == 1
    b.checks.pop()
    assert b.report("unit-test", "Ctrl-C", logs) == 1


def test_bench_restore_survives_a_lost_board(json_bytes: bytes, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    class GoneLink(FakeLink):
        def write(self, endpoint_id: int, data: bytes) -> bytes:
            raise LinkLost("unplugged")

    b = safety_test.Bench(Board(GoneLink(json_bytes)), "s", "ABC")
    b.restore({"axis0.controller.config.vel_limit": 8.0}, [])
    assert "Press OUT on the PSU" in capsys.readouterr().out


# --- flash bookkeeping ---------------------------------------------------------------------------
def test_sectors_touched_and_readback_check() -> None:
    segs = [(0x08008000, b"\x11" * 0x4800)]                        # sector 2 and the start of sector 3
    touched = swd_flash.sectors_touched(segs)
    assert [swd_flash.SECTORS.index(s) for s in touched] == [2, 3]
    pre = bytearray(b"\xaa" * 0x100000)
    post = bytearray(pre)
    post[0x8000:0x8000 + 0x4800] = segs[0][1]
    post[0xC800:0x10000] = b"\xff" * (0x10000 - 0xC800)            # the rest of sector 3: erased
    ok = swd_flash.readback_check(segs, touched, bytes(pre), bytes(post))
    assert ok["image_bytes_wrong_after"] == ok["untouched_sectors_changed_bytes"] == ok["erased_not_programmed_non_ff"] == 0
    post[0x8000] = 0                                                # an image byte wrong
    post[0x40000] ^= 1                                              # a byte outside the erased sectors changed
    post[0xF000] = 0                                                # an erased byte not FF
    bad = swd_flash.readback_check(segs, touched, bytes(pre), bytes(post))
    assert (bad["image_bytes_wrong_after"], bad["untouched_sectors_changed_bytes"], bad["erased_not_programmed_non_ff"]) == (1, 1, 1)


def test_intel_hex_records() -> None:
    assert seal_image.intel_hex(0x08008000, b"\x01\x02") == ":020000040800F2\n:0280000001027B\n:00000001FF\n"
    lines = seal_image.intel_hex(0x0800FFF0, bytes(range(32))).splitlines()
    assert lines[0] == ":020000040800F2" and lines[2] == ":020000040801F1"  # a new upper address at 0x08010000
    assert [line[7:9] for line in lines] == ["04", "00", "04", "00", "01"]
    for line in lines:
        assert sum(bytes.fromhex(line[1:])) & 0xFF == 0                   # each record sums to zero
    assert struct.unpack(">H", bytes.fromhex(lines[1][3:7]))[0] == 0xFFF0
