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
import csv, datetime, sys, time

from dump_board import connect
import pathlib
LOGS = pathlib.Path.cwd() / "logs"
label = sys.argv[1] if len(sys.argv) > 1 else "run"
d = connect(timeout=10); a = d.axis0; c = a.controller
saved = (c.config.input_mode, a.trap_traj.config.vel_limit, a.trap_traj.config.accel_limit, a.trap_traj.config.decel_limit, c.config.vel_limit)
rows = []; t0 = time.monotonic()
def sample(ev=""):
    rows.append((round(time.monotonic()-t0, 4), d.vbus_voltage, d.ibus, d.brake_resistor_current, a.encoder.vel_estimate,
                 a.motor.current_control.Iq_measured, a.motor.spike_count, a.current_state, a.error, ev))
    if a.error or abs(rows[-1][4]) > 22: raise RuntimeError(f"error {a.error:#x} or overspeed")
try:
    a.requested_state = 1; time.sleep(0.3); d.clear_errors()
    c.config.control_mode = 3; c.config.input_mode = 5; c.config.vel_limit = 18.0
    a.trap_traj.config.vel_limit = 15.0; a.trap_traj.config.accel_limit = 30.0; a.trap_traj.config.decel_limit = 30.0
    a.requested_state = 8; time.sleep(0.5); start = a.encoder.pos_estimate
    for tgt, ev in ((start + 30, "out"), (start, "back")):
        print(f"phase {ev} start, uptime {d.system_stats.uptime}", flush=True); c.input_pos = tgt; t = time.monotonic()
        while time.monotonic() - t < 3.2: sample(ev)
    print(f"hold start, uptime {d.system_stats.uptime}", flush=True); n0 = a.motor.spike_count; t = time.monotonic()
    while time.monotonic() - t < 10: sample("hold")
    n1 = a.motor.spike_count; print(f"hold end, uptime {d.system_stats.uptime}; requesting IDLE", flush=True)
finally:
    a.requested_state = 1
    c.config.input_mode, a.trap_traj.config.vel_limit, a.trap_traj.config.accel_limit, a.trap_traj.config.decel_limit, c.config.vel_limit = saved
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
path = f"{LOGS}/{stamp}_{d.serial_number:X}_brake-check-{label}.csv"
with open(path, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["t","vbus","ibus","brake_current","vel","Iq_meas","spike_count","state","axis_error","event"]); w.writerows(rows)
mv = [r for r in rows if r[9] in ("out", "back")]
print(f"{label}: vbus {min(r[1] for r in mv):.2f}-{max(r[1] for r in mv):.2f} V, ibus min {min(r[2] for r in mv):+.2f} A, "
      f"brake current peak {max(r[3] for r in mv):.2f} A (samples >0.1 A: {sum(1 for r in mv if r[3] > 0.1)}), "
      f"peak vel {max(abs(r[4]) for r in mv):.1f}; hold glitches {n1-n0} in 10 s -> {path}")
