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

Usage (from the repo root):  python tools/capture_test.py
"""
import datetime
import json
import sys
import time

import numpy as np

from capture import ARMED, DONE, FALLING, IDLE, LOGS, MANUAL, RISING, WORKDIR, capture, read, setup, wait_done
from xdrive import usb
from xdrive.enums import ControlMode
from xdrive.props import odrv

LOOP = "n_evt_control_loop"
CPU_HZ = 168e6


def main():
    b = usb.connect()
    serial = format(b.get(odrv.serial_number), "X")
    c = odrv.capture
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    def add(eid):
        ok: bool = b.call(c.add_channel(endpoint_id=eid))
        return ok

    test_property = b.get(odrv.test_property)
    try:
        print("rejections")
        b.call(c.clear_channels())
        check("start() without channels fails", not b.call(c.start()))
        refused = [i for i, eid in (("endpoint 0", 0), ("clear_errors()", b.endpoint_id(odrv.clear_errors)),
                                    ("serial_number (uint64)", b.endpoint_id(odrv.serial_number)),
                                    ("readout endpoint", b.get(c.readout_endpoint)))
                   if not add(eid)]
        check("add_channel refuses endpoint 0, a function, a uint64, the readout endpoint", len(refused) == 4
              and b.get(c.n_channels) == 0, f"refused {refused}")
        loop_id = b.endpoint_id(odrv.n_evt_control_loop)
        added = sum(add(loop_id) for _ in range(9))
        capacity = b.get(c.capacity)
        check("8 channels at most", added == 8 and b.get(c.n_channels) == 8 and capacity == 1024,
              f"added {added}, capacity {capacity}")
        b.call(c.clear_channels())
        add(loop_id)
        b.set(c.trigger_mode, RISING)
        b.set(c.trigger_channel, 1)
        check("level trigger on a missing channel fails", not b.call(c.start()))
        b.call(c.clear_channels())

        print("sample clock")
        for decimation, fields in ((1, [LOOP]), (4, [LOOP, "vbus_voltage"])):
            t, d, meta = capture(b, fields, decimation=decimation)
            steps = np.diff(d[LOOP].astype(np.int64))
            capacity = 8192 // len(fields)
            check(f"decimation {decimation}: counter steps by {decimation}, full buffer",
                  (steps == decimation).all() and meta["n_samples"] == capacity and meta["trigger_index"] == 0,
                  f"steps {sorted(set(steps.tolist()))}, {meta['n_samples']} samples, readout {meta['readout_s']} s")
        vbus = b.get(odrv.vbus_voltage)
        check("float32 channel matches the USB read", abs(float(d["vbus_voltage"].mean()) - vbus) < 0.5,
              f"{float(d['vbus_voltage'].mean()):.2f} V vs {vbus:.2f} V")

        print("types")
        ax = odrv.axis0
        fields = ["axis0.encoder.shadow_count", "axis0.encoder.is_ready", "axis0.controller.config.control_mode"]
        usb_values = [b.get(ax.encoder.shadow_count), int(b.get(ax.encoder.is_ready)),
                      b.get(ax.controller.config.control_mode).value]
        t, d, meta = capture(b, fields, decimation=8)
        got = [int(d[f][-1]) for f in fields]
        check("int32, bool and uint8 channels match the USB reads",
              abs(got[0] - usb_values[0]) < 50 and got[1:] == usb_values[1:], f"capture {got} vs USB {usb_values}")

        def rw_values():
            mode: ControlMode = b.get(ax.controller.config.control_mode)
            return (b.get(odrv.test_property), mode.value, b.get(ax.controller.config.pos_gain))

        b.set(odrv.test_property, 1234)
        before = rw_values()
        t, d, meta = capture(b, ["test_property", "axis0.controller.config.control_mode",
                                 "axis0.controller.config.pos_gain"], decimation=8)
        after = rw_values()
        captured = (int(d["test_property"][-1]), int(d["axis0.controller.config.control_mode"][-1]),
                    float(d["axis0.controller.config.pos_gain"][-1]))
        check("capturing read-write properties reads them and leaves them unchanged", before == after == captured,
              f"before {before}, after {after}, captured {captured}")

        print("triggers")
        for mode, before_v, after_v, post in ((RISING, 0, 5, 100), (FALLING, 5, 0, 10)):
            name = "rising" if mode is RISING else "falling"
            b.set(odrv.test_property, before_v)
            fields, types = setup(b, [LOOP, "test_property"], trigger=("test_property", mode, 2.5), post=post)
            time.sleep(0.2)
            armed = b.get(c.state) is ARMED
            b.set(odrv.test_property, after_v)
            wait_done(b, 2.0)
            t, d, meta = read(b, fields, types)
            k, x = meta["trigger_index"], d["test_property"]
            check(f"{name}: stays armed until the USB write crosses 2.5, {post} samples follow, pre-trigger kept",
                  armed and x[k] == after_v and x[k - 1] == before_v and meta["n_samples"] - 1 - k == post and k > 1000,
                  f"armed {armed}, values around the trigger {x[k - 2:k + 2].tolist()}, trigger_index {k}")

        fields, types = setup(b, [LOOP], trigger=(None, MANUAL, 0.0), post=50)
        time.sleep(0.2)
        armed = b.get(c.state) is ARMED
        n0 = b.get(odrv.n_evt_control_loop)
        b.call(c.trigger())
        wait_done(b, 2.0)
        t, d, meta = read(b, fields, types)
        k = meta["trigger_index"]
        check("manual: waits for trigger(), 50 samples follow, pre-trigger kept", armed and int(d[LOOP][k]) >= n0
              and k == meta["n_samples"] - 51 and k > 1000, f"armed {armed}, trigger_index {k}")

        print("cost")
        fields, types = setup(b, [LOOP] * 8, trigger=(None, MANUAL, 0.0))
        lengths = []
        for _ in range(50):
            b.set(odrv.task_timers_armed, True)
            t0 = time.monotonic()
            while b.get(odrv.task_timers_armed) and time.monotonic() - t0 < 0.5:
                pass
            lengths.append(b.get(odrv.task_times.capture_update.length))
        us = np.array(lengths) / CPU_HZ * 1e6
        check("8 channels cost under 10 % of the 125 us control period", us.max() < 12.5,
              f"capture_update mean {us.mean():.1f} us, max {us.max():.1f} us")
        b.call(c.clear_channels())
        state = b.get(c.state)
        check("clear_channels stops the capture", state is IDLE and b.get(c.n_channels) == 0, f"state {state.name}")
    finally:
        b.set(odrv.test_property, test_property)
        b.call(c.clear_channels())
        b.close()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = {"t": datetime.datetime.now().astimezone().isoformat(), "serial": serial, "checks": checks}
    path = LOGS / f"{stamp}_{serial}_capture-test.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    failed = [ch for ch in checks if not ch["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed -> {path.relative_to(WORKDIR)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
