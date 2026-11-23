"""can_test.py end to end against a fake board on python-can's virtual bus.

The fake answers endpoint access like the firmware and echoes impedance commands as replies, so the
checks that need a real rotor (stiffness, the watchdog hold) fail here. The fake's thread can miss a
reply deadline under load, so the timing checks may fail too; every other check passes, and the run
must end with the axis IDLE, the gains zero and the settings restored.
"""
from __future__ import annotations

import json
import pathlib
import time
import uuid
from typing import Any, Iterator

import pytest

from test_xdrive import FakeCanBoard, FakeLink, cache, json_bytes  # noqa: F401  (fixtures)

import can_test  # noqa: E402

NEEDS_A_ROTOR = {"kp 20: T +0.5 Nm deflects T/kp", "kp 20: T -0.5 Nm deflects T/kp", "kp 80: T +0.5 Nm deflects T/kp",
                 "a pause in the commands starts the hold", "commands are ignored during the hold"}
TIMING = {"no missed replies at 100 Hz", "round trip within the 10 ms period (p99)"}


class BenchLink(FakeLink):
    """FakeLink plus the board behavior can_test relies on: requested_state becomes current_state,
    and system_stats.uptime counts from the last (re)boot."""

    def __init__(self, json_bytes: bytes) -> None:
        super().__init__(json_bytes)
        self.boot = time.monotonic()
        self.put("can.config.baud_rate", 1_000_000)
        self.put("system_stats.stack_size_can", 1024)
        self.put("system_stats.max_stack_usage_can", 400)
        self.put("axis0.controller.config.vel_limit", 8.0)
        self.put("axis0.controller.config.max_pos_error", float("inf"))
        self.put("axis0.config.watchdog_timeout", 1.5)

    def read(self, endpoint_id: int, size: int) -> bytes:
        if endpoint_id == self.itf.properties["system_stats.uptime"].id:
            self.put("system_stats.uptime", int(1000 * (time.monotonic() - self.boot)))
        return super().read(endpoint_id, size)

    def write(self, endpoint_id: int, data: bytes) -> bytes:
        out = super().write(endpoint_id, data)
        if endpoint_id == self.itf.properties["axis0.requested_state"].id:
            state = self.value("axis0.requested_state")
            self.put("axis0.current_state", state)
            self.armed = state == 8
        return out

    def reconnect(self, timeout: float) -> None:
        if self.rebooting:
            self.rebooting = False
            self.boot = time.monotonic()


@pytest.fixture
def board(json_bytes: bytes) -> Iterator[tuple[str, FakeCanBoard]]:  # noqa: F811
    channel = f"can-test-{uuid.uuid4()}"
    fake = FakeCanBoard(json_bytes, channel, 3, link=BenchLink(json_bytes))
    yield channel, fake
    fake.stop()


def test_full_run_against_a_fake_board(board: tuple[str, FakeCanBoard], tmp_path: pathlib.Path,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    channel, fake = board
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(can_test, "WORKDIR", tmp_path)
    monkeypatch.setattr(can_test, "LOGS", tmp_path / "logs")

    code = can_test.main(["--interface", "virtual", "--channel", channel, "--rate", "100"])

    out_path, = (tmp_path / "logs").glob("*_node3_can-test.json")
    out: dict[str, Any] = json.loads(out_path.read_text())
    assert out["abort"] is None
    failed = {c["check"] for c in out["checks"] if not c["ok"]}
    assert NEEDS_A_ROTOR <= failed <= NEEDS_A_ROTOR | TIMING
    assert code == 1
    names = {c["check"] for c in out["checks"]}
    assert {"node ID and baud rate read back", "saved value survives the reboot (changed)",
            "saved value survives the reboot (restored)", "clear_errors over CAN resumes impedance control",
            "no missed replies at 100 Hz"} <= names
    assert out["stats"]["cycle_back_to_back"]["rate_hz"] > 100
    assert sorted(p.split("can-")[-1] for p in out["logs"]) == ["impedance.csv", "latency.csv"]

    link = fake.link
    assert link.value("axis0.current_state") == 1 and link.value("axis0.requested_state") == 1
    assert link.value("axis0.config.can.heartbeat_rate_ms") == 20
    assert link.value("axis0.controller.config.vel_limit") == 8.0
    assert link.value("axis0.controller.config.max_pos_error") == float("inf")
    assert link.value("axis0.config.watchdog_timeout") == 1.5 and not link.value("axis0.config.enable_watchdog")
    assert link.value("axis0.controller.config.control_mode") == 0
    for name in ("input_kp", "input_kd", "input_vel", "input_torque"):
        assert link.value(f"axis0.controller.{name}") == 0.0


def test_silent_bus_aborts_with_a_hint(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(can_test, "WORKDIR", tmp_path)
    monkeypatch.setattr(can_test, "LOGS", tmp_path / "logs")
    code = can_test.main(["--interface", "virtual", "--channel", f"can-test-{uuid.uuid4()}"])
    out = json.loads(next((tmp_path / "logs").glob("*_can-test.json")).read_text())
    assert code == 1 and "no heartbeat heard" in out["abort"]
