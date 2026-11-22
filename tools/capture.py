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
  python tools/capture.py axis0.motor.current_control.Iq_measured axis0.motor.current_control.Id_measured --label hold
  python tools/capture.py axis0.motor.current_control.Iq_measured --trigger 'axis0.motor.current_control.Iq_measured>1.5'
"""
import argparse
import datetime
import json
import pathlib
import re
import sys
import time

import numpy as np

from xdrive import paths, usb
from xdrive.enums import CaptureState, CaptureTrigger
from xdrive.props import odrv

WORKDIR = pathlib.Path.cwd()  # logs/, backups/ and configs/ go under the working directory
LOGS = WORKDIR / "logs"
CONTROL_HZ = 8000  # XDRIVE Mini / ODrive v3 control loop rate (TIM1 period 3500 counts, RCR 2, 168 MHz)
MAX_CHANNELS = 8
IDLE, ARMED, TRIGGERED, DONE = CaptureState.IDLE, CaptureState.ARMED, CaptureState.TRIGGERED, CaptureState.DONE
IMMEDIATE, RISING, FALLING, MANUAL = (CaptureTrigger.IMMEDIATE, CaptureTrigger.RISING, CaptureTrigger.FALLING,
                                      CaptureTrigger.MANUAL)
DTYPES = {"float": np.float32, "int32": np.int32}  # every other accepted type is unsigned, zero-padded to 32 bits


class CaptureError(Exception):
    pass


def parse_trigger(text):
    """'path>level' -> (path, RISING, level); 'path<level' -> (path, FALLING, level)."""
    m = re.fullmatch(r"\s*([\w.]+)\s*([<>])\s*(\S+)\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"trigger must look like 'axis0.x.y>1.5' or 'axis0.x.y<-2', got {text!r}")
    return m[1], RISING if m[2] == ">" else FALLING, float(m[3])


def setup(b, fields, decimation=1, trigger=None, post=None):
    """Configure and start a capture; returns the channels' paths and wire types.

    fields: dotted property paths. trigger: None for an immediate capture, or (path, RISING | FALLING
    | MANUAL, level); a trigger path not in fields is appended as a channel. post: samples after the
    trigger (None: the rest of the buffer for an immediate capture, half of it otherwise)."""
    c = odrv.capture
    fields = list(fields)
    if trigger and trigger[1] is not MANUAL and trigger[0] not in fields:
        fields.append(trigger[0])
    if not 0 < len(fields) <= MAX_CHANNELS:
        raise CaptureError(f"1..{MAX_CHANNELS} channels, got {len(fields)}")
    types = [b.interface.properties[paths.prop(f).path].type for f in fields]
    b.call(c.clear_channels())
    for f in fields:
        eid = b.endpoint_id(paths.prop(f))
        if not b.call(c.add_channel(endpoint_id=eid)):
            raise CaptureError(f"add_channel refused {f} (endpoint {eid})")
    capacity = b.get(c.capacity)
    b.set(c.decimation, decimation)
    if trigger is None:
        b.set(c.trigger_mode, IMMEDIATE)
        b.set(c.post_trigger, capacity - 1 if post is None else post)
    else:
        path, mode, level = trigger
        b.set(c.trigger_mode, mode)
        if mode is not MANUAL:
            b.set(c.trigger_channel, fields.index(path))
            b.set(c.trigger_level, level)
        b.set(c.post_trigger, capacity // 2 if post is None else post)
    if not b.call(c.start()):
        raise CaptureError("start() refused")
    return fields, types


def wait_done(b, timeout):
    t0 = time.monotonic()
    while (state := b.get(odrv.capture.state)) is not DONE:
        if time.monotonic() - t0 > timeout:
            raise CaptureError(f"no trigger within {timeout} s (state {state.name})")
        time.sleep(0.02)


def read(b, fields, types):
    """Read a DONE capture: returns (t [s] relative to the trigger sample, {field: np.ndarray}, meta)."""
    c = odrv.capture
    n, nch, decimation, trig = b.get(c.n_samples), b.get(c.n_channels), b.get(c.decimation), b.get(c.trigger_index)
    if nch != len(types):
        raise CaptureError(f"the capture has {nch} channels, expected {len(types)}")
    t0 = time.monotonic()
    raw = b.read_buffer(b.get(c.readout_endpoint), n * nch * 4)
    read_s = time.monotonic() - t0
    words = np.frombuffer(raw, dtype="<u4").reshape(n, nch)
    data = {f: words[:, i].view(DTYPES.get(ty, np.uint32)) for i, (f, ty) in enumerate(zip(fields, types))}
    period = max(decimation, 1) / CONTROL_HZ
    t = (np.arange(n) - trig) * period
    meta = {"n_samples": n, "channels": fields, "decimation": decimation, "period_s": period,
            "trigger_index": trig, "trigger_mode": b.get(c.trigger_mode).value, "readout_s": round(read_s, 3)}
    return t, data, meta


def capture(b, fields, decimation=1, trigger=None, post=None, timeout=10.0):
    """setup + wait + read; see those functions."""
    fields, types = setup(b, fields, decimation, trigger, post)
    wait_done(b, timeout)
    return read(b, fields, types)


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
    b = usb.connect()
    serial = format(b.get(odrv.serial_number), "X")
    t, data, meta = capture(b, a.fields, a.decimation, a.trigger, a.post, a.timeout)
    b.close()
    meta.update(t=datetime.datetime.now().astimezone().isoformat(), serial=serial,
                trigger=None if a.trigger is None else [a.trigger[0], a.trigger[1].value, a.trigger[2]])
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
