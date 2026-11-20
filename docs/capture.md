# Capture

The board can record up to 8 properties at the 8 kHz control rate into a 32 KiB RAM buffer and send the buffer to the host in about 0.2 s. USB polling reaches about 150 to 200 samples per second for a set of properties, so capture is the way to see what happens within a few control periods: a current step, a hard stop, a fault.

## From the command line

`tools/capture.py` never moves the motor and doesn't change what the axis is doing:

```sh
# record now, until the buffer is full (8192 / channels samples)
python tools/capture.py axis0.motor.current_control.Iq_measured axis0.motor.current_control.Id_measured --label hold

# wait for Iq to rise through 1.5 A, keep half the buffer before it and half after
python tools/capture.py axis0.motor.current_control.Iq_measured vbus_voltage \
    --trigger 'axis0.motor.current_control.Iq_measured>1.5'
```

- `--trigger 'field>level'` triggers on a rising crossing, `'field<level'` on a falling one. A trigger field not in the list is added as a channel.
- `--post N` sets how many samples follow the trigger (default: half the buffer).
- `--decimation N` records every Nth control period, for a longer window at a lower rate.

Output: `logs/<stamp>_<serial>_capture_<label>.csv`, with time in seconds from the trigger sample and one column per property, and a `.json` with the settings.

## From Python

The same file is a library: `capture(dev, fields, decimation=1, trigger=None, post=None)` configures, waits and reads, returning the time axis, a NumPy array per property and the settings; `setup()` and `read()` split it, so a script can start a capture, run a move, and read afterwards. `regen_test.py` records its stops this way.

## The firmware interface

`odrv0.capture` ([property reference](reference.md#odrv0capture)):

1. `clear_channels()`, then `add_channel(endpoint_id)` for each property (float32, int32, uint32, uint16, uint8 or bool).
2. Set `decimation`, `trigger_mode` (`IMMEDIATE`, `RISING`, `FALLING` or `MANUAL`), `trigger_channel`, `trigger_level` and `post_trigger`.
3. `start()`. `state` goes `ARMED`, then `TRIGGERED` (recording the post-trigger samples), then `DONE`. `trigger()` triggers by hand in any mode.
4. Read the buffer from `readout_endpoint` in one transfer: `n_samples` frames of 4 bytes per channel, in channel order, with the trigger sample at `trigger_index`.

`capacity` = 8192 / channels frames. Recording costs about 10 µs of the 125 µs control period with 8 channels.
