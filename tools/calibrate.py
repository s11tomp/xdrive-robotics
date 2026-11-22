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

Usage (from the repo root):  python tools/calibrate.py --motor --offset [--correction] [--save]
"""
import argparse
import datetime
import json
import math
import pathlib
import sys
import time
from typing import Any

from correction_table import read_table
from xdrive import report, usb
from xdrive.enums import AxisState
from xdrive.props import odrv

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
IDLE = AxisState.IDLE


def run_state(b, state, name, timeout):
    print(f"\n{name}: requesting state {state.value} ({state.name}) ...", flush=True)
    ax = odrv.axis0
    t0 = time.monotonic()
    b.set(ax.requested_state, state)
    time.sleep(0.3)
    while b.get(ax.current_state) is not IDLE:
        if time.monotonic() - t0 > timeout:
            b.set(ax.requested_state, IDLE)
            raise SystemExit(f"{name}: timed out after {timeout:.0f} s; axis set IDLE")
        time.sleep(0.1)
    e = {k: report.jsonable(v) for k, v in report.errors(b).items()}
    flags = {k: v["flags"] or v.get("unknown_bits") for k, v in e.items() if v["flags"] or v.get("unknown_bits")}
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

    b = usb.connect()
    ax = odrv.axis0
    mc, ec = ax.motor.config, ax.encoder.config
    serial = format(b.get(odrv.serial_number), "X")
    if b.get(ax.current_state) is not IDLE:
        raise SystemExit(f"axis0 is not IDLE (state {b.get(ax.current_state).name}); not calibrating.")
    rec: dict[str, Any] = {"t": datetime.datetime.now().astimezone().isoformat(), "action": "calibrate", "serial": serial,
           "argv": sys.argv[1:], "results": {}}

    if args.motor:
        run_state(b, AxisState.MOTOR_CALIBRATION, "motor calibration", 20)
        r: dict[str, Any] = {"phase_resistance": b.get(mc.phase_resistance), "phase_inductance": b.get(mc.phase_inductance)}
        b.set(mc.pre_calibrated, True)
        print(f"  R = {r['phase_resistance'] * 1000:.1f} mOhm, L = {r['phase_inductance'] * 1e6:.1f} uH "
              f"(v0.5.1 measured 56.2 mOhm, 25.8 uH); motor.config.pre_calibrated = True")
        rec["results"]["motor"] = r

    def offset():
        run_state(b, AxisState.ENCODER_OFFSET_CALIBRATION, "encoder offset calibration", 30)
        pp, cpr = b.get(mc.pole_pairs), b.get(ec.cpr)
        expected = b.get(ec.calib_scan_distance) / (pp * 2 * math.pi / cpr)
        resp = b.get(ax.encoder.calib_scan_response)
        off, off_f, direction = b.get(ec.phase_offset), b.get(ec.phase_offset_float), b.get(ec.direction)
        err_pct = (resp - expected) / expected * 100
        print(f"  phase_offset {off} (+{off_f:.3f}), direction {direction}, "
              f"scan {resp:.0f} counts vs {expected:.0f} expected ({err_pct:+.2f} %, "
              f"limit ±{b.get(ec.calib_range) * 100:.0f} %)")
        return {"phase_offset": off, "phase_offset_float": off_f, "direction": direction,
                "calib_scan_response": resp, "expected": expected, "response_error_pct": err_pct}

    if args.offset:
        rec["results"]["offset"] = offset()

    if args.correction:
        run_state(b, AxisState.ENCODER_CORRECTION_CALIBRATION, "encoder correction calibration", 90)
        enc = ax.encoder
        table = read_table(b)
        rms_c, peak_c, bins = b.get(enc.correction_rms), b.get(enc.correction_peak), b.get(enc.correction_bins)
        enabled = b.get(ec.correction_enabled)
        r = {"correction_rms_counts": rms_c, "correction_peak_counts": peak_c, "bins": bins,
             "enabled": enabled, "scan_turns": b.get(ec.correction_scan_turns)}
        deg = 360.0 / b.get(ec.cpr)
        print(f"  error rms {rms_c:.1f} counts ({rms_c * deg:.2f} deg), peak {peak_c:.1f} counts "
              f"({peak_c * deg:.2f} deg), {bins}/256 bins; correction_enabled = {enabled}")
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
        print("\nSaving: the board saves and REBOOTS; its startup sequence runs.")
        b.save()
        print("board back up after the save")
    b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
