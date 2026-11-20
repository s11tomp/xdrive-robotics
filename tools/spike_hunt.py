#!/usr/bin/env python3
"""Count single-sample measured-current spikes while holding.  *** MOTOR HOLDS (small moves between positions). ***

Holds axis0 in closed loop (position control, passthrough) and reads only
motor.current_control.Id_measured and Iq_measured in a tight loop (~1-2 kHz over USB), so a
glitch that lasts one 125 us control period is caught far more often than by the ~200 Hz,
20-field bench samplers. A spike is a reading that differs from both neighbors by more than
--threshold while the neighbors agree within 0.4 A.

With --elec DEG, the rotor first moves to the nearest position at that electrical angle (the
firmware's own phase: offset, direction, pole pairs and cpr read from the board), so the scenario
is the same wherever the rotor rests. With --positions, the rotor steps to each offset (turns, relative to the start) with a slow trap
move and holds there for --duration seconds; spikes are counted per position. Ends IDLE.

Firmware with the spike diagnostics (motor.spike_count, get_spike_n/db/dc) also counts every armed
control period whose current vector jumps by more than motor.spike_threshold, at the full 8 kHz;
the last 32 events per position are logged with their phase-B/phase-C changes. --quiet holds
without reading currents over USB (only the firmware counter). --adc1 off stops ADC1's
free-running scan for the hold (restored on exit).
Logged to logs/<stamp>_<serial>_spike-hunt.csv (+ .json).

Usage (from the repo root):
  python tools/spike_hunt.py --duration 60
  python tools/spike_hunt.py --elec 10 --duration 60     # the reproduction scenario
  python tools/spike_hunt.py --duration 30 --positions 0,0.125,0.25,0.375,0.5,0.625,0.75,0.875
"""
import argparse
import csv
import datetime
import json
import pathlib
import sys
import time

from dump_board import connect

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
CLOSED_LOOP, IDLE = 8, 1


def find_spikes(ts, xs, threshold):
    out = []
    for i in range(1, len(xs) - 1):
        d = xs[i] - (xs[i - 1] + xs[i + 1]) / 2
        if abs(d) > threshold and abs(xs[i - 1] - xs[i + 1]) < 0.4:
            out.append((ts[i], xs[i - 1], xs[i], xs[i + 1]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duration", type=float, default=60.0, help="seconds of fast reading per position")
    ap.add_argument("--positions", default="0", help="comma-separated offsets in turns from the start position")
    ap.add_argument("--elec", type=float, default=None, help="first move to this electrical angle [deg]; offsets are relative to it")
    ap.add_argument("--threshold", type=float, default=1.0, help="spike threshold in A")
    ap.add_argument("--quiet", action="store_true", help="no USB current reads during the hold (firmware counter only)")
    ap.add_argument("--adc1", choices=("on", "off"), default="on", help="ADC1 free-running scan during the hold")
    args = ap.parse_args()
    dev = connect(timeout=10)
    ax = dev.axis0
    cc = ax.motor.current_control
    serial = format(dev.serial_number, "X")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = {"input_mode": ax.controller.config.input_mode, "trap_vel": ax.trap_traj.config.vel_limit}
    rows, results, abort = [], [], None
    t0 = time.monotonic()
    try:
        ax.requested_state = IDLE
        time.sleep(0.3)
        dev.clear_errors()
        ax.controller.config.control_mode = 3
        ax.controller.config.input_mode = 5          # trap traj for the steps between positions
        ax.trap_traj.config.vel_limit = 1.0
        ax.requested_state = CLOSED_LOOP
        time.sleep(0.5)
        if ax.current_state != CLOSED_LOOP:
            raise RuntimeError(f"no closed loop: state {ax.current_state}, axis error {ax.error:#x}")
        start = ax.encoder.pos_estimate
        if args.elec is not None:
            # phase = 2*pi*pp/cpr * (count - phase_offset - phase_offset_float) * direction (encoder.cpp)
            e = ax.encoder.config
            cpr, pp = e.cpr, ax.motor.config.pole_pairs
            base = e.phase_offset + e.phase_offset_float + e.direction * args.elec / 360 * cpr / pp
            period = cpr / pp
            target = base + round((start * cpr - base) / period) * period
            start = target / cpr
        for off in (float(x) for x in args.positions.split(",")):
            ax.controller.input_pos = start + off
            t_move = time.monotonic()
            while not ax.controller.trajectory_done and time.monotonic() - t_move < 10:
                time.sleep(0.02)
            time.sleep(0.5)
            pos = ax.encoder.pos_estimate
            ts, ids, iqs = [], [], []
            dev.set_adc1_scan(args.adc1 == "on")
            c0 = ax.motor.spike_count
            end = time.monotonic() + args.duration
            while args.quiet and time.monotonic() < end:
                time.sleep(0.05)
            while not args.quiet and time.monotonic() < end:
                t = time.monotonic() - t0
                i_d = cc.Id_measured
                i_q = cc.Iq_measured
                ts.append(t); ids.append(i_d); iqs.append(i_q)
                rows.append((round(t, 5), off, i_d, i_q))
            c1 = ax.motor.spike_count
            dev.set_adc1_scan(True)
            events = [{"n": ax.motor.get_spike_n(k), "dB": round(ax.motor.get_spike_db(k), 3),
                       "dC": round(ax.motor.get_spike_dc(k), 3)} for k in range(max(c0, c1 - 32), c1)]
            if ax.current_state != CLOSED_LOOP or ax.error:
                raise RuntimeError(f"left closed loop at offset {off}: axis error {ax.error:#x}")
            sd, sq = find_spikes(ts, ids, args.threshold), find_spikes(ts, iqs, args.threshold)
            rate_hz = len(ts) / args.duration if ts else 0.0
            e = ax.encoder.config
            elec = ((pos * e.cpr - e.phase_offset - e.phase_offset_float) * ax.motor.config.pole_pairs * 360 / e.cpr
                    * e.direction) % 360
            res = {"offset_turn": off, "mech_deg": round((pos % 1.0) * 360, 1), "elec_deg": round(elec, 1), "reads": len(ts),
                   "read_rate_hz": round(rate_hz, 1), "spikes_Id": len(sd), "spikes_Iq": len(sq),
                   "spikes_per_min": round((len(sd) + len(sq)) / args.duration * 60, 2),
                   "adc1": args.adc1, "quiet": args.quiet,
                   "fw_spikes": c1 - c0, "fw_spikes_per_s": round((c1 - c0) / args.duration, 2), "fw_events": events,
                   "examples": [{"field": f, "t": round(s[0], 4), "prev_now_next": [round(v, 3) for v in s[1:]]}
                                for f, ss in (("Id", sd), ("Iq", sq)) for s in ss[:5]]}
            results.append(res)
            print(f"offset {off:+.3f} turn (mech {res['mech_deg']:5.1f} deg, elec {res['elec_deg']:5.1f} deg): {len(ts)} reads at {rate_hz:.0f} Hz, "
                  f"spikes Id {len(sd)}, Iq {len(sq)} ({res['spikes_per_min']}/min); "
                  f"firmware {c1 - c0} jumps ({res['fw_spikes_per_s']}/s), adc1 {args.adc1}")
    except (RuntimeError, KeyboardInterrupt) as ex:
        abort = repr(ex)
        print(f"ABORT: {abort}")
    finally:
        try:
            ax.requested_state = IDLE
            dev.set_adc1_scan(True)
            ax.controller.config.input_mode = saved["input_mode"]
            ax.trap_traj.config.vel_limit = saved["trap_vel"]
        except Exception as ex:  # USB gone: the only stop left is the PSU
            print(f"!!! Could not command IDLE ({ex!r}). Press OUT on the PSU.")
    LOGS.mkdir(exist_ok=True)
    base = LOGS / f"{stamp}_{serial}_spike-hunt"
    with base.with_suffix(".csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "offset_turn", "Id_measured", "Iq_measured"])
        w.writerows(rows)
    base.with_suffix(".json").write_text(json.dumps(
        {"t": datetime.datetime.now().astimezone().isoformat(), "serial": serial, "argv": sys.argv[1:],
         "threshold_A": args.threshold, "abort": abort, "results": results}, indent=2) + "\n")
    print(f"axis IDLE -> {base.relative_to(WORKDIR)}.csv/.json")
    return 1 if abort else 0


if __name__ == "__main__":
    sys.exit(main())
