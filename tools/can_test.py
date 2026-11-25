#!/usr/bin/env python3
"""Bench test of one board over CAN.  *** MOTOR MOVES (impedance: about 20 s, up to 4 turns; current: five
small torque steps against a spring) and the board reboots twice (save: its startup sequence runs each time) ***

Stages; the bus checks always run first, then --tests in this order:
  bus        the node sends heartbeats (no --node: the only node heard is the one tested)
  endpoint   endpoint access (0x1F): connect (the interface JSON comes from the cache, or over CAN once
             per firmware build), node ID and baud rate read back, heartbeat interval matches
             heartbeat_rate_ms, a write's reply carries the stored value, a function call, the firmware
             refuses a write to a read-only property, 200-read round-trip latency, no CAN error flags
  save       a configure-save-reboot round trip over CAN: heartbeat_rate_ms changed, saved (the board
             reboots), the heartbeat interval follows, then the original value saved back. Saving
             stores the board's whole RAM config, so run it on a board whose RAM config is its saved one
  impedance  impedance_test.py's checks through the impedance frame (0x1E) at --rate Hz: stiffness
             (T/kp), a 0.1 turn step, a host-streamed 1 turn cosine move, damping only (kp = 0), and
             the watchdog: a pause in the commands starts the decelerate-and-hold, commands are ignored
             during it, clear_errors over CAN resumes
  latency    3 s of impedance cycles at --rate Hz (no missed replies, round trip within the period), then
             3 s back to back (the fastest cycle rate one board allows); CAN thread stack high-water mark
             and CAN error flags afterwards
  current    command to current: five 0.5 Nm torque steps through the impedance frame while the spring
             (kp 20) holds the rotor. On the board, an 8 kHz capture triggered by input_torque times the
             Iq setpoint and the measured current (10 % and 90 % of the step) from the moment the
             controller sees the command; on the host, back-to-back cycles time the first reply whose
             torque (from the measured current) shows half the step: within one --rate period
  load       six joints' traffic: every cycle also carries five absent joints' commands and replies
             (nodes the bus scan didn't hear; the stage refuses if another node is on the bus), at
             250 Hz and 500 Hz (no missed replies, the whole cycle within the period), then back to
             back; CAN error flags afterwards

Every impedance cycle is logged to logs/<stamp>_node<N>_can-<stage>.csv, the current stage's capture
windows to logs/<stamp>_node<N>_can-current-capture.csv; the checks and the latency
numbers go to logs/<stamp>_node<N>_can-test.json. RAM-only settings, restored at the end; ends IDLE.
Exit code 1 if any check fails.

Before the first run, over USB (the board's defaults are 250 kbit/s and node 0; can.config.protocol
must be 1, CANSimple, the default):
  python tools/set_config.py can.config.baud_rate=1000000 axis0.config.can.node_id=1 --save
Wiring, termination and ground: docs/can.md.

Usage (from the repo root):  python tools/can_test.py [--interface gs_usb --channel 0] [--node 1] [--rate 250]
                             [--tests endpoint,save,impedance,latency]
"""
import argparse
import csv
import dataclasses
import datetime
import json
import math
import statistics
import sys
import time
from typing import Any

import numpy as np

import can as python_can

from logfiles import logs_dir, rel
from xdrive import can, report
from xdrive.board import Board
from xdrive.enums import AxisState, ControlMode, InputMode, WatchdogAction
from xdrive.errors import LinkError, Refused, XdriveError
from xdrive.impedance_frame import MSG_IMPEDANCE, Reply
from xdrive.model import RwProp
from xdrive.props import odrv

import capture

RUNAWAY = 12.0           # turn/s: IDLE immediately above this
POS_MARGIN = 5.0         # turn: the impedance stage travels up to 4 turns from where it starts
MAX_MISSED = 25          # consecutive missed replies before the run aborts
FRAME_BITS = 130         # one 8-byte frame with bit stuffing: 0.13 ms at 1 Mbit/s (docs/can.md)
TESTS = ["endpoint", "save", "impedance", "latency", "current", "load"]
STEP_TORQUE = 0.5        # Nm: the current stage's torque step, about 4.7 A on a 10018
STEPS = 5                # torque steps in the current stage
CAPTURE_FIELDS = ["axis0.controller.input_torque", "axis0.controller.torque_setpoint",
                  "axis0.motor.current_control.Iq_setpoint", "axis0.motor.current_control.Iq_measured"]
WINDOW = (16, 80)        # capture samples read before and after the trigger: 2 ms and 10 ms at 8 kHz
LOAD_JOINTS = 5          # the joints the load stage stands in for, besides the tested one
LOAD_FRAME = bytes.fromhex("8a3c51e07f2d96b4")  # payload of each load frame

ax = odrv.axis0
ctl = ax.controller.config
wd = ax.config
SETTINGS: list[RwProp[Any]] = [  # every setting a stage changes in RAM; restored at the end (watchdog first)
    wd.enable_watchdog, wd.watchdog_timeout, wd.watchdog_action, wd.watchdog_decel, wd.watchdog_torque_lim,
    ctl.control_mode, ctl.input_mode, ctl.max_pos_error,
]
FIELDS = ["t", "event", "cmd_pos", "cmd_vel", "cmd_kp", "cmd_kd", "cmd_torque",
          "pos", "vel", "torque", "armed", "error", "timeout", "fet_temp", "vbus", "rtt_ms"]


class Unexpected(Exception):
    pass


@dataclasses.dataclass
class Row:
    t: float
    event: str
    cmd: can.Impedance
    reply: Reply | None
    rtt: float


def stats_ms(seconds):
    s = sorted(seconds)
    return {"n": len(s), "median_ms": 1e3 * statistics.median(s), "p99_ms": 1e3 * s[min(len(s) - 1, int(0.99 * len(s)))],
            "max_ms": 1e3 * s[-1]}


class Bench:
    def __init__(self, bus, node, rate, bitrate, stamp):
        self.bus, self.node, self.rate, self.stamp = bus, node, rate, stamp
        self.frame_s = FRAME_BITS / bitrate
        self.connected: Board | None = None
        self.rows, self.checks, self.stats = [], [], {}
        self.t0 = time.perf_counter()

    def check(self, name, ok, detail):
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    def log(self, name):
        path = logs_dir() / f"{self.stamp}_node{self.node}_can-{name}.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(FIELDS)
            for r in self.rows:
                c, p = r.cmd, r.reply
                got = ([p.pos, p.vel, p.torque, int(p.armed), int(p.error), int(p.timeout), p.fet_temp, p.vbus]
                       if p else [""] * 8)
                w.writerow([f"{r.t:.5f}", r.event, c.pos, c.vel, c.kp, c.kd, c.torque] + got + [f"{1e3 * r.rtt:.3f}"])
        self.rows = []
        return path

    @property
    def board(self) -> Board:
        if self.connected is None:
            raise Unexpected("no board connected")
        return self.connected

    # --- impedance cycles -----------------------------------------------------------------------
    def stream(self, seconds, command, event, rate=None, allow_error=False, require_armed=True, load=()):
        """Sends command (an Impedance, or a function of the time since the start) once per cycle for
        `seconds` at `rate` Hz (default --rate; 0: back to back), each reply awaited up to one --rate
        period. Returns this call's rows. Aborts on a runaway, an unexpected error flag or disarm, or
        MAX_MISSED replies missed in a row.

        load: node IDs of absent joints. Each cycle then sends their commands (LOAD_FRAME) ahead of the
        tested node's and their replies after its reply, so the bus carries every joint's traffic; a
        row's rtt covers the whole cycle."""
        rate = self.rate if rate is None else rate
        period = 1.0 / rate if rate else 0.0
        timeout = 1.0 / self.rate
        rows, missed = [], 0
        start = time.perf_counter()
        next_t = start
        while (now := time.perf_counter()) - start < seconds:
            cmd = command(now - start) if callable(command) else command
            for n in load:
                self.bus.send_raw(can.arbitration_id(n, MSG_IMPEDANCE), LOAD_FRAME)
            reply = self.bus.cycle({self.node: cmd}, timeout)[self.node]
            for n in load:
                self.bus.send_raw(can.arbitration_id(n, MSG_IMPEDANCE), LOAD_FRAME)
            row = Row(now - self.t0, event, cmd, reply, time.perf_counter() - now)
            event = ""
            rows.append(row)
            self.rows.append(row)
            if reply is None:
                missed += 1
                if missed >= MAX_MISSED:
                    raise Unexpected(f"{missed} impedance replies missed in a row")
            else:
                missed = 0
                if abs(reply.vel) > RUNAWAY:
                    raise Unexpected(f"runaway guard: |vel| {abs(reply.vel):.1f} > {RUNAWAY} turn/s")
                if reply.error and not allow_error:
                    raise Unexpected(f"error flag in the impedance reply: {self.errors()}")
                if require_armed and not reply.armed:
                    raise Unexpected(f"disarmed: state {self.board.get(ax.current_state).name}, errors {self.errors()}")
            if period:
                next_t += period
                delay = next_t - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -period:
                    next_t = time.perf_counter()  # fell behind by more than a period: don't burst to catch up
        return rows

    @staticmethod
    def replies(rows):
        return [r.reply for r in rows if r.reply is not None]

    @staticmethod
    def mean(rows, field, last):
        """Mean of a reply field over the rows within `last` seconds of the final row."""
        t_end = rows[-1].t
        vals = [getattr(r.reply, field) for r in rows if r.reply is not None and r.t >= t_end - last]
        if not vals:
            raise Unexpected(f"no impedance replies in the final {last} s")
        return sum(vals) / len(vals)

    # --- board helpers --------------------------------------------------------------------------
    def errors(self):
        """The axis's error words; motor.error is 64 bits, out of reach of endpoint access, so its
        heartbeat flag stands in for it."""
        board = self.board
        out = {"axis": f"{int(board.get(ax.error)):#x}", "encoder": f"{int(board.get(ax.encoder.error)):#x}",
               "controller": f"{int(board.get(ax.controller.error)):#x}"}
        hb = self.bus.heartbeat(self.node)
        out["motor"] = "unknown" if hb is None else "set" if hb.motor_error else "clear"
        return out

    def idle(self):
        """IDLE, then wait for the rotor to coast below 0.5 turn/s."""
        self.board.set(ax.requested_state, AxisState.IDLE)
        t = time.monotonic()
        while time.monotonic() - t < 20:
            vel: float = self.board.get(ax.encoder.vel_estimate)
            if abs(vel) <= 0.5:
                break
            time.sleep(0.05)

    def arm(self, kp, kd):
        """Impedance control, passthrough, closed loop, holding where the rotor is. Returns the hold command."""
        pos = self.board.get(ax.encoder.pos_estimate)
        limit = self.bus.ranges[self.node].pos - POS_MARGIN
        if abs(pos) > limit:
            raise Unexpected(f"pos_estimate {pos:+.2f} turn is outside +/-{limit:g} turn, which the impedance "
                             "frame's position range must cover for this test: bring the count back near 0 "
                             "(axis0.encoder.set_linear_count in IDLE) and run again")
        self.board.set(ctl.control_mode, ControlMode.IMPEDANCE_CONTROL)
        self.board.set(ctl.input_mode, InputMode.PASSTHROUGH)
        hold = can.Impedance(pos=pos, kp=kp, kd=kd)
        self.bus.cycle({self.node: hold}, 1.0 / self.rate)   # sets the inputs before arming
        self.board.call(odrv.clear_errors())
        self.board.set(ax.requested_state, AxisState.CLOSED_LOOP_CONTROL)
        self.stream(0.4, hold, "closed_loop", require_armed=False)
        state = self.board.get(ax.current_state)
        if state != AxisState.CLOSED_LOOP_CONTROL:
            raise Unexpected(f"did not enter closed loop: state {state.name}, errors {self.errors()}")
        return hold

    def heartbeat_interval(self, seconds):
        """Median interval between the node's heartbeats over `seconds`, by host receipt time."""
        times: list[float] = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            hb = self.bus.heartbeat(self.node)
            if hb is not None and (not times or hb.t != times[-1]):
                times.append(hb.t)
            time.sleep(0.002)
        gaps = [b - a for a, b in zip(times, times[1:])]
        return statistics.median(gaps) if gaps else math.inf

    def wait_booted(self, timeout=30.0):
        """After a reboot: waits until the startup sequence has ended in IDLE or closed loop."""
        end = time.monotonic() + timeout
        settled: list[AxisState] = []
        while time.monotonic() < end:
            state = self.board.get(ax.current_state)
            settled = settled[-2:] + [state]
            if len(settled) == 3 and len(set(settled)) == 1 and state in (AxisState.IDLE, AxisState.CLOSED_LOOP_CONTROL):
                return state
            time.sleep(0.2)
        raise Unexpected(f"startup did not settle in {timeout:g} s: state {settled[-1].name if settled else '?'}")


def test_bus(b, wanted):
    print("bus")
    nodes = b.bus.scan(0.5)
    if wanted is None:
        if len(nodes) != 1:
            raise Unexpected(f"heartbeats heard from nodes {nodes}; pass --node" if nodes else
                             "no heartbeat heard: check the bitrate (the board's can.config.baud_rate), "
                             "can.config.protocol (1: CANSimple), wiring, termination and the adapter's "
                             "ground (docs/can.md)")
        b.node = nodes[0]
    b.check("node sends heartbeats", b.node in nodes, f"node {b.node}, heard {nodes}")
    if b.node not in nodes:
        raise Unexpected(f"node {b.node} is silent")
    hb = b.bus.heartbeat(b.node)
    print(f"  node {b.node}: state {hb.state.name}, axis error {int(hb.axis_error):#x}")


def test_endpoint(b, bitrate):
    print("endpoint")
    board = b.board
    v = [board.get(p) for p in (odrv.fw_version_major, odrv.fw_version_minor, odrv.fw_version_revision)]
    print(f"  firmware {'.'.join(map(str, v))}, vbus {board.get(odrv.vbus_voltage):.2f} V")
    node, baud = board.get(ax.config.can.node_id), board.get(odrv.can.config.baud_rate)
    b.check("node ID and baud rate read back", node == b.node and baud == bitrate, f"node_id {node}, baud_rate {baud}")
    rate_ms = board.get(ax.config.can.heartbeat_rate_ms)
    gap = b.heartbeat_interval(1.0)
    b.check("heartbeat interval matches heartbeat_rate_ms", abs(1e3 * gap - rate_ms) <= 0.2 * rate_ms,
            f"{1e3 * gap:.1f} ms vs {rate_ms} ms")

    vel_limit = board.get(ctl.vel_limit)
    try:
        stored = board.set(ctl.vel_limit, vel_limit + 1.0)
        read = board.get(ctl.vel_limit)
    finally:
        board.set(ctl.vel_limit, vel_limit)
    b.check("a write's reply is the stored value", stored == read == vel_limit + 1.0,
            f"reply {stored}, read back {read}, written {vel_limit + 1.0}")
    first, second = board.call(odrv.test_function(delta=3)), board.call(odrv.test_function(delta=3))
    b.check("function call (test_function)", second - first == 3, f"cnt {first} then {second}")
    try:
        board.link.write(board.endpoint_id(odrv.vbus_voltage), bytes(4))
        refused = "no refusal"
    except Refused as ex:
        refused = str(ex)
    b.check("firmware refuses a write to a read-only property", "WRONG_KIND" in refused, refused)

    times = []
    for _ in range(200):
        t = time.perf_counter()
        board.get(odrv.vbus_voltage)
        times.append(time.perf_counter() - t)
    s = b.stats["endpoint_read"] = stats_ms(times)
    print(f"  endpoint read round trip: median {s['median_ms']:.2f} ms, p99 {s['p99_ms']:.2f} ms, max {s['max_ms']:.2f} ms")
    err = board.get(odrv.can.error)
    b.check("no CAN error flags", not err, f"can.error {report.flag_names(err)}")


def test_save(b):
    print("save")
    board, hb = b.board, ax.config.can.heartbeat_rate_ms
    b.idle()
    original = board.get(hb)
    changed = 50 if original != 50 else 100
    for value, label in ((changed, "changed"), (original, "restored")):
        board.set(hb, value)
        t = time.monotonic()
        board.save()                                   # returns once the board answers again
        up = time.monotonic() - t
        state = b.wait_booted()
        print(f"  saved heartbeat_rate_ms = {value}: back after {up:.1f} s, startup ended in {state.name}")
        gap = b.heartbeat_interval(1.0)
        now = board.get(hb)
        b.check(f"saved value survives the reboot ({label})", now == value and abs(1e3 * gap - value) <= 0.2 * value,
                f"heartbeat_rate_ms {now}, heartbeat interval {1e3 * gap:.1f} ms")
        b.idle()                                       # the startup sequence may have armed it


def test_impedance(b):
    print("impedance")
    board = b.board
    hold = b.arm(20.0, 0.3)
    p0 = hold.pos

    print("  stiffness")
    for kp, torques in ((20.0, (0.5, -0.5)), (80.0, (0.5,))):
        hold = can.Impedance(pos=p0, kp=kp, kd=0.3)
        base = b.mean(b.stream(1.0, hold, f"kp{kp:g}_T0"), "pos", 0.5)
        for t in torques:
            dp = b.mean(b.stream(1.5, dataclasses.replace(hold, torque=t), f"kp{kp:g}_T{t:+g}"), "pos", 0.5) - base
            want = t / kp
            b.check(f"kp {kp:g}: T {t:+g} Nm deflects T/kp", abs(dp - want) <= 0.25 * abs(want),
                    f"{dp:+.5f} turn vs {want:+.5f}")

    print("  tracking")
    hold = can.Impedance(pos=p0, kp=50.0, kd=0.5)
    b.stream(0.5, hold, "track_hold")
    target = p0 + 0.1
    err = b.mean(b.stream(1.5, dataclasses.replace(hold, pos=target), "step_0.1"), "pos", 0.3) - target
    b.check("0.1 turn step settles on target", abs(err) < 0.003, f"final error {err:+.5f} turn")

    print("  streamed move")
    start, span, dur = target, 1.0, 1.0

    def cosine(t):
        s = min(t / dur, 1.0)
        return can.Impedance(pos=start + 0.5 * span * (1.0 - math.cos(math.pi * s)),
                             vel=0.5 * span * math.pi / dur * math.sin(math.pi * s), kp=50.0, kd=0.5)

    rows = b.stream(dur + 0.6, cosine, "cosine_1turn")
    lag = max(abs(r.reply.pos - r.cmd.pos) for r in rows if r.reply is not None and r.t - rows[0].t <= dur)
    final = b.mean(rows, "pos", 0.3) - (start + span)
    b.check("host-streamed 1 turn move tracks", lag < 0.02, f"peak error {lag:.4f} turn")
    b.check("host-streamed 1 turn move ends on target", abs(final) < 0.003, f"final error {final:+.5f} turn")

    print("  damping")
    board.set(ctl.max_pos_error, 0.05)
    p = rows[-1].cmd.pos
    rows = b.stream(2.5, can.Impedance(pos=p, vel=1.0, kp=0.0, kd=0.2), "damping_vel1")
    v, tq = b.mean(rows, "vel", 1.0), b.mean(rows, "torque", 1.0)
    # The steady speed sits below input_vel by drag / kd: a gearbox on the rotor slows it more.
    b.check("damping only: runs forward at a steady speed", 0.2 <= v <= 1.05, f"{v:.3f} turn/s")
    b.check("damping only: torque = kd * vel error", abs(tq - 0.2 * (1.0 - v)) < 0.02,
            f"{tq:+.4f} Nm (measured) vs {0.2 * (1.0 - v):+.4f}")
    stop = can.Impedance(pos=p, vel=0.0, kp=0.0, kd=0.2)
    b.stream(1.0, stop, "damping_stop")
    rows = b.stream(1.0, stop, "damping_still")
    replies = b.replies(rows)
    drift = replies[-1].pos - replies[0].pos
    b.check("damping only: no spring, no position fault",
            abs(drift) < 0.05 and not board.get(ax.controller.error) and board.get(ax.current_state) == AxisState.CLOSED_LOOP_CONTROL,
            f"drift {drift:+.4f} turn, controller error {int(board.get(ax.controller.error)):#x}")
    board.set(ctl.max_pos_error, math.inf)

    print("  watchdog")
    p_hold = replies[-1].pos
    hold = can.Impedance(pos=p_hold, kp=20.0, kd=0.3)
    b.stream(0.3, hold, "hold")
    board.set(wd.watchdog_timeout, 0.2)
    board.set(wd.watchdog_action, WatchdogAction.DECEL_HOLD)
    board.set(wd.watchdog_decel, 10.0)
    board.set(wd.watchdog_torque_lim, math.inf)
    board.set(wd.enable_watchdog, True)                # every frame to the board feeds it
    b.stream(0.5, hold, "fed_by_commands")
    time.sleep(0.6)                                    # three timeouts without a frame
    rows = b.stream(0.02, hold, "after_pause", allow_error=True)
    r = rows[0].reply
    detail = (f"timeout {r.timeout}, armed {r.armed}, pos - hold {r.pos - p_hold:+.4f} turn" if r is not None
              else "no reply")
    b.check("a pause in the commands starts the hold", r is not None and r.timeout and r.armed and abs(r.pos - p_hold) < 0.01,
            detail)
    rows = b.stream(0.5, dataclasses.replace(hold, pos=p_hold + 0.5), "command_during_hold", allow_error=True)
    moved = b.mean(rows, "pos", 0.2) - p_hold
    b.check("commands are ignored during the hold", abs(moved) < 0.01, f"moved {moved:+.4f} turn toward a +0.5 turn command")
    board.call(odrv.clear_errors())
    rows = b.stream(0.5, hold, "resume")
    r = b.replies(rows)[-1]
    mode = board.get(ctl.control_mode)
    b.check("clear_errors over CAN resumes impedance control", not r.timeout and r.armed and mode == ControlMode.IMPEDANCE_CONTROL,
            f"timeout {r.timeout}, armed {r.armed}, control_mode {mode.name}")
    board.set(wd.enable_watchdog, False)
    b.idle()
    return b.log("impedance")


def test_latency(b):
    print("latency")
    board = b.board
    hold = b.arm(20.0, 0.3)
    rows = b.stream(3.0, hold, f"hold_{b.rate:g}Hz")
    got = [r.rtt for r in rows if r.reply is not None]
    missed = len(rows) - len(got)
    s = b.stats["cycle_at_rate"] = {"rate_hz": b.rate, "cycles": len(rows), "missed": missed, **stats_ms(got)}
    b.check(f"no missed replies at {b.rate:g} Hz", missed == 0, f"{missed} of {len(rows)}")
    b.check(f"round trip within the {1e3 / b.rate:g} ms period (p99)", s["p99_ms"] < 1e3 / b.rate,
            f"median {s['median_ms']:.2f} ms, p99 {s['p99_ms']:.2f} ms, max {s['max_ms']:.2f} ms")

    rows = b.stream(3.0, hold, "back_to_back", rate=0)
    got = [r.rtt for r in rows if r.reply is not None]
    fastest = len(rows) / (rows[-1].t - rows[0].t)
    s = b.stats["cycle_back_to_back"] = {"rate_hz": fastest, "cycles": len(rows), "missed": len(rows) - len(got),
                                         **stats_ms(got)}
    # Estimate, not measured: six joints per cycle add five command-and-reply pairs of bus time to one round trip.
    six = s["median_ms"] + 1e3 * 10 * b.frame_s
    b.stats["six_joint_cycle_estimate_ms"] = six
    print(f"  back to back: {fastest:.0f} cycles/s, median {s['median_ms']:.2f} ms, missed {s['missed']}; "
          f"bus load from the cycles about {100 * fastest * 2 * b.frame_s:.0f} %")
    print(f"  estimate: one six-joint cycle takes about {six:.2f} ms ({1e3 / six:.0f} Hz at most)")

    used, size = board.get(odrv.system_stats.max_stack_usage_can), board.get(odrv.system_stats.stack_size_can)
    b.check("CAN thread stack below 80 % after the traffic", used < 0.8 * size, f"{used} of {size} bytes")
    err = board.get(odrv.can.error)
    b.check("no CAN error flags", not err, f"can.error {report.flag_names(err)}")
    b.idle()
    return b.log("latency")


def first_at(t, fraction, level):
    """Time of the first sample at t >= 0 whose fraction of the step reaches `level`, in ms; None if none does."""
    hits = np.nonzero((t >= 0) & (fraction >= level))[0]
    return None if len(hits) == 0 else 1e3 * float(t[hits[0]])


def test_current(b):
    """Command to current: STEPS torque steps of STEP_TORQUE through the impedance frame while the spring
    holds the rotor. On the board, an 8 kHz capture triggered by input_torque (the moment the CAN
    thread applies the command) times the measured current; on the host, back-to-back cycles time the
    first reply whose torque (from the measured current) shows half the step. Iq's sign follows the
    motor's direction, so the board's times use each signal's fraction of the Iq setpoint's step."""
    print("current")
    board = b.board
    hold = b.arm(20.0, 0.3)
    step = dataclasses.replace(hold, torque=STEP_TORQUE)
    steps: list[dict[str, Any]] = []
    windows = []
    for i in range(STEPS):
        fields, types = capture.setup(board, CAPTURE_FIELDS, trigger=(CAPTURE_FIELDS[0], capture.RISING, STEP_TORQUE / 2))
        before = b.stream(0.2, hold, "hold", rate=0)
        rows = b.stream(0.2, step, f"step_{i}", rate=0)
        try:
            capture.wait_done(board, 1.0)
        except capture.CaptureError:
            steps.append({"triggered": False})
            b.stream(0.3, hold, "release", rate=0)
            continue
        t, data, _ = capture.read(board, fields, types, window=WINDOW)
        b.stream(0.3, hold, "release", rate=0)
        iq_sp, iq = data[CAPTURE_FIELDS[2]], data[CAPTURE_FIELDS[3]]
        pre = t < 0
        sp0, iq0 = float(iq_sp[pre].mean()), float(iq[pre].mean())
        d_sp = float(iq_sp[(t >= 0) & (t < 0.0005)].mean()) - sp0      # the setpoint's step, A (signed)
        base = b.mean(before, "torque", 0.1)
        seen = next((r for r in rows if r.reply is not None and r.reply.torque - base >= 0.5 * STEP_TORQUE), None)
        steps.append({"triggered": True, "iq_setpoint_step_a": d_sp,
                      "applied_to_setpoint_ms": first_at(t, (iq_sp - sp0) / d_sp, 0.5),
                      "applied_to_10pct_current_ms": first_at(t, (iq - iq0) / d_sp, 0.1),
                      "applied_to_90pct_current_ms": first_at(t, (iq - iq0) / d_sp, 0.9),
                      "host_send_to_reply_ms": None if seen is None else 1e3 * (seen.t + seen.rtt - rows[0].t)})
        windows.append((i, t, data))
    b.idle()

    done = [s for s in steps if s["triggered"]]
    b.check("the CAN command reaches the controller in every step", len(done) == STEPS,
            f"the capture triggered on input_torque in {len(done)} of {STEPS} steps")
    def med(key):
        vals = [s[key] for s in done if s.get(key) is not None]
        return statistics.median(vals) if len(vals) == len(done) and vals else None
    s = b.stats["command_to_current"] = {"steps": steps, "step_torque_nm": STEP_TORQUE,
                                         **{f"median_{k}": med(k) for k in ("applied_to_setpoint_ms", "applied_to_10pct_current_ms",
                                            "applied_to_90pct_current_ms", "host_send_to_reply_ms")}}
    one_way = b.stats.get("cycle_back_to_back", {}).get("median_ms")
    if one_way is not None and s["median_applied_to_90pct_current_ms"] is not None:
        # Estimate: half a round trip stands in for the one-way command time, which no shared clock measures.
        s["estimate_send_to_90pct_current_ms"] = one_way / 2 + s["median_applied_to_90pct_current_ms"]
    print(f"  on the board, command applied -> Iq setpoint {s['median_applied_to_setpoint_ms']} ms, measured current "
          f"10 % {s['median_applied_to_10pct_current_ms']} ms, 90 % {s['median_applied_to_90pct_current_ms']} ms (medians)")
    if "estimate_send_to_90pct_current_ms" in s:
        print(f"  estimate, host send -> 90 % current: {s['estimate_send_to_90pct_current_ms']:.2f} ms "
              "(half the back-to-back round trip plus the board's part)")
    host = [st["host_send_to_reply_ms"] for st in done]
    worst = max((h for h in host if h is not None), default=None)
    b.check(f"the current shows in a reply within the {1e3 / b.rate:g} ms period at {b.rate:g} Hz",
            done and None not in host and worst is not None and worst < 1e3 / b.rate,
            f"host send -> first reply with half the step: {', '.join('none' if h is None else f'{h:.2f}' for h in host)} ms")

    path = logs_dir() / f"{b.stamp}_node{b.node}_can-current-capture.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "t_ms"] + CAPTURE_FIELDS)
        for i, t, data in windows:
            for k in range(len(t)):
                w.writerow([i, f"{1e3 * t[k]:.3f}"] + [f"{float(data[c][k]):.5f}" for c in CAPTURE_FIELDS])
    return [b.log("current"), path]


def test_load(b):
    """Six joints' traffic with one board: each cycle also carries LOAD_JOINTS absent joints' commands
    and replies, at 250 Hz, 500 Hz and back to back."""
    print("load")
    board = b.board
    others = [n for n in b.bus.scan() if n != b.node]
    if others:
        raise Unexpected(f"nodes {others} are on the bus: the load stage's frames would command them; "
                         "run it with only the tested board on the bus")
    load = [n for n in range(64) if n != b.node][:LOAD_JOINTS]
    frames = 2 * (LOAD_JOINTS + 1)
    hold = b.arm(20.0, 0.3)
    for rate in (250.0, 500.0):
        rows = b.stream(3.0, hold, f"load_{rate:g}Hz", rate=rate, load=load)
        got = [r.rtt for r in rows if r.reply is not None]
        missed = len(rows) - len(got)
        s = b.stats[f"load_{rate:g}hz"] = {"rate_hz": rate, "cycles": len(rows), "missed": missed,
                                           "bus_load_pct": 100 * rate * frames * b.frame_s, **stats_ms(got)}
        b.check(f"no missed replies at {rate:g} Hz with {LOAD_JOINTS + 1} joints' traffic", missed == 0,
                f"{missed} of {len(rows)}; bus load about {s['bus_load_pct']:.0f} %")
        b.check(f"a {LOAD_JOINTS + 1}-joint cycle fits the {1e3 / rate:g} ms period (p99)", s["p99_ms"] < 1e3 / rate,
                f"median {s['median_ms']:.2f} ms, p99 {s['p99_ms']:.2f} ms, max {s['max_ms']:.2f} ms")
    rows = b.stream(3.0, hold, "load_back_to_back", rate=0, load=load)
    got = [r.rtt for r in rows if r.reply is not None]
    fastest = len(rows) / (rows[-1].t - rows[0].t)
    s = b.stats["load_back_to_back"] = {"rate_hz": fastest, "cycles": len(rows), "missed": len(rows) - len(got),
                                        "bus_load_pct": 100 * fastest * frames * b.frame_s, **stats_ms(got)}
    print(f"  back to back with {LOAD_JOINTS + 1} joints' traffic: {fastest:.0f} cycles/s, median {s['median_ms']:.2f} ms, "
          f"missed {s['missed']}; bus load about {s['bus_load_pct']:.0f} %")
    err = board.get(odrv.can.error)
    b.check("no CAN error flags after the load", not err, f"can.error {report.flag_names(err)}")
    b.idle()
    return b.log("load")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", default="gs_usb", help="python-can interface (default gs_usb: candleLight adapters)")
    ap.add_argument("--channel", default="0", help="python-can channel (gs_usb: any; slcan: the serial port)")
    ap.add_argument("--bitrate", type=int, default=1_000_000)
    ap.add_argument("--node", type=int, help="node ID to test (default: the only node heard)")
    ap.add_argument("--rate", type=float, default=250.0, help="impedance cycle rate [Hz]")
    ap.add_argument("--tests", default=",".join(TESTS))
    args = ap.parse_args(argv)
    tests = args.tests.split(",")
    unknown = set(tests) - set(TESTS)
    if unknown:
        ap.error(f"unknown tests {sorted(unknown)}; choose from {TESTS}")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    print("*** The motor moves and the board reboots during this test. Keep hands clear; the PSU's OUT button stops it. ***")

    logs, abort = [], None
    saved: dict[RwProp[Any], Any] = {}
    try:
        opened = can.open(timeout=0.5, interface=args.interface, channel=args.channel, bitrate=args.bitrate)
    except python_can.CanError as ex:
        print(f"Can't open the CAN adapter (interface {args.interface}, channel {args.channel}): {ex}")
        return 1
    with opened as bus:
        b = Bench(bus, args.node, args.rate, args.bitrate, stamp)
        try:
            test_bus(b, args.node)
            t = time.monotonic()
            b.connected = bus.connect(b.node)
            print(f"  connected in {time.monotonic() - t:.1f} s")
            saved = {p: b.board.get(p) for p in SETTINGS}
            b.idle()
            for name in TESTS:
                if name not in tests:
                    continue
                if name == "endpoint":
                    test_endpoint(b, args.bitrate)
                elif name == "save":
                    test_save(b)
                elif name == "impedance":
                    logs.append(rel(test_impedance(b)))
                elif name == "latency":
                    logs.append(rel(test_latency(b)))
                elif name == "current":
                    logs += [rel(p) for p in test_current(b)]
                elif name == "load":
                    logs.append(rel(test_load(b)))
        except (Unexpected, XdriveError, KeyboardInterrupt) as ex:
            abort = repr(ex)
            print(f"ABORT: {abort}")
        finally:
            if b.connected is not None:
                try:
                    b.idle()
                    for p in (ax.controller.input_kp, ax.controller.input_kd, ax.controller.input_vel, ax.controller.input_torque):
                        b.board.set(p, 0.0)
                    for p, value in saved.items():
                        b.board.set(p, value)
                    if b.rows:
                        logs.append(rel(b.log("abort")))
                except (LinkError, XdriveError) as ex:  # the bus or the board gone: the only stop left is the PSU
                    print(f"!!! Post-run IDLE/restore failed ({ex!r}). Press OUT on the PSU if the motor is driven.")
    out = {"t": datetime.datetime.now().astimezone().isoformat(), "node": b.node, "interface": args.interface,
           "bitrate": args.bitrate, "rate_hz": args.rate, "tests": tests, "abort": abort, "checks": b.checks,
           "stats": b.stats, "logs": logs}
    path = logs_dir() / f"{stamp}_node{b.node}_can-test.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    failed = [c for c in b.checks if not c["ok"]]
    print(f"{len(b.checks) - len(failed)}/{len(b.checks)} checks passed; axis IDLE; settings restored -> {rel(path)}")
    return 1 if failed or abort else 0


if __name__ == "__main__":
    sys.exit(main())
