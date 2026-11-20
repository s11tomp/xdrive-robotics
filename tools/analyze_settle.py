#!/usr/bin/env python3
"""Step / settle metrics per move segment for move_test.py logs.

For each "out"/"back" segment:
  - accel/decel tracking: rms and peak of (vel_estimate - vel_setpoint) while the
    trajectory runs (velocity, because logged positions are ~1 ms skewed)
  - overshoot past the target after trajectory_done (counts, in the move direction)
  - settle time: from trajectory_done until |pos - target| stays within --band counts
  - residual: mean |pos - target| over the last 0.2 s of the segment
  - hold noise: Iq_setpoint std over that same last 0.2 s
Prints one row per segment and the median over segments, so runs with different
gains can be compared side by side.

Usage:  python tools/analyze_settle.py logs/<a>.csv [logs/<b>.csv ...] [--band 10]
"""
import argparse
import csv
import statistics as st

import numpy as np

CPR = 16384


def load(path):
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        h = next(r)
        rows = list(r)
    ix = {k: i for i, k in enumerate(h)}

    def c(k, rs):
        return np.array([1.0 if x[ix[k]] == "True" else 0.0 if x[ix[k]] == "False" else float(x[ix[k]]) for x in rs])

    segs, cur = [], None
    for row in rows:
        ev = row[ix["event"]]
        if ev:
            cur = [ev, []]
            segs.append(cur)
        if cur:
            cur[1].append(row)
    return [(name, {k: c(k, rs) for k in ix if k != "event"}) for name, rs in segs
            if name.startswith(("out", "back"))]


def metrics(d, band):
    t = d["t"]
    done = d["axis0.controller.trajectory_done"] > 0
    i_done = int(np.argmax(done & (t - t[0] > 0.05)))
    target = d["axis0.controller.input_pos"][i_done]
    start = d["axis0.encoder.pos_estimate"][0]
    direction = np.sign(target - start) or 1.0
    run = slice(0, i_done)
    ve = (d["axis0.encoder.vel_estimate"] - d["axis0.controller.vel_setpoint"])[run]
    e = (d["axis0.encoder.pos_estimate"][i_done:] - target) * CPR
    ts = t[i_done:] - t[i_done]
    outside = np.nonzero(np.abs(e) > band)[0]
    settle = ts[outside[-1] + 1] if len(outside) and outside[-1] + 1 < len(ts) else (0.0 if not len(outside) else float("nan"))
    tail = ts > ts[-1] - 0.2
    return {
        "vel_err_rms": float(np.sqrt(np.mean(ve ** 2))) if len(ve) else float("nan"),
        "vel_err_peak": float(np.max(np.abs(ve))) if len(ve) else float("nan"),
        "overshoot": float(max(0.0, np.max(direction * e))),
        "settle_s": float(settle),
        "residual": float(np.mean(np.abs(e[tail]))),
        "hold_iq_std": float(np.std(d["axis0.motor.current_control.Iq_setpoint"][i_done:][tail])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--band", type=float, default=10.0, help="settle band in counts (default 10 ≈ 0.22°)")
    args = ap.parse_args()
    cols = ["vel_err_rms", "vel_err_peak", "overshoot", "settle_s", "residual", "hold_iq_std"]
    print(f"{'segment':>12} {'velErr rms':>10} {'velErr pk':>9} {'overshoot':>9} {'settle s':>8} "
          f"{'resid':>6} {'hold Iq σ':>9}   (counts; settle band ±{args.band:g})")
    for path in args.csv:
        print(f"-- {path}")
        rows = []
        for name, d in load(path):
            m = metrics(d, args.band)
            rows.append(m)
            print(f"{name:>12} {m['vel_err_rms']:10.3f} {m['vel_err_peak']:9.3f} {m['overshoot']:9.1f} "
                  f"{m['settle_s']:8.3f} {m['residual']:6.1f} {m['hold_iq_std']:9.3f}")
        if rows:
            med = {k: st.median(r[k] for r in rows) for k in cols}
            print(f"{'median':>12} {med['vel_err_rms']:10.3f} {med['vel_err_peak']:9.3f} {med['overshoot']:9.1f} "
                  f"{med['settle_s']:8.3f} {med['residual']:6.1f} {med['hold_iq_std']:9.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
