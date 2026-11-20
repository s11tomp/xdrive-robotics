#!/usr/bin/env python3
"""High-rate capture: record up to 8 properties at the 8 kHz control rate in the board's RAM, then read them.

Uses the firmware's odrv.capture (this firmware only; stock ODrive has no capture). Never moves the motor and doesn't change what the
axis is doing: it configures the capture, waits for it to finish and reads the buffer (32 KiB, about 1 s).
  immediate   records a full buffer from now: 8192 / n_channels samples
  trigger     '<field>>level' (rising) or '<field><level' (falling); --post samples follow the trigger
              (default half the buffer, so the other half is before it)
Output: logs/<stamp>_<serial>_capture_<label>.csv (t [s] from the trigger sample, one column per field)
and a .json with the settings and trigger details.

Usage (from the repo root):
  python xdrive/tools/capture.py axis0.motor.current_control.Iq_measured axis0.motor.current_control.Id_measured --label hold
  python xdrive/tools/capture.py axis0.motor.current_control.Iq_measured --trigger 'axis0.motor.current_control.Iq_measured>1.5'
"""
import argparse
import datetime
import json
import re
import sys
import time

import numpy as np

from dump_board import connect
from sample import LOGS, WORKDIR, resolve

CONTROL_HZ = 8000  # XDRIVE Mini / ODrive v3 control loop rate (TIM1 period 3500 counts, RCR 2, 168 MHz)
MAX_CHANNELS = 8
IDLE, ARMED, TRIGGERED, DONE = 0, 1, 2, 3  # CaptureState
IMMEDIATE, RISING, FALLING, MANUAL = 0, 1, 2, 3  # CaptureTrigger
DTYPES = {"<f": np.float32, "<i": np.int32}  # every other accepted type is unsigned, zero-padded to 32 bits


class CaptureError(Exception):
    pass


def parse_trigger(text):
    """'path>level' -> (path, RISING, level); 'path<level' -> (path, FALLING, level)."""
    m = re.fullmatch(r"\s*([\w.]+)\s*([<>])\s*(\S+)\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"trigger must look like 'axis0.x.y>1.5' or 'axis0.x.y<-2', got {text!r}")
    return m[1], RISING if m[2] == ">" else FALLING, float(m[3])


def setup(dev, fields, decimation=1, trigger=None, post=None):
    """Configure and start a capture; returns the RemoteProperty per channel.

    fields: dotted property paths (v0.5.1 names are mapped by sample.resolve). trigger: None for an
    immediate capture, or (path, RISING | FALLING | MANUAL, level); a trigger path not in fields is
    appended as a channel. post: samples after the trigger (None: the rest of the buffer for an
    immediate capture, half of it otherwise)."""
    c = dev.capture
    fields = list(fields)
    if trigger and trigger[1] != MANUAL and trigger[0] not in fields:
        fields.append(trigger[0])
    if not 0 < len(fields) <= MAX_CHANNELS:
        raise CaptureError(f"1..{MAX_CHANNELS} channels, got {len(fields)}")
    props = [resolve(dev, f) for f in fields]
    c.clear_channels()
    for f, p in zip(fields, props):
        if not c.add_channel(p._id):
            raise CaptureError(f"add_channel refused {f} (endpoint {p._id})")
    capacity = c.capacity
    c.decimation = decimation
    if trigger is None:
        c.trigger_mode = IMMEDIATE
        c.post_trigger = capacity - 1 if post is None else post
    else:
        path, mode, level = trigger
        c.trigger_mode = mode
        if mode != MANUAL:
            c.trigger_channel = fields.index(path)
            c.trigger_level = level
        c.post_trigger = capacity // 2 if post is None else post
    if not c.start():
        raise CaptureError("start() refused")
    return fields, props


def wait_done(dev, timeout):
    t0 = time.monotonic()
    while (state := dev.capture.state) != DONE:
        if time.monotonic() - t0 > timeout:
            raise CaptureError(f"no trigger within {timeout} s (state {state})")
        time.sleep(0.02)


def read(dev, fields, props):
    """Read a DONE capture: returns (t [s] relative to the trigger sample, {field: np.ndarray}, meta)."""
    c = dev.capture
    n, nch, decimation, trig = c.n_samples, c.n_channels, c.decimation, c.trigger_index
    t0 = time.monotonic()
    raw = dev.__channel__.remote_endpoint_read_buffer(c.readout_endpoint)
    read_s = time.monotonic() - t0
    if nch != len(props) or len(raw) != n * nch * 4:
        raise CaptureError(f"readout {len(raw)} bytes, expected {n} x {nch} x 4 (channels {len(props)})")
    words = np.frombuffer(raw, dtype="<u4").reshape(n, nch)
    data = {f: words[:, i].view(DTYPES.get(p._codec._struct_format, np.uint32)) for i, (f, p) in enumerate(zip(fields, props))}
    period = max(decimation, 1) / CONTROL_HZ
    t = (np.arange(n) - trig) * period
    meta = {"n_samples": n, "channels": fields, "decimation": decimation, "period_s": period,
            "trigger_index": trig, "trigger_mode": c.trigger_mode, "readout_s": round(read_s, 3)}
    return t, data, meta


def capture(dev, fields, decimation=1, trigger=None, post=None, timeout=10.0):
    """setup + wait + read; see those functions."""
    fields, props = setup(dev, fields, decimation, trigger, post)
    wait_done(dev, timeout)
    return read(dev, fields, props)


def save(t, data, meta, serial, label):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = LOGS / f"{stamp}_{serial}_capture_{label}"
    cols = [t] + list(data.values())
    np.savetxt(base.with_suffix(".csv"), np.column_stack(cols), delimiter=",", fmt="%.9g",
               header=",".join(["t"] + list(data)), comments="")
    base.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    return base.with_suffix(".csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fields", nargs="+")
    ap.add_argument("--decimation", type=int, default=1)
    ap.add_argument("--trigger", type=parse_trigger)
    ap.add_argument("--post", type=int, help="samples after the trigger")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--label", default="capture")
    a = ap.parse_args()
    dev = connect(timeout=10)
    serial = format(dev.serial_number, "X")
    t, data, meta = capture(dev, a.fields, a.decimation, a.trigger, a.post, a.timeout)
    meta.update(t=datetime.datetime.now().astimezone().isoformat(), serial=serial,
                trigger=None if a.trigger is None else list(a.trigger))
    path = save(t, data, meta, serial, a.label)
    print(f"{meta['n_samples']} samples x {len(data)} channels at {1 / meta['period_s']:.0f} Hz, "
          f"trigger at sample {meta['trigger_index']}, read in {meta['readout_s']} s")
    for f, x in data.items():
        x = x.astype(float)
        print(f"  {f:50s} mean {x.mean():+.5g}  std {x.std():.4g}  min {x.min():+.5g}  max {x.max():+.5g}")
    print(f"-> {path.relative_to(WORKDIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
