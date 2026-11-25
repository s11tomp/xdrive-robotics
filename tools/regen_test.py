#!/usr/bin/env python3
"""Bench test of regen handling: brake resistor, flux braking, bus current soft limits.  *** MOTOR MOVES ***

Trap moves to 10 turn/s and back (0.3 s cruise); the firmware's high-rate capture records vbus, brake
current, I_bus, Iq, Id and velocity over the out move at 800 Hz, and the checks use I_bus averaged over the
acceleration and the stop (single frames carry about 0.3 A of current-measurement noise). The stand's bare
rotor stores little energy: at 30 turn/s^2 friction and copper loss absorb the stop, so the soft limits
are tested at 120 turn/s^2, and flux braking with its start voltage below the bus.
  brake        30 turn/s^2, brake resistor on (stock setup): bus rise, resistor energy and peak power
  hard         120 turn/s^2, brake resistor off, no limits: the baseline draw and regen
  flux         holding, flux-braking start 1 V below the bus at 10 A/V: Id = -gain * (vbus - start), and
               I_bus rises by the copper loss 1.5 * R * Id^2 / vbus
  flux-stop    as hard, flux braking from 0.5 V above idle at 10 A/V: the bus rises less
  regen-limit  as hard, I_bus_soft_min = 0: the stop burns its energy with d-axis current (more than full
               current can burn at 10 turn/s, so braking torque is also clamped); no net regen, no
               controller windup, the move ends on target
  draw-cap     as hard with the brake on, I_bus_soft_max = 0.3 A: the acceleration draws at most that
The overvoltage trip is 30 V (RAM) during the test; a trip disarms, and the rotor coasts (back-EMF at
10 turn/s is about 8 V line to line, below the 24 V bus). RAM-only settings, restored at the end; ends IDLE.
Logs: logs/<stamp>_<serial>_regen-test.json + one capture CSV per move.

Usage (from the repo root):  python tools/regen_test.py
"""
import argparse
import datetime
import sys

import numpy as np

from capture import RISING, capture, read, save, setup, wait_done
from logfiles import rel
from xdrive import usb
from xdrive.props import odrv
from safety_test import CLOSED_LOOP, IDLE, POS, SETTINGS, TRAP, Bench, Unexpected

ACCEL = 30.0      # turn/s^2
HARD = 120.0      # turn/s^2
OV_TRIP = 30.0    # V, during the test
CHANNELS = ["vbus_voltage", "brake_resistor_current", "axis0.motor.I_bus", "axis0.motor.current_control.Iq_measured",
            "axis0.motor.current_control.Id_measured", "axis0.encoder.vel_estimate"]
REGEN_SETTINGS = SETTINGS + [
    "config.enable_brake_resistor", "config.dc_bus_overvoltage_trip_level", "axis0.controller.config.vel_limit",
    "axis0.motor.config.I_bus_soft_min", "axis0.motor.config.I_bus_soft_max",
    "axis0.motor.config.flux_brake_start_voltage", "axis0.motor.config.flux_brake_gain",
]


def move(b, vel, label, results, accel=ACCEL):
    """Out-and-back trap move at `vel`; the out move is captured. Returns the metrics of the out move."""
    b.set("axis0.trap_traj.config.vel_limit", vel)
    b.set("axis0.trap_traj.config.accel_limit", accel)
    b.set("axis0.trap_traj.config.decel_limit", accel)
    turns = vel * vel / accel + 0.3 * vel  # accelerate, cruise 0.3 s, decelerate
    start = b.get("axis0.encoder.pos_estimate")
    capacity = 8192 // len(CHANNELS)
    fields, types = setup(b.board, CHANNELS, decimation=10, trigger=("axis0.encoder.vel_estimate", RISING, 0.5),
                          post=capacity - 40)
    out = {"label": label, "vel": vel, "turns": round(turns, 2)}
    for target in (start + turns, start):
        b.event = f"{label}_to_{target - start:+.2f}"
        b.set("axis0.controller.input_pos", target)
        b.run(2 * vel / accel + 0.3 + 3.0,
              until=lambda r: b.v(r, "axis0.controller.trajectory_done") and abs(b.v(r, "axis0.encoder.pos_estimate") - target) < 0.01)
        b.run(0.3)
        if b.get("axis0.current_state") != CLOSED_LOOP:
            out["tripped"] = b.errors() | {"odrv": hex(b.get("error"))}
            break
        if target != start:
            out["final_error"] = round(b.get("axis0.encoder.pos_estimate") - target, 4)
    try:
        wait_done(b.board, 2.0)
    except Exception as ex:  # noqa: BLE001 - a trip before the trigger leaves nothing to analyze
        out["capture"] = repr(ex)
        results.append(out)
        print(f"  {label} {vel:g} turn/s: {out}")
        return out
    t, d, meta = read(b.board, fields, types)
    out["csv"] = rel(save(t, d, meta, b.serial, f"regen-{label}-{vel:g}"))
    dt = meta["period_s"]
    vbus = d["vbus_voltage"].astype(float)
    ibrake = d["brake_resistor_current"].astype(float)
    ibus = d["axis0.motor.I_bus"].astype(float)
    v = d["axis0.encoder.vel_estimate"].astype(float)
    idle = float(np.median(vbus[:30]))
    # Acceleration: up to the first frame at 90 % of the cruise speed; stop: from the last such frame.
    k = np.arange(len(v))
    fast = np.nonzero(v >= 0.9 * vel)[0]
    accel_w, decel_w = (k < fast[0]) & (v > 1.0), (k > fast[-1]) & (v > 0.5)
    stop = np.nonzero((k > fast[-1]) & (v < 0.2))[0]
    out.update(
        vbus_idle=round(idle, 2), vbus_peak=round(float(vbus.max()), 2), vbus_rise=round(float(vbus.max()) - idle, 2),
        brake_energy_J=round(float((ibrake ** 2).sum() * 2.0 * dt), 2),
        brake_peak_W=round(float((ibrake ** 2).max() * 2.0), 1),
        stop_bus_energy_J=round(float((ibus * vbus)[decel_w].sum() * dt), 2),
        ibus_accel=round(float(ibus[accel_w].mean()), 3), ibus_stop=round(float(ibus[decel_w].mean()), 3),
        id_min=round(float(d["axis0.motor.current_control.Id_measured"].min()), 2),
        vel_peak=round(float(v.max()), 2),
        stop_s=round(float((stop[0] - fast[-1]) * dt), 3) if len(stop) else None,
    )
    results.append(out)
    print(f"  {label} {vel:g} turn/s at {accel:g} turn/s^2: vbus {idle:.2f} -> peak {out['vbus_peak']} V, resistor "
          f"{out['brake_energy_J']} J (peak {out['brake_peak_W']} W), mean I_bus {out['ibus_accel']:+.3f} A accelerating, "
          f"{out['ibus_stop']:+.3f} A stopping ({out['stop_bus_energy_J']:+.2f} J), Id min {out['id_min']} A, stop {out['stop_s']} s"
          f"{', TRIPPED ' + str(out['tripped']) if 'tripped' in out else ''}")
    return out


def test_regen(b):
    b.set("axis0.controller.config.vel_limit", 11.0)  # an overshoot recovery runs at vel_limit; the guard is 12
    b.set("axis0.trap_traj.config.accel_limit", ACCEL)
    b.set("axis0.trap_traj.config.decel_limit", ACCEL)
    b.set("config.dc_bus_overvoltage_trip_level", OV_TRIP)
    b.clear_errors()
    b.set("axis0.controller.input_pos", b.get("axis0.encoder.pos_estimate"))
    b.closed_loop(POS, TRAP)
    results: list[dict[str, object]] = []

    print("brake")
    m = move(b, 10.0, "brake", results)
    b.check("30 turn/s^2 stop with the brake resistor: no trip", "tripped" not in m,
            f"vbus rise {m['vbus_rise']} V, mean I_bus while stopping {m['ibus_stop']:+.3f} A, resistor "
            f"{m['brake_energy_J']} J at up to {m['brake_peak_W']} W")

    print("hard")
    b.set("config.enable_brake_resistor", False)
    hard = move(b, 10.0, "hard", results, accel=HARD)
    b.check("120 turn/s^2 without limits: the stop regenerates (baseline)", "tripped" not in hard and hard["ibus_stop"] < -0.15,
            f"mean I_bus {hard['ibus_accel']:+.3f} A accelerating, {hard['ibus_stop']:+.3f} A stopping, vbus rise {hard['vbus_rise']} V")

    print("flux")  # the stand's rotor regenerates too little to lift the bus, so the start sits below it
    vbus = float(np.median([b.get("vbus_voltage") for _ in range(20)]))
    start, gain = round(vbus - 1.0, 2), 10.0
    t, d, meta = capture(b.board, CHANNELS, decimation=4)
    before = {k: float(np.mean(d[k])) for k in ("axis0.motor.I_bus", "axis0.motor.current_control.Id_measured")}
    b.set("axis0.motor.config.flux_brake_gain", gain)
    b.set("axis0.motor.config.flux_brake_start_voltage", start)
    b.run(0.3)
    t, d, meta = capture(b.board, CHANNELS, decimation=4)
    b.set("axis0.motor.config.flux_brake_start_voltage", float("inf"))
    save(t, d, meta, b.serial, "regen-flux-hold")
    vb, i_d, ibus = (float(np.mean(d[k])) for k in ("vbus_voltage", "axis0.motor.current_control.Id_measured", "axis0.motor.I_bus"))
    want_id = -gain * (vb - start)
    want_dibus = 1.5 * b.get("axis0.motor.config.phase_resistance") * (i_d ** 2 - before["axis0.motor.current_control.Id_measured"] ** 2) / vb
    b.check("flux braking: Id = -gain * (vbus - start), and its copper loss shows in I_bus",
            abs(i_d - want_id) < 0.1 * abs(want_id) and abs((ibus - before["axis0.motor.I_bus"]) - want_dibus) < 0.3 * want_dibus
            and b.get("axis0.current_state") == CLOSED_LOOP,
            f"Id {i_d:+.2f} A vs {want_id:+.2f}; I_bus {before['axis0.motor.I_bus']:+.3f} -> {ibus:+.3f} A "
            f"(+{ibus - before['axis0.motor.I_bus']:.3f} vs +{want_dibus:.3f} predicted)")

    print("flux-stop")
    start = round(hard["vbus_idle"] + 0.5, 2)
    b.set("axis0.motor.config.flux_brake_gain", 10.0)
    b.set("axis0.motor.config.flux_brake_start_voltage", start)
    m = move(b, 10.0, "flux-stop", results, accel=HARD)
    b.set("axis0.motor.config.flux_brake_start_voltage", float("inf"))
    b.check("flux braking from 0.5 V above idle (10 A/V) holds down the bus rise of the same stop",
            "tripped" not in m and m["vbus_rise"] < 0.6 * hard["vbus_rise"] and m["id_min"] < -3.0,
            f"vbus rise {m['vbus_rise']} V vs {hard['vbus_rise']} V, Id min {m['id_min']} A")

    print("regen-limit")
    b.set("axis0.motor.config.I_bus_soft_min", 0.0)
    m = move(b, 10.0, "regen-limit", results, accel=HARD)
    b.set("axis0.motor.config.I_bus_soft_min", float("-inf"))
    b.check("I_bus_soft_min = 0: the stop burns its energy (Id) instead of regenerating; no windup, ends on target",
            "tripped" not in m and m["ibus_stop"] > -0.05 and m["vbus_rise"] < 0.3 * hard["vbus_rise"] and m["id_min"] < -5.0
            and abs(m.get("final_error", 1)) < 0.01,
            f"mean I_bus while stopping {m['ibus_stop']:+.3f} A vs {hard['ibus_stop']:+.3f} A, vbus rise {m['vbus_rise']} V vs "
            f"{hard['vbus_rise']} V, Id min {m['id_min']} A, "
            f"stop {m['stop_s']} s vs {hard['stop_s']} s, final error {m.get('final_error')} turn")
    b.set("config.enable_brake_resistor", True)

    print("draw-cap")
    b.set("axis0.motor.config.I_bus_soft_max", 0.3)
    m = move(b, 10.0, "draw-cap", results, accel=HARD)
    b.check("I_bus_soft_max = 0.3 A caps the mean draw while accelerating; ends on target",
            "tripped" not in m and m["ibus_accel"] < 0.33 and hard["ibus_accel"] > 0.5 and abs(m.get("final_error", 1)) < 0.01,
            f"mean I_bus accelerating {m['ibus_accel']:+.3f} A vs {hard['ibus_accel']:+.3f} A uncapped; "
            f"final error {m.get('final_error')} turn")
    b.set("axis0.motor.config.I_bus_soft_max", float("inf"))
    b.set("axis0.requested_state", IDLE)
    return results


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    board = usb.connect()
    serial = format(board.get(odrv.serial_number), "X")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    b = Bench(board, stamp, serial, prefix="regen")
    saved = {p: b.get(p) for p in REGEN_SETTINGS}
    results, logs, abort = [], [], None
    try:
        b.set("axis0.requested_state", IDLE)
        b.idle_and_settle()
        results = test_regen(b)
        logs.append(rel(b.log("test")))
    except (Unexpected, KeyboardInterrupt, StopIteration, IndexError) as ex:
        abort = repr(ex)
        print(f"ABORT: {abort}")
    finally:
        def cleanup():
            board.call(odrv.capture.clear_channels())
            b.clear_errors()
        b.restore(saved, logs, cleanup)
    return b.report("regen-test", abort, logs, moves=results)


if __name__ == "__main__":
    sys.exit(main())
