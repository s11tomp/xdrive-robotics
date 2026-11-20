#!/usr/bin/env python3
"""Angle-locked ripple vs speed for a move_test.py log.

For samples where a trajectory is running, bins by |vel_setpoint| and fits
const + k-per-turn harmonic (k = --harmonic, default 4) of the raw encoder
angle + linear speed trend to: velocity error, Iq_setpoint and Iq_measured.
Compares the measured Iq ripple with the "loop tracks an encoder error"
model:  I = J * (2*pi*k*speed)^2 * E / Kt.

--locked LO HI adds an estimate of what a per-angle encoder correction table
would remove: all ripple locked to the rotor angle over |vel_setpoint| LO..HI,
fitted per direction and per narrow speed band (the loop's response to a fixed
angle error changes amplitude and phase with speed and direction). It also
prints the pooled 4x Id phase per direction: compare it across logs to check
that the encoder error stays put (a table only helps if it does).

Usage:  python xdrive/tools/analyze_ripple.py logs/<move>.csv [--J 5e-4 --E-deg 1.44 --Kt 0.107]
        python xdrive/tools/analyze_ripple.py logs/<move>.csv --bw 2000 --locked 4.5 7
"""
import argparse
import csv
import math

import numpy as np


def locked_report(th, vsp, moving, signals, iqm, idm, lo, hi, harmonics, band, k_phase):
    """Angle-locked share of the ripple over |vsp| in [lo, hi): what an encoder correction table could remove.

    Prints a report and returns the numbers: <signal>_rms and <signal>_rms_unlocked (signal = vel_err, Iq_meas,
    Id_meas), peak_I_A and peak_I_A_unlocked, id_phase_deg per direction. Empty dict if no band had enough samples.
    """
    sel = moving & (np.abs(vsp) >= lo) & (np.abs(vsp) < hi)
    n_h = 2 * len(harmonics)
    used = np.zeros(len(vsp), bool)
    ssr_before = {name: 0.0 for name in signals}
    ssr_after = {name: 0.0 for name in signals}
    locked = {name: np.zeros(len(vsp)) for name in signals}
    p_before = p_after = 0
    for d in (1, -1):
        b = lo
        while b < hi:
            m = sel & (np.sign(vsp) == d) & (np.abs(vsp) >= b) & (np.abs(vsp) < b + band)
            b += band
            if m.sum() < 2 + n_h + 6:
                continue
            used |= m
            base = [np.ones(m.sum()), vsp[m]]
            A0 = np.column_stack(base)
            A = np.column_stack(base + [f(k * th[m]) for k in harmonics for f in (np.cos, np.sin)])
            p_before += A0.shape[1]
            p_after += A.shape[1]
            for name, y in signals.items():
                r0 = y[m] - A0 @ np.linalg.lstsq(A0, y[m], rcond=None)[0]
                cf = np.linalg.lstsq(A, y[m], rcond=None)[0]
                r1 = y[m] - A @ cf
                ssr_before[name] += float(r0 @ r0)
                ssr_after[name] += float(r1 @ r1)
                locked[name][m] = A[:, 2:] @ cf[2:]
    n = int(used.sum())
    hs = ",".join(str(k) for k in harmonics)
    print(f"\nAngle-locked share, |vel_sp| {lo:g}-{hi:g} turn/s, harmonics {hs} per turn, "
          f"fitted per direction x {band:g} turn/s band ({n} of {int(sel.sum())} samples)")
    if n == 0:
        print("  no band has enough samples")
        return {}
    res = {"samples": n}
    print("  signal          ripple rms   without the angle-locked part   (rms corrected for fitted params)")
    for name in signals:
        before = math.sqrt(ssr_before[name] / max(n - p_before, 1))
        after = math.sqrt(ssr_after[name] / max(n - p_after, 1))
        print(f"  {name:14s}  {before:8.3f}      {after:8.3f}   ({before / after:4.1f}x)")
        key = name.split()[0]
        res[f"{key}_rms"], res[f"{key}_rms_unlocked"] = before, after
    iq_names = [s for s in signals if s.startswith("Iq")]
    id_names = [s for s in signals if s.startswith("Id")]
    if iq_names and id_names:
        iql, idl = locked[iq_names[0]], locked[id_names[0]]
        pk0 = np.hypot(iqm[used], idm[used]).max()
        pk1 = np.hypot(iqm[used] - iql[used], idm[used] - idl[used]).max()
        print(f"  peak |I| = sqrt(Iq²+Id²): {pk0:.2f} A measured -> {pk1:.2f} A without the angle-locked part")
        res["peak_I_A"], res["peak_I_A_unlocked"] = float(pk0), float(pk1)
    # Pooled phase per direction: a fingerprint of where the error sits on the rotor.
    out = []
    for d in (1, -1):
        m = sel & (np.sign(vsp) == d)
        if m.sum() < 15:
            out.append(f"dir {d:+d}: too few samples")
            continue
        A = np.column_stack([np.ones(m.sum()), vsp[m], np.cos(k_phase * th[m]), np.sin(k_phase * th[m])])
        cf = np.linalg.lstsq(A, idm[m], rcond=None)[0]
        ph = math.degrees(math.atan2(cf[3], cf[2]))
        out.append(f"dir {d:+d}: ±{math.hypot(cf[2], cf[3]):.2f} A at {ph:6.1f}° (rotor angle {ph / k_phase:5.1f}°)")
        res[f"id_phase_deg_dir{d:+d}"] = ph
    print(f"  Id {k_phase}x per direction, pooled over the range: " + " | ".join(out))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--harmonic", type=int, default=4)
    ap.add_argument("--bin", type=float, default=1.0, help="speed bin width, turn/s")
    ap.add_argument("--J", type=float, default=5e-4, help="rotor inertia kg·m² (default: a DJI 10018 with its prop hub)")
    ap.add_argument("--E-deg", type=float, default=1.44, help="encoder error amplitude, degrees")
    ap.add_argument("--Kt", type=float, default=0.107, help="true torque constant Nm/A")
    ap.add_argument("--bw", type=float, default=1000.0, help="current_control_bandwidth rad/s (for the Id model)")
    ap.add_argument("--R", type=float, default=0.0562, help="phase resistance ohm")
    ap.add_argument("--L", type=float, default=25.8e-6, help="phase inductance H")
    ap.add_argument("--pp", type=int, default=21, help="pole pairs")
    ap.add_argument("--locked", nargs=2, type=float, metavar=("LO", "HI"),
                    help="also estimate the ripple an encoder correction table would remove, over |vel_setpoint| LO..HI")
    ap.add_argument("--locked-harmonics", default="4,8", help="angle harmonics per motor turn for --locked")
    ap.add_argument("--band", type=float, default=0.75, help="speed band width for --locked, turn/s")
    args = ap.parse_args()

    with open(args.csv) as f:
        r = csv.reader(f)
        next(r)
        h = next(r)
        rows = list(r)
    ix = {k: i for i, k in enumerate(h)}

    def c(k):
        return np.array([1.0 if x[ix[k]] == "True" else 0.0 if x[ix[k]] == "False" else float(x[ix[k]]) for x in rows])

    moving = (c("axis0.controller.trajectory_done") == 0) & (c("axis0.current_state") == 8)
    vsp, vest = c("axis0.controller.vel_setpoint"), c("axis0.encoder.vel_estimate")
    th = c("axis0.encoder.pos_abs") / 16384 * 2 * math.pi
    iqs, iqm = c("axis0.motor.current_control.Iq_setpoint"), c("axis0.motor.current_control.Iq_measured")
    idm = c("axis0.motor.current_control.Id_measured")
    lam = args.Kt / (1.5 * args.pp)
    k, E = args.harmonic, math.radians(args.E_deg)

    print(f"{k}x-per-turn ripple amplitude by speed (model: J={args.J:g}, E={args.E_deg}°, Kt={args.Kt})")
    print("  |speed| bin    n   vel_err ±t/s  Iq_sp ±A  Iq_meas ±A  model ±A  peak|Iq_sp|  peak|Iq_meas|"
          f"   Id ±A  Id model ±A (bw {args.bw:g})  peak|I|")
    top = np.abs(vsp[moving]).max() if moving.any() else 0
    lo = 0.5
    while lo < top:
        hi = lo + args.bin
        m = moving & (np.abs(vsp) >= lo) & (np.abs(vsp) < hi)
        if m.sum() >= 12:
            A = np.column_stack([np.ones(m.sum()), np.cos(k * th[m]), np.sin(k * th[m]), vsp[m]])
            amps = []
            for y in (vest - vsp, iqs, iqm, idm):
                cf, *_ = np.linalg.lstsq(A, y[m], rcond=None)
                amps.append(math.hypot(cf[1], cf[2]))
            mid = (lo + min(hi, top)) / 2
            model = args.J * (2 * math.pi * k * mid) ** 2 * E / args.Kt
            w4 = 2 * math.pi * k * mid
            vd = 2 * math.pi * mid * args.pp * lam * math.sin(args.pp * E)
            id_model = vd / abs(complex(args.R, w4 * args.L)) / abs(1 + args.bw / (1j * w4))
            ipk = np.hypot(iqm[m], idm[m]).max()
            print(f"  {lo:4.1f}-{hi:4.1f}  {m.sum():5d}     {amps[0]:6.3f}     {amps[1]:6.2f}    {amps[2]:6.2f}    "
                  f"{model:6.2f}     {np.abs(iqs[m]).max():6.2f}       {np.abs(iqm[m]).max():6.2f}"
                  f"   {amps[3]:6.2f}      {id_model:6.2f}            {ipk:6.2f}")
        lo = hi
    if args.locked:
        signals = {"vel_err t/s": vest - vsp, "Iq_meas A": iqm, "Id_meas A": idm}
        harmonics = [int(x) for x in args.locked_harmonics.split(",")]
        locked_report(th, vsp, moving, signals, iqm, idm, args.locked[0], args.locked[1],
                      harmonics, args.band, k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
