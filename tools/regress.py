#!/usr/bin/env python3
"""Bench regression suite: run the standard tests on one board, compare with a baseline.

MOVES THE MOTOR (closed-loop hold, out-and-back moves of 1/3/10 turns at trap vel 6, ±0.2 Nm
virtual-weight steps). Each test leaves the axis IDLE; the suite ends IDLE.

Steps (each is an existing script, so its own logs and guards apply):
  1. dump_board.py               firmware version, config diff vs --compare, boot errors
     With --hold-at F (or a baseline that records one), move_to.py first puts the rotor at
     fractional turn F before steps 2 and 4: cogging makes hold noise and disturbance deflection
     depend on where the rotor rests, so runs compare only at the same angle.
  2. hold_ab.py --hold 15        hold noise: Iq setpoint/measured, Id, velocity, position std
  3. move_test.py --moves 1,3,10 peak currents, tracking error, final error; then from its CSV:
     analyze_settle metrics (median over segments) and analyze_ripple --locked 4.5 6.5
     (the 4x encoder-error ripple at cruise speed, and what's left without the angle-locked part)
  4. disturb_test.py --torque 0.2  peak deflection, recovery time, final error

Writes logs/<stamp>_<serial>_regress-<tag>.json. With --baseline FILE it prints each metric
next to the baseline and flags anything worse by more than the tolerance. --save-baseline
copies this run to configs/regress-baseline_<serial>.json, including its --hold-at angle, which
later runs against that baseline then use by default.

Usage (from the repo root):
  python tools/regress.py --tag fw-0.5.1-dev --save-baseline
  python tools/regress.py --tag fw-0.5.6 --baseline configs/regress-baseline_<serial>.json
"""
import argparse
import contextlib
import datetime
import io
import csv
import json
import math
import pathlib
import statistics
import subprocess
import sys

import numpy as np

import analyze_ripple
import analyze_settle

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
CONFIGS = WORKDIR / "configs"
PY = sys.executable

# metric -> (direction, relative tolerance, absolute floor). direction +1 = higher is worse.
CHECKS = {
    # Hold current noise is checked as |I| = sqrt(Iq^2 + Id^2): the phase-current sense noise isn't isotropic
    # (B and C are measured, A = -B-C), so its d/q split depends on the electrical angle where the hold
    # happens to stop. Iq_meas_std and Id_std alone are reported but not checked.
    "hold.Iq_sp_std": (1, 0.30, 0.02), "hold.I_meas_noise": (1, 0.30, 0.02),
    "hold.vel_std": (1, 0.30, 0.003), "hold.pos_std_counts": (1, 0.30, 0.3),
    "move.peak_abs_Iq_meas_A": (1, 0.20, 0.5), "move.max_tracking_error_turn": (1, 0.25, 0.005),
    "move.max_final_error_turn": (1, 0.50, 0.002),
    "settle.overshoot_counts": (1, 0.50, 2.0), "settle.settle_s": (1, 0.50, 0.05), "settle.residual_counts": (1, 0.50, 1.0),
    "settle.vel_err_rms": (1, 0.25, 0.02),
    "ripple.vel_err_rms": (1, 0.25, 0.02), "ripple.Iq_meas_rms": (1, 0.25, 0.2), "ripple.Id_meas_rms": (1, 0.25, 0.1),
    "ripple.peak_I_A": (1, 0.20, 0.5),
    "disturb.peak_deflection_counts": (1, 0.25, 3.0), "disturb.recovery_s": (1, 0.50, 0.1),
    "disturb.final_error_counts": (1, 0.50, 2.0),
}


def run(script, *args):
    """Run one of the bench scripts; return its stdout (and fail loudly if it fails)."""
    cmd = [PY, str(pathlib.Path(__file__).resolve().parent / script), *args]
    print(f"\n$ {' '.join(cmd[1:])}", flush=True)
    p = subprocess.run(cmd, cwd=WORKDIR, capture_output=True, text=True)
    sys.stdout.write("".join("  | " + ln + "\n" for ln in p.stdout.strip().splitlines()[-12:]))
    if p.returncode != 0:
        sys.stdout.write(p.stderr[-2000:])
        raise SystemExit(f"{script} failed (exit {p.returncode})")
    return p.stdout


def newest(pattern):
    hits = sorted(LOGS.glob(pattern))
    if not hits:
        raise SystemExit(f"no log matching {pattern}")
    return hits[-1]


def current_spikes(csv_path):
    """Closed-loop samples below 1 turn/s whose measured current jumps away from the command for one sample
    (|Id| > 1.5 A or |Iq_meas - Iq_setpoint| > 1.5 A). They happen sporadically on every firmware build so
    far, and a single one sets the peak-current metrics and adds ~0.05 A rms to the hold noise, so the count
    is reported next to them (not checked)."""
    rows = list(csv.reader(line for line in open(csv_path) if not line.startswith("#")))
    ix = {n: i for i, n in enumerate(rows[0])}
    n = 0
    for r in rows[1:]:
        try:
            if r[ix["axis0.current_state"]] != "8" or abs(float(r[ix["axis0.encoder.vel_estimate"]])) >= 1.0:
                continue
            idm = float(r[ix["axis0.motor.current_control.Id_measured"]])
            diq = float(r[ix["axis0.motor.current_control.Iq_measured"]]) - float(r[ix["axis0.motor.current_control.Iq_setpoint"]])
        except ValueError:
            continue
        n += abs(idm) > 1.5 or abs(diq) > 1.5
    return n


def ripple_metrics(csv_path, lo=4.5, hi=6.5):
    """analyze_ripple's angle-locked report, captured instead of printed."""
    import csv as _csv
    with open(csv_path) as f:
        r = _csv.reader(f)
        next(r)
        h = next(r)
        rows = list(r)
    ix = {k: i for i, k in enumerate(h)}

    def c(k):
        return np.array([1.0 if x[ix[k]] == "True" else 0.0 if x[ix[k]] == "False" else float(x[ix[k]]) for x in rows])

    moving = (c("axis0.controller.trajectory_done") == 0) & (c("axis0.current_state") == 8)
    vsp, vest = c("axis0.controller.vel_setpoint"), c("axis0.encoder.vel_estimate")
    th = c("axis0.encoder.pos_abs") / 16384 * 2 * math.pi
    iqm, idm = c("axis0.motor.current_control.Iq_measured"), c("axis0.motor.current_control.Id_measured")
    signals = {"vel_err t/s": vest - vsp, "Iq_meas A": iqm, "Id_meas A": idm}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = analyze_ripple.locked_report(th, vsp, moving, signals, iqm, idm, lo, hi, [4, 8], 0.75, 4)
    return res or {}, buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True, help="name for this run, e.g. the firmware under test")
    ap.add_argument("--baseline", help="regress JSON to compare against")
    ap.add_argument("--save-baseline", action="store_true", help="store this run as configs/regress-baseline_<serial>.json")
    ap.add_argument("--hold", type=float, default=15.0)
    ap.add_argument("--hold-at", type=float, help="fractional turn (0..1) to move the rotor to before the hold and "
                                                     "disturbance tests (default: the baseline's)")
    ap.add_argument("--compare", help="settings file the board's config must match (passed to dump_board.py)")
    args = ap.parse_args()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"regress-{args.tag}-{stamp}"
    out = {"tag": args.tag, "t": datetime.datetime.now().astimezone().isoformat(), "metrics": {}, "files": {}}
    M = out["metrics"]
    baseline_doc = json.loads(pathlib.Path(args.baseline).read_text()) if args.baseline else {}
    hold_at = args.hold_at if args.hold_at is not None else baseline_doc.get("hold_at")
    out["hold_at"] = hold_at

    # 1. Dump.
    run("dump_board.py", "--label", f"{label}-dump", *(["--compare", args.compare] if args.compare else []))
    dump_path = newest(f"*_{label}-dump_dump.json")
    d = json.loads(dump_path.read_text())
    v = d["values"]
    out["serial"] = d["meta"].get("serial") or format(v.get("serial_number", 0), "X")
    out["fw_version"] = f"{v.get('fw_version_major')}.{v.get('fw_version_minor')}.{v.get('fw_version_revision')}" + \
                        ("-dev" if v.get("fw_version_unreleased") else "")
    out["config_diffs"] = d["diff_vs_expected"]
    out["boot_errors"] = {k: e for k, e in d["errors_decoded"].items()
                          if isinstance(e, dict) and e.get("flags")}
    out["files"]["dump"] = str(dump_path.relative_to(WORKDIR))

    # 2. Hold noise.
    if hold_at is not None:
        run("move_to.py", str(hold_at))
    run("hold_ab.py", "--hold", str(args.hold), "--variant", "hold:", "--label", f"{label}-hold")
    hp = newest(f"*_{label}-hold.json")
    h = json.loads(hp.read_text())
    if h.get("abort_reason"):
        raise SystemExit(f"hold aborted: {h['abort_reason']}")
    for k in ("Iq_sp_std", "Iq_meas_std", "Id_std", "vel_std", "pos_std_counts"):
        M[f"hold.{k}"] = h["results"][0][k]
    M["hold.I_meas_noise"] = math.hypot(M["hold.Iq_meas_std"], M["hold.Id_std"])
    M["hold.abs_Iq_meas_mean"] = abs(h["results"][0]["Iq_meas_mean"])
    M["hold.current_spikes"] = current_spikes(hp.with_suffix(".csv"))
    out["files"]["hold"] = str(hp.relative_to(WORKDIR))

    # 3. Moves + settle + ripple.
    run("move_test.py", "--moves", "1,3,10", "--label", f"{label}-move")
    mp = newest(f"*_{label}-move.json")
    m = json.loads(mp.read_text())
    out["move_abort_reason"] = m.get("abort_reason")
    out["move_final_errors"] = {k: e for k, e in (m.get("final_errors") or {}).items() if e.get("flags")}
    segs = [s for s in m["segments"] if s["segment"].startswith(("out", "back"))]
    M["move.peak_abs_Iq_meas_A"] = max(s["peak_abs_Iq_measured_A"] for s in segs)
    M["move.peak_abs_vel_turn_s"] = max(s["peak_abs_vel_turn_s"] for s in segs)
    M["move.max_tracking_error_turn"] = max(s["max_tracking_error_turn"] for s in segs)
    M["move.max_final_error_turn"] = max(s["final_error_turn"] for s in segs)
    csv_path = mp.with_suffix(".csv")
    M["move.current_spikes"] = current_spikes(csv_path)
    sm = [analyze_settle.metrics(dd, 10.0) for _, dd in analyze_settle.load(str(csv_path))]
    M["settle.overshoot_counts"] = statistics.median(x["overshoot"] for x in sm)
    M["settle.settle_s"] = statistics.median(x["settle_s"] for x in sm)
    M["settle.residual_counts"] = statistics.median(x["residual"] for x in sm)
    M["settle.vel_err_rms"] = statistics.median(x["vel_err_rms"] for x in sm)
    rip, rip_text = ripple_metrics(csv_path)
    out["ripple_report"] = rip_text
    for k in ("vel_err_rms", "Iq_meas_rms", "Id_meas_rms", "peak_I_A",
              "vel_err_rms_unlocked", "Iq_meas_rms_unlocked", "Id_meas_rms_unlocked", "peak_I_A_unlocked"):
        if k in rip:
            M[f"ripple.{k}"] = rip[k]
    out["files"]["move"] = str(mp.relative_to(WORKDIR))

    # 4. Disturbance.
    if hold_at is not None:
        run("move_to.py", str(hold_at))
    run("disturb_test.py", "--torque", "0.2", "--label", f"{label}-disturb")
    dp = newest(f"*_{label}-disturb.json")
    dt = json.loads(dp.read_text())
    out["disturb_abort_reason"] = dt.get("abort_reason")
    st = [s for s in dt["steps"] if s["torque_Nm"] != 0]
    M["disturb.peak_deflection_counts"] = max(abs(s["peak_deflection_counts"]) for s in st)
    M["disturb.recovery_s"] = max(s["recovered_within_band_s"] for s in dt["steps"])
    M["disturb.final_error_counts"] = max(abs(s["final_error_counts"]) for s in dt["steps"])
    out["files"]["disturb"] = str(dp.relative_to(WORKDIR))

    M = out["metrics"] = {k: (round(v, 5) if isinstance(v, float) else v) for k, v in M.items()}
    path = LOGS / f"{stamp}_{out['serial']}_regress-{args.tag}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")

    # Report.
    problems = []
    if out["config_diffs"]:
        problems.append(f"config differs from --compare: {out['config_diffs']}")
    for name, val in (("boot errors", out["boot_errors"]), ("move abort", out["move_abort_reason"]),
                      ("move errors", out["move_final_errors"]), ("disturb abort", out["disturb_abort_reason"])):
        if val:
            problems.append(f"{name}: {val}")
    base = baseline_doc.get("metrics", {})
    print(f"\n=== regress {args.tag} (fw {out['fw_version']}, serial {out['serial']})" +
          (f" vs {args.baseline}" if base else ""))
    print(f"  {'metric':34s} {'this run':>10s} {'baseline':>10s}  {'change':>8s}")
    for k, val in M.items():
        b = base.get(k)
        flag = ""
        if b is not None and k in CHECKS and isinstance(val, (int, float)):
            sign, rel, floor = CHECKS[k]
            worse = (val - b) * sign
            if worse > max(rel * abs(b), floor):
                flag = "  <-- WORSE"
                problems.append(f"{k}: {val} vs baseline {b}")
        ch = f"{(val - b) / abs(b) * 100:+7.0f}%" if b not in (None, 0) else ""
        print(f"  {k:34s} {val:10.4g} {b if b is not None else '':>10}  {ch:>8s}{flag}")
    print(f"\nWrote {path.relative_to(WORKDIR)}")
    if args.save_baseline:
        bp = CONFIGS / f"regress-baseline_{out['serial']}.json"
        bp.write_text(json.dumps(out, indent=2) + "\n")
        print(f"Saved baseline {bp.relative_to(WORKDIR)}")
    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    print("\nRESULT: OK" + (" (no regressions vs baseline)" if base else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
