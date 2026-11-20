#!/usr/bin/env python3
"""Run calibration states one at a time and report the results. THE MOTOR MOVES.

  --motor       AXIS_STATE_MOTOR_CALIBRATION (4): measures R and L (a beep, little or no rotation),
                then sets motor.config.pre_calibrated = True.
  --offset      AXIS_STATE_ENCODER_OFFSET_CALIBRATION (7): sweeps ~1/3 turn each way. Reports
                the phase offset, direction and scan response vs the expected counts.
  --correction  AXIS_STATE_ENCODER_CORRECTION_CALIBRATION (14, this firmware): one mechanical turn
                each way at the calibration current (~25 s). Reports rms/peak error and bins, writes
                the table to logs/<stamp>_<serial>_correction-table.json, then re-runs --offset.
  --save        save_configuration() at the end (v0.5.6: the board reboots and runs its startup
                sequence; if startup calibration is enabled, the motor moves again).

Steps run in the order motor, offset, correction. Each waits for the axis to return to IDLE,
prints the axis/motor/encoder errors, and stops on any error. Logged to logs/actions.jsonl.

Usage (from the repo root):  python xdrive/tools/calibrate.py --motor --offset [--correction] [--save]
"""
import argparse
import datetime
import json
import math
import pathlib
import sys
import time

import odrive

from dump_board import decode_bitmask, connect

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
IDLE, MOTOR_CAL, OFFSET_CAL, CORRECTION_CAL = 1, 4, 7, 14


def errors(ax):
    return {"axis": decode_bitmask(ax.error, "AXIS_ERROR_"),
            "motor": decode_bitmask(ax.motor.error, "MOTOR_ERROR_"),
            "encoder": decode_bitmask(ax.encoder.error, "ENCODER_ERROR_"),
            "controller": decode_bitmask(ax.controller.error, "CONTROLLER_ERROR_")}


def run_state(ax, state, name, timeout):
    print(f"\n{name}: requesting state {state} ...", flush=True)
    t0 = time.monotonic()
    ax.requested_state = state
    time.sleep(0.3)
    while ax.current_state != IDLE:
        if time.monotonic() - t0 > timeout:
            ax.requested_state = IDLE
            raise SystemExit(f"{name}: timed out after {timeout:.0f} s; axis set IDLE")
        time.sleep(0.1)
    e = errors(ax)
    flags = {k: v["flags"] for k, v in e.items() if v["flags"]}
    print(f"{name}: done in {time.monotonic() - t0:.1f} s" + (f"; ERRORS {flags}" if flags else "; no errors"))
    if flags:
        raise SystemExit(1)
    return e


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--motor", action="store_true")
    ap.add_argument("--offset", action="store_true")
    ap.add_argument("--correction", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    if not (args.motor or args.offset or args.correction):
        ap.error("choose at least one of --motor --offset --correction")

    dev = connect(timeout=10)
    ax = dev.axis0
    serial = format(dev.serial_number, "X")
    if ax.current_state != IDLE:
        raise SystemExit(f"axis0 is not IDLE (state {ax.current_state}); not calibrating.")
    rec = {"t": datetime.datetime.now().astimezone().isoformat(), "action": "calibrate", "serial": serial,
           "argv": sys.argv[1:], "results": {}}

    if args.motor:
        run_state(ax, MOTOR_CAL, "motor calibration", 20)
        r = {"phase_resistance": ax.motor.config.phase_resistance, "phase_inductance": ax.motor.config.phase_inductance}
        ax.motor.config.pre_calibrated = True
        print(f"  R = {r['phase_resistance'] * 1000:.1f} mOhm, L = {r['phase_inductance'] * 1e6:.1f} uH "
              f"(v0.5.1 measured 56.2 mOhm, 25.8 uH); motor.config.pre_calibrated = True")
        rec["results"]["motor"] = r

    def offset():
        run_state(ax, OFFSET_CAL, "encoder offset calibration", 30)
        enc = ax.encoder
        pp, cpr = ax.motor.config.pole_pairs, enc.config.cpr
        expected = enc.config.calib_scan_distance / (pp * 2 * math.pi / cpr)
        resp = enc.calib_scan_response
        r = {"phase_offset": enc.config.phase_offset, "phase_offset_float": enc.config.phase_offset_float,
             "direction": enc.config.direction, "calib_scan_response": resp, "expected": expected,
             "response_error_pct": (resp - expected) / expected * 100}
        print(f"  phase_offset {r['phase_offset']} (+{r['phase_offset_float']:.3f}), direction {r['direction']}, "
              f"scan {resp:.0f} counts vs {expected:.0f} expected ({r['response_error_pct']:+.2f} %, "
              f"limit ±{enc.config.calib_range * 100:.0f} %)")
        return r

    if args.offset:
        rec["results"]["offset"] = offset()

    if args.correction:
        run_state(ax, CORRECTION_CAL, "encoder correction calibration", 90)
        enc = ax.encoder
        table = [enc.get_correction(i) for i in range(256)]
        r = {"correction_rms_counts": enc.correction_rms, "correction_peak_counts": enc.correction_peak,
             "bins": enc.correction_bins, "enabled": enc.config.correction_enabled,
             "scan_turns": enc.config.correction_scan_turns}
        deg = 360.0 / enc.config.cpr
        print(f"  error rms {r['correction_rms_counts']:.1f} counts ({r['correction_rms_counts'] * deg:.2f} deg), "
              f"peak {r['correction_peak_counts']:.1f} counts ({r['correction_peak_counts'] * deg:.2f} deg), "
              f"{r['bins']}/256 bins; correction_enabled = {r['enabled']}")
        # Harmonic content of the table (which rotor-angle harmonics the error has)
        harm = []
        for h in range(1, 13):
            c = sum(t * math.cos(2 * math.pi * h * (k + 0.5) / 256) for k, t in enumerate(table)) * 2 / 256
            s = sum(t * math.sin(2 * math.pi * h * (k + 0.5) / 256) for k, t in enumerate(table)) * 2 / 256
            harm.append((h, math.hypot(c, s), math.degrees(math.atan2(s, c))))
        top = sorted(harm, key=lambda x: -x[1])[:4]
        print("  largest harmonics (per turn): " + ", ".join(f"{h}x {a * deg:.2f} deg @ {p:.0f}" for h, a, p in top))
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        out = LOGS / f"{stamp}_{serial}_correction-table.json"
        out.write_text(json.dumps({"serial": serial, **r, "table_counts": table,
                                   "harmonics_counts": [{"h": h, "amp": a, "phase_deg": p} for h, a, p in harm]},
                                  indent=2) + "\n")
        print(f"  table -> {out.relative_to(WORKDIR)}")
        r["file"] = str(out.relative_to(WORKDIR))
        rec["results"]["correction"] = r
        rec["results"]["offset_after_correction"] = offset()

    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    if args.save:
        print("\nSaving: the board saves and REBOOTS (v0.5.6); its startup sequence runs.")
        try:
            dev.save_configuration()
        except Exception as ex:
            print(f"(link dropped during save, as expected: {type(ex).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
