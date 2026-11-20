#!/usr/bin/env python3
"""Draws the plotted figures of xdrive/docs/ as SVG.

  trap-trajectory.svg        one 3-turn trap move from a move_test.py or regress.py log (--move-log)
  input-filter.svg           step response of INPUT_MODE_POS_FILTER, simulated with the firmware's update
                             equations (Controller::update, update_filter_gains) at the 8 kHz control rate
  torque-mode-vel-limit.svg  the torque limit of torque control with enable_torque_mode_vel_limit
                             (limitVel in controller.cpp)
  correction-table.svg       an encoder correction table, from correction_table.py --save-json (--table)
  correction-ripple.svg      the 6 turn/s cruise of the 10-turn move of two regress.py move logs, without and
                             with the correction table (--ripple-logs OFF ON)

Usage (from the repo root):
  python xdrive/docs/figures/plots.py [--move-log L] [--table T] [--ripple-logs OFF ON]
Figures whose inputs aren't given are left as they are.
"""
import argparse
import csv
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent
CONTROL_HZ = 8000.0
DARK, BLUE, RED, GRAY = "#1f2937", "#2563eb", "#b91c1c", "#9ca3af"

plt.rcParams.update({
    "svg.fonttype": "none",       # text stays text, in the viewer's sans-serif font
    "svg.hashsalt": "xdrive",     # stable element ids, so reruns don't change the files
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.edgecolor": DARK,
    "axes.labelcolor": DARK,
    "xtick.color": DARK,
    "ytick.color": DARK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def save(fig, name):
    fig.savefig(OUT / name, format="svg", metadata={"Date": None}, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / name)


def trap_trajectory(log):
    rows = read_log(log)
    start = next(i for i, r in enumerate(rows) if r["event"] == "out +3")
    end = next(i for i, r in enumerate(rows) if r["event"] == "back -3")
    seg = rows[start:end]
    t0 = float(seg[0]["t"])
    t = [float(r["t"]) - t0 for r in seg]
    p0 = float(seg[0]["axis0.controller.pos_setpoint"])
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4.2), sharex=True)
    ax1.plot(t, [float(r["axis0.controller.pos_setpoint"]) - p0 for r in seg], color=BLUE, label="setpoint")
    ax1.plot(t, [float(r["axis0.encoder.pos_estimate"]) - p0 for r in seg], color=DARK, ls="--", label="measured")
    ax1.set_ylabel("position [turn]")
    ax1.legend(frameon=False, loc="lower right")
    ax2.plot(t, [float(r["axis0.controller.vel_setpoint"]) for r in seg], color=BLUE, label="setpoint")
    ax2.plot(t, [float(r["axis0.encoder.vel_estimate"]) for r in seg], color=DARK, lw=0.8, label="measured")
    ax2.set_ylabel("velocity [turn/s]")
    ax2.set_xlabel("time [s]")
    ax2.legend(frameon=False, loc="upper right")
    fig.suptitle("A 3-turn trap move: vel_limit 6 turn/s, accel and decel 5 turn/s² (DJI 10018)", fontsize=10)
    save(fig, "trap-trajectory.svg")


def read_log(path):
    with open(path) as f:
        next(f)  # host_start line
        return list(csv.DictReader(f))


def correction_table(path):
    d = json.load(open(path))
    counts = d["table_counts"]
    cpr = 16384
    x = [i / len(counts) for i in range(len(counts))]
    deg = [c / cpr * 360.0 for c in counts]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(x, deg, color=BLUE, lw=1.8)
    ax.axhline(0, color=GRAY, lw=0.6)
    ax.set_xlabel("rotor angle [turn]")
    ax.set_ylabel("correction [° mechanical]")
    ax.set_title(f"Encoder correction table, DJI 10018 test stand: {len(counts)} bins, "
                 f"{d['correction_rms_counts'] / cpr * 360:.2f}° rms, {d['correction_peak_counts'] / cpr * 360:.2f}° peak",
                 fontsize=10)
    save(fig, "correction-table.svg")


def cruise(rows):
    start = next(i for i, r in enumerate(rows) if r["event"] == "out +10")
    end = next(i for i, r in enumerate(rows) if r["event"] == "back -10")
    seg = [r for r in rows[start:end] if abs(float(r["axis0.controller.vel_setpoint"]) - 6.0) < 1e-3]
    p0 = float(seg[0]["axis0.encoder.pos_estimate"])
    pos = [float(r["axis0.encoder.pos_estimate"]) - p0 for r in seg]
    keep = [i for i, p in enumerate(pos) if p <= 2.0]
    return ([pos[i] for i in keep], [float(seg[i]["axis0.encoder.vel_estimate"]) for i in keep],
            [float(seg[i]["axis0.motor.current_control.Iq_measured"]) for i in keep])


def correction_ripple(off, on):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4.2), sharex=True)
    for path, color, label, lw in ((off, GRAY, "without the table", 1.0), (on, BLUE, "with the table", 1.6)):
        pos, vel, iq = cruise(read_log(path))
        ax1.plot(pos, vel, color=color, lw=lw, label=label)
        ax2.plot(pos, iq, color=color, lw=lw)
    ax1.set_ylabel("velocity [turn/s]")
    ax1.legend(frameon=False, loc="upper right", ncol=2)
    ax2.set_ylabel("Iq measured [A]")
    ax2.set_xlabel("rotor travel during the cruise [turn]")
    fig.suptitle("Cruising at 6 turn/s, DJI 10018 with an off-center magnet", fontsize=10)
    save(fig, "correction-ripple.svg")


def input_filter():
    dt = 1.0 / CONTROL_HZ
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4.2), sharex=True)
    for bw, color in ((2.0, BLUE), (8.0, DARK)):
        ki = 2.0 * min(bw, 0.25 * CONTROL_HZ)
        kp = 0.25 * ki * ki
        pos = vel = 0.0
        ts, ps, vs = [], [], []
        for n in range(int(1.5 * CONTROL_HZ)):
            accel = kp * (1.0 - pos) + ki * (0.0 - vel)
            vel += dt * accel
            pos += dt * vel
            ts.append(n * dt)
            ps.append(pos)
            vs.append(vel)
        ax1.plot(ts, ps, color=color, label=f"input_filter_bandwidth {bw:g} rad/s")
        ax2.plot(ts, vs, color=color)
    ax1.axhline(1.0, color=GRAY, lw=0.8, ls=":")
    ax1.set_ylabel("pos_setpoint [turn]")
    ax1.legend(frameon=False, loc="lower right")
    ax2.set_ylabel("vel_setpoint [turn/s]")
    ax2.set_xlabel("time [s]")
    fig.suptitle("INPUT_MODE_POS_FILTER: input_pos steps from 0 to 1 turn at t = 0 (computed)", fontsize=10)
    save(fig, "input-filter.svg")


def torque_mode_vel_limit():
    vel_limit, vel_gain, command = 8.0, 0.537, 2.0
    v = [x / 100.0 for x in range(-1200, 1201)]
    tmax = [(vel_limit - x) * vel_gain for x in v]
    tmin = [(-vel_limit - x) * vel_gain for x in v]
    out = [min(max(command, lo), hi) for lo, hi in zip(tmin, tmax)]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.plot(v, tmax, color=RED, lw=1, ls="--", label="limits: ±vel_limit − velocity, × vel_gain")
    ax.plot(v, tmin, color=RED, lw=1, ls="--")
    ax.plot(v, out, color=BLUE, lw=2, label=f"torque applied for input_torque = {command:g} Nm")
    ax.axhline(0, color=GRAY, lw=0.6)
    ax.axvline(0, color=GRAY, lw=0.6)
    ax.set_ylim(-12, 12)
    ax.set_xlabel("velocity [turn/s]")
    ax.set_ylabel("torque [Nm]")
    ax.legend(frameon=False, loc="lower left")
    ax.set_title(f"Torque control with enable_torque_mode_vel_limit: vel_limit {vel_limit:g} turn/s, "
                 f"vel_gain {vel_gain:g} Nm/(turn/s)", fontsize=10)
    save(fig, "torque-mode-vel-limit.svg")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--move-log", help="a move_test.py or regress.py move log with a 3-turn move")
    ap.add_argument("--table", help="a correction table JSON from correction_table.py --save-json")
    ap.add_argument("--ripple-logs", nargs=2, metavar=("OFF", "ON"), help="regress.py move logs without and with the table")
    args = ap.parse_args()
    if args.move_log:
        trap_trajectory(args.move_log)
    if args.table:
        correction_table(args.table)
    if args.ripple_logs:
        correction_ripple(*args.ripple_logs)
    input_filter()
    torque_mode_vel_limit()


if __name__ == "__main__":
    main()
