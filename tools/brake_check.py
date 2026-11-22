#!/usr/bin/env python3
"""Hard-braking check.  *** THIS MOVES THE MOTOR (30 turns out and back at 15 turn/s, 30 turn/s^2). ***

Closes the loop, runs out and back with hard stops, then holds 10 s. Samples vbus, ibus,
odrv.brake_resistor_current, velocity, Iq and motor.spike_count (firmware with the spike
diagnostics). Prints the bus-voltage range, brake-current peak and the glitch count during the hold;
logs every sample to logs/<stamp>_<serial>_brake-check-<label>.csv. Ends IDLE.

This check froze the board in 3 of 3 runs on firmware with the brake bridge held static at zero duty (the
measured-current spike investigation); 0 of 7 without it.

Usage (from the repo root):  python tools/brake_check.py <label>
"""
import csv
import datetime
import pathlib
import sys
import time

from xdrive import paths, usb
from xdrive.enums import AxisState, ControlMode, InputMode
from xdrive.props import odrv

LOGS = pathlib.Path.cwd() / "logs"


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    b = usb.connect()
    a = odrv.axis0
    c, tt = a.controller, a.trap_traj.config
    restore = ["axis0.controller.config.input_mode", "axis0.trap_traj.config.vel_limit",
               "axis0.trap_traj.config.accel_limit", "axis0.trap_traj.config.decel_limit",
               "axis0.controller.config.vel_limit"]
    saved = {p: paths.get(b, p) for p in restore}
    rows = []
    t0 = time.monotonic()

    def sample(ev=""):
        r = b.get_many([odrv.vbus_voltage, odrv.ibus, odrv.brake_resistor_current, a.encoder.vel_estimate,
                        a.motor.current_control.Iq_measured, a.motor.spike_count, a.current_state, a.error]).values
        rows.append((round(time.monotonic() - t0, 4), *r[:6], r[6].value, int(r[7]), ev))
        if r[7] or abs(r[3]) > 22:
            raise RuntimeError(f"error {int(r[7]):#x} or overspeed")

    try:
        b.set(a.requested_state, AxisState.IDLE)
        time.sleep(0.3)
        b.call(odrv.clear_errors())
        b.set(c.config.control_mode, ControlMode.POSITION_CONTROL)
        b.set(c.config.input_mode, InputMode.TRAP_TRAJ)
        b.set(c.config.vel_limit, 18.0)
        b.set(tt.vel_limit, 15.0)
        b.set(tt.accel_limit, 30.0)
        b.set(tt.decel_limit, 30.0)
        b.set(a.requested_state, AxisState.CLOSED_LOOP_CONTROL)
        time.sleep(0.5)
        start = b.get(a.encoder.pos_estimate)
        for tgt, ev in ((start + 30, "out"), (start, "back")):
            print(f"phase {ev} start, uptime {b.get(odrv.system_stats.uptime)}", flush=True)
            b.set(c.input_pos, tgt)
            t = time.monotonic()
            while time.monotonic() - t < 3.2:
                sample(ev)
        print(f"hold start, uptime {b.get(odrv.system_stats.uptime)}", flush=True)
        n0 = b.get(a.motor.spike_count)
        t = time.monotonic()
        while time.monotonic() - t < 10:
            sample("hold")
        n1 = b.get(a.motor.spike_count)
        print(f"hold end, uptime {b.get(odrv.system_stats.uptime)}; requesting IDLE", flush=True)
    finally:
        b.set(a.requested_state, AxisState.IDLE)
        for p, v in saved.items():
            paths.set(b, p, v)
    serial = format(b.get(odrv.serial_number), "X")
    b.close()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = LOGS / f"{stamp}_{serial}_brake-check-{label}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "vbus", "ibus", "brake_current", "vel", "Iq_meas", "spike_count", "state", "axis_error", "event"])
        w.writerows(rows)
    mv = [r for r in rows if r[9] in ("out", "back")]
    print(f"{label}: vbus {min(r[1] for r in mv):.2f}-{max(r[1] for r in mv):.2f} V, ibus min {min(r[2] for r in mv):+.2f} A, "
          f"brake current peak {max(r[3] for r in mv):.2f} A (samples >0.1 A: {sum(1 for r in mv if r[3] > 0.1)}), "
          f"peak vel {max(abs(r[4]) for r in mv):.1f}; hold glitches {n1 - n0} in 10 s -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
