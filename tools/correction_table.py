#!/usr/bin/env python3
"""Read, smooth, save or restore the encoder correction table. No motion.

  --show                 print the table's harmonic content (default if nothing else is given)
  --save-json FILE       write the board's table to FILE
  --load-json FILE       write a saved table (table_counts) to the board
  --smooth H             keep only harmonics 1..H per turn and write the result to the board

Why smoothing: the open-loop calibration also records the rotor being pulled ahead/behind the field
by cogging (36x and 42x per turn on the 10018: 36 slots, 42 magnets). That is not encoder error;
in the table it becomes a false ±4-9 deg electrical commutation error. The magnet-placement error
is low order (1x, 2x, 4x, 8x).

Writes are RAM only; save with set_config.py --save (the board saves and reboots). Logged to logs/actions.jsonl.
Usage (from the repo root): python tools/correction_table.py --smooth 12
"""
import argparse
import datetime
import json
import math
import pathlib
import sys

from logfiles import log_action, logs_dir, rel
from xdrive import usb
from xdrive.board import Board
from xdrive.props import odrv

N = 256


def harmonics(t: list[float], hmax: int) -> list[tuple[int, float, float]]:
    out = []
    for h in range(1, hmax + 1):
        c = sum(v * math.cos(2 * math.pi * h * (k + 0.5) / N) for k, v in enumerate(t)) * 2 / N
        s = sum(v * math.sin(2 * math.pi * h * (k + 0.5) / N) for k, v in enumerate(t)) * 2 / N
        out.append((h, c, s))
    return out


def smooth(t: list[float], hmax: int) -> list[float]:
    hs = harmonics(t, hmax)
    return [sum(c * math.cos(2 * math.pi * h * (k + 0.5) / N) + s * math.sin(2 * math.pi * h * (k + 0.5) / N)
                for h, c, s in hs) for k in range(N)]


def rms(x: list[float]) -> float:
    return math.sqrt(sum(v * v for v in x) / len(x))


def show(t: list[float], cpr: int) -> None:
    deg = 360.0 / cpr
    hs = harmonics(t, 64)
    top = sorted(hs, key=lambda x: -math.hypot(x[1], x[2]))[:8]
    low = smooth(t, 12)
    print(f"table rms {rms(t):.1f} counts ({rms(t) * deg:.2f} deg); harmonics 1-12 rms {rms(low):.1f}; "
          f"rest rms {rms([a - b for a, b in zip(t, low)]):.2f} counts")
    print("largest harmonics: " + ", ".join(f"{h}x {math.hypot(c, s):.1f}" for h, c, s in top))


def read_table(board: Board) -> list[float]:
    return [board.call(odrv.axis0.encoder.get_correction(index=i)) for i in range(N)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save-json")
    ap.add_argument("--load-json")
    ap.add_argument("--smooth", type=int, metavar="H")
    args = ap.parse_args()

    new: list[float] | None = None
    if args.load_json:
        new = json.loads(pathlib.Path(args.load_json).read_text())["table_counts"]
        if new is None or len(new) != N:
            sys.exit(f"{args.load_json}: table_counts must have {N} entries")

    board = usb.connect()
    enc = odrv.axis0.encoder
    cpr = board.get(enc.config.cpr)
    serial = format(board.get(odrv.serial_number), "X")
    table = read_table(board)
    print(f"board {serial}: correction_enabled = {board.get(enc.config.correction_enabled)}")
    show(table, cpr)
    rec: dict[str, object] = {"t": datetime.datetime.now().astimezone().isoformat(), "action": "correction_table",
           "serial": serial, "argv": sys.argv[1:]}

    if args.save_json:
        pathlib.Path(args.save_json).write_text(json.dumps({"serial": serial, "table_counts": table}, indent=2) + "\n")
        print(f"saved -> {args.save_json}")
    if args.smooth:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        before = logs_dir() / f"{stamp}_{serial}_correction-table-before-smooth.json"
        before.write_text(json.dumps({"serial": serial, "table_counts": table}, indent=2) + "\n")
        new = smooth(new or table, args.smooth)
        rec["before"] = rel(before)
        print(f"\nsmoothed to harmonics 1..{args.smooth} (original kept in {rel(before)}):")
    if new is not None:
        for i, v in enumerate(new):
            board.call(enc.set_correction(index=i, val=float(v)))
        back = read_table(board)
        if max(abs(a - b) for a, b in zip(back, new)) >= 1e-3:
            sys.exit("the table read back differs from the one written")
        show(back, cpr)
        print("written to the board (RAM only).")
        rec["written_rms_counts"] = rms(back)
    log_action(rec)
    board.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
