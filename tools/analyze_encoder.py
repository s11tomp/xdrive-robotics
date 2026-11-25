#!/usr/bin/env python3
"""Look for encoder glitches in a sample.py CSV.

Unwraps the raw 14-bit `axis0.encoder.pos_abs`, then for each sample compares
it with the straight line between its neighbours (time-weighted). Smooth motion,
even a brisk hand flick, stays within a few tens of counts of that line at
~150 Hz. A one-sample position jump (corrupted SPI frame) sticks out by its full
size. Also reports how far the raw reading strays from the firmware's filtered
pos_estimate.

Usage:  python tools/analyze_encoder.py logs/<file>.csv [--threshold 100]
"""
import argparse
import statistics as st
import sys

from logfiles import read_columns

CPR = 16384


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--threshold", type=float, default=100, help="glitch threshold in counts (default 100 ≈ 2.2°)")
    args = ap.parse_args()

    col = {h: v.tolist() for h, v in read_columns(args.csv).items()}
    t, raw = col["t"], col["axis0.encoder.pos_abs"]

    # Unwrap raw counts across the 0/16383 boundary
    x = [raw[0]]
    for a, b in zip(raw, raw[1:]):
        x.append(x[-1] + ((b - a + CPR / 2) % CPR) - CPR / 2)

    dev = []
    for i in range(1, len(x) - 1):
        w = (t[i] - t[i - 1]) / (t[i + 1] - t[i - 1])
        dev.append((t[i], x[i] - (x[i - 1] + w * (x[i + 1] - x[i - 1]))))
    absdev = sorted(abs(d) for _, d in dev)
    glitches = [(ti, d) for ti, d in dev if abs(d) > args.threshold]

    turns = (max(x) - min(x)) / CPR
    vel = [(x[i + 1] - x[i]) / (t[i + 1] - t[i]) / CPR for i in range(len(x) - 1)]
    print(f"{len(x)} samples over {t[-1] - t[0]:.1f} s; travelled span {turns:.2f} turns; "
          f"peak |speed| {max(abs(v) for v in vel):.2f} turn/s")
    print(f"deviation from neighbour line (counts): median {st.median(absdev):.1f}  "
          f"p99 {absdev[int(0.99 * (len(absdev) - 1))]:.1f}  max {absdev[-1]:.1f}")
    print(f"glitches > {args.threshold:.0f} counts: {len(glitches)}")
    for ti, d in glitches[:20]:
        print(f"  t={ti:7.3f} s  {d:+.0f} counts ({d / CPR * 360:+.1f}°)")

    # Raw vs filtered estimate (pos_estimate is in turns, unwrapped, offset by an arbitrary constant)
    est = [p * CPR for p in col["axis0.encoder.pos_estimate"]]
    off = st.median(xi - ei for xi, ei in zip(x, est))
    gap = sorted(abs(xi - ei - off) for xi, ei in zip(x, est))
    print(f"|raw - pos_estimate| (counts): median {st.median(gap):.1f}  p99 {gap[int(0.99 * (len(gap) - 1))]:.1f}  max {gap[-1]:.1f}")
    errs = {h: sorted({int(v) for v in vs if v}) for h, vs in col.items() if h.endswith("error")}
    print("nonzero errors:", {k: [hex(v) for v in vs] for k, vs in errs.items() if vs} or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
