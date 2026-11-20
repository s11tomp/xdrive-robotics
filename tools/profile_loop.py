#!/usr/bin/env python3
"""Control-loop CPU time and thread stack headroom (firmware v0.5.2+). MOTOR HOLDS (closed loop, no move).

Arms <odrv>.task_timers_armed N times while axis0 holds position in closed loop; each arming makes the
firmware time one control iteration (TIM13, in 168 MHz cycles). Reports per-task length (mean / max),
the busy span of the iteration (first start to last end) against the 125 us loop period, and
system_stats stack high-water marks against the stack sizes. Ends IDLE. Logged to logs/.

Usage (from the repo root):  python tools/profile_loop.py [--samples 200]
"""
import argparse
import datetime
import json
import pathlib
import statistics
import sys
import time

from dump_board import connect

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
CLOCK_HZ = 168e6
PERIOD_CYCLES = CLOCK_HZ / 8000.0          # 21000 cycles per control iteration
WRAP = 65536                               # sample_TIM13() returns uint16


def timers(obj, prefix):
    """{name: TaskTimer remote object} under obj.task_times."""
    tt = obj.task_times
    return {f"{prefix}{k}": getattr(tt, k) for k in tt._remote_attributes}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=200)
    args = ap.parse_args()
    dev = connect(timeout=10)
    ax = dev.axis0
    serial = format(dev.serial_number, "X")
    tmap = {**timers(dev, ""), **timers(ax, "axis0.")}
    stats = dev.system_stats
    stacks = {k[len("max_stack_usage_"):]: (getattr(stats, k), getattr(stats, "stack_size_" + k[len("max_stack_usage_"):], None))
              for k in stats._remote_attributes if k.startswith("max_stack_usage_")}

    lengths = {k: [] for k in tmap}
    busy = []
    try:
        ax.requested_state = 8
        time.sleep(0.8)
        if ax.current_state != 8:
            raise SystemExit(f"axis0 did not enter closed loop (state {ax.current_state})")
        for _ in range(args.samples):
            dev.task_timers_armed = True
            t0 = time.monotonic()
            while dev.task_timers_armed and time.monotonic() - t0 < 0.5:
                pass
            starts, ends = [], []
            ref = None
            for k, t in tmap.items():
                ln, st, en = t.length, t.start_time, t.end_time
                if ln == 0 and st == 0:
                    continue                      # task didn't run this iteration
                lengths[k].append(ln)
                ref = st if ref is None else ref
                starts.append((st - ref) % WRAP)
                ends.append((en - ref) % WRAP)
            if starts:
                busy.append(max(ends) - min(starts))
    finally:
        ax.requested_state = 1
    us = lambda c: c / CLOCK_HZ * 1e6
    print(f"board {serial}, {args.samples} control iterations timed while holding in closed loop")
    rows = []
    for k, v in lengths.items():
        if v:
            rows.append((k, statistics.mean(v), max(v)))
    for k, mean, mx in sorted(rows, key=lambda r: -r[1]):
        print(f"  {k:45s} mean {us(mean):6.2f} us   max {us(mx):6.2f} us")
    b_mean, b_max = statistics.mean(busy), max(busy)
    print(f"busy span per iteration: mean {us(b_mean):.1f} us, max {us(b_max):.1f} us "
          f"of {us(PERIOD_CYCLES):.0f} us ({b_mean / PERIOD_CYCLES * 100:.0f} % mean, {b_max / PERIOD_CYCLES * 100:.0f} % max)")
    print("thread stacks (max used / size, bytes):")
    for name, (used, size) in stacks.items():
        print(f"  {name:10s} {used:6d} / {size if size is not None else '?'}"
              + (f"   ({used / size * 100:.0f} %)" if size else ""))
    print(f"min heap free: {stats.min_heap_space} bytes; uptime {stats.uptime / 1000:.0f} s")
    out = {"t": datetime.datetime.now().astimezone().isoformat(), "serial": serial, "samples": args.samples,
           "tasks_us": {k: {"mean": us(m), "max": us(x)} for k, m, x in rows},
           "busy_us": {"mean": us(b_mean), "max": us(b_max)}, "period_us": us(PERIOD_CYCLES),
           "stacks": {k: {"max_used": u, "size": s} for k, (u, s) in stacks.items()},
           "min_heap_space": stats.min_heap_space}
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    LOGS.mkdir(exist_ok=True)
    (LOGS / f"{stamp}_{serial}_profile-loop.json").write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
