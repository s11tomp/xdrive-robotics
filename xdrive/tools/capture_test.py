#!/usr/bin/env python3
"""Bench test of the firmware's high-rate capture (odrv.capture). No motion: it never touches the axis.

  sample clock    n_evt_control_loop (the control-loop counter) steps by exactly `decimation` per sample
  types           float32, uint32, int32 and bool channels match the USB reads
  triggers        rising and falling (on test_property, written over USB), manual,
                  with post_trigger samples after the trigger sample and pre-trigger samples before it
  rejections      endpoint 0, a function, a uint64, a 9th channel, start() without channels or with a
                  level trigger on a missing channel
  cost            control-loop time of capture_update with 8 channels (task timers), and readout time
Leaves the capture cleared and test_property restored. Log: logs/<stamp>_<serial>_capture-test.json.

Usage (from the repo root):  python xdrive/tools/capture_test.py
"""
import datetime
import json
import sys
import time

import numpy as np

from capture import ARMED, DONE, FALLING, IDLE, MANUAL, RISING, capture, read, setup, wait_done
from dump_board import connect
from sample import LOGS, WORKDIR

LOOP = "n_evt_control_loop"
CPU_HZ = 168e6


def main():
    dev = connect(timeout=10)
    serial = format(dev.serial_number, "X")
    c = dev.capture
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    test_property = dev.test_property
    try:
        print("rejections")
        c.clear_channels()
        check("start() without channels fails", not c.start())
        fn_id = dev._remote_attributes["clear_errors"]._trigger_id
        refused = [i for i, eid in (("endpoint 0", 0), ("clear_errors()", fn_id), ("serial_number (uint64)",
                   dev._remote_attributes["serial_number"]._id), ("readout endpoint", c.readout_endpoint))
                   if not c.add_channel(eid)]
        check("add_channel refuses endpoint 0, a function, a uint64, the readout endpoint", len(refused) == 4
              and c.n_channels == 0, f"refused {refused}")
        loop_id = dev._remote_attributes[LOOP]._id
        added = sum(c.add_channel(loop_id) for _ in range(9))
        check("8 channels at most", added == 8 and c.n_channels == 8 and c.capacity == 1024,
              f"added {added}, capacity {c.capacity}")
        c.clear_channels()
        c.add_channel(loop_id)
        c.trigger_mode, c.trigger_channel = RISING, 1
        check("level trigger on a missing channel fails", not c.start())
        c.clear_channels()

        print("sample clock")
        for decimation, fields in ((1, [LOOP]), (4, [LOOP, "vbus_voltage"])):
            t, d, meta = capture(dev, fields, decimation=decimation)
            steps = np.diff(d[LOOP].astype(np.int64))
            capacity = 8192 // len(fields)
            check(f"decimation {decimation}: counter steps by {decimation}, full buffer",
                  (steps == decimation).all() and meta["n_samples"] == capacity and meta["trigger_index"] == 0,
                  f"steps {sorted(set(steps.tolist()))}, {meta['n_samples']} samples, readout {meta['readout_s']} s")
        vbus = dev.vbus_voltage
        check("float32 channel matches the USB read", abs(float(d["vbus_voltage"].mean()) - vbus) < 0.5,
              f"{float(d['vbus_voltage'].mean()):.2f} V vs {vbus:.2f} V")

        print("types")
        fields = ["axis0.encoder.shadow_count", "axis0.encoder.is_ready", "axis0.controller.config.control_mode"]
        usb = [dev.axis0.encoder.shadow_count, dev.axis0.encoder.is_ready, dev.axis0.controller.config.control_mode]
        t, d, meta = capture(dev, fields, decimation=8)
        got = [int(d[f][-1]) for f in fields]
        check("int32, bool and uint8 channels match the USB reads", abs(got[0] - usb[0]) < 50 and got[1:] == [int(usb[1]), usb[2]],
              f"capture {got} vs USB {[usb[0], int(usb[1]), usb[2]]}")

        dev.test_property = 1234
        before = (dev.test_property, dev.axis0.controller.config.control_mode, dev.axis0.controller.config.pos_gain)
        t, d, meta = capture(dev, ["test_property", "axis0.controller.config.control_mode",
                                   "axis0.controller.config.pos_gain"], decimation=8)
        after = (dev.test_property, dev.axis0.controller.config.control_mode, dev.axis0.controller.config.pos_gain)
        got = (int(d["test_property"][-1]), int(d["axis0.controller.config.control_mode"][-1]),
               float(d["axis0.controller.config.pos_gain"][-1]))
        check("capturing read-write properties reads them and leaves them unchanged", before == after == got,
              f"before {before}, after {after}, captured {got}")

        print("triggers")
        for mode, before, after, post in ((RISING, 0, 5, 100), (FALLING, 5, 0, 10)):
            name = "rising" if mode == RISING else "falling"
            dev.test_property = before
            fields, props = setup(dev, [LOOP, "test_property"], trigger=("test_property", mode, 2.5), post=post)
            time.sleep(0.2)
            armed = c.state == ARMED
            dev.test_property = after
            wait_done(dev, 2.0)
            t, d, meta = read(dev, fields, props)
            k, x = meta["trigger_index"], d["test_property"]
            check(f"{name}: stays armed until the USB write crosses 2.5, {post} samples follow, pre-trigger kept",
                  armed and x[k] == after and x[k - 1] == before and meta["n_samples"] - 1 - k == post and k > 1000,
                  f"armed {armed}, values around the trigger {x[k - 2:k + 2].tolist()}, trigger_index {k}")

        fields, props = setup(dev, [LOOP], trigger=(None, MANUAL, 0.0), post=50)
        time.sleep(0.2)
        armed = c.state == ARMED
        n0 = dev.n_evt_control_loop
        c.trigger()
        wait_done(dev, 2.0)
        t, d, meta = read(dev, fields, props)
        k = meta["trigger_index"]
        check("manual: waits for trigger(), 50 samples follow, pre-trigger kept", armed and int(d[LOOP][k]) >= n0
              and k == meta["n_samples"] - 51 and k > 1000, f"armed {armed}, trigger_index {k}")

        print("cost")
        fields, props = setup(dev, [LOOP] * 8, trigger=(None, MANUAL, 0.0))
        lengths = []
        for _ in range(50):
            dev.task_timers_armed = True
            t0 = time.monotonic()
            while dev.task_timers_armed and time.monotonic() - t0 < 0.5:
                pass
            lengths.append(dev.task_times.capture_update.length)
        us = np.array(lengths) / CPU_HZ * 1e6
        check("8 channels cost under 10 % of the 125 us control period", us.max() < 12.5,
              f"capture_update mean {us.mean():.1f} us, max {us.max():.1f} us")
        c.clear_channels()
        check("clear_channels stops the capture", c.state == IDLE and c.n_channels == 0, f"state {c.state}")
    finally:
        dev.test_property = test_property
        c.clear_channels()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = {"t": datetime.datetime.now().astimezone().isoformat(), "serial": serial, "checks": checks}
    path = LOGS / f"{stamp}_{serial}_capture-test.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    failed = [ch for ch in checks if not ch["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed -> {path.relative_to(WORKDIR)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
