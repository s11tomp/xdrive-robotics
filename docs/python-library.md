# Python library (`xdrive`)

`tools/xdrive` is the host library for this firmware: typed reads, writes and function calls on a board, by names generated from the firmware's interface file. It talks to the board over USB with its own client for the firmware's packet protocol, so it needs neither the `odrive` Python package nor `odrivetool`. CAN support (the same `Board` over [endpoint access](can.md#endpoint-access-0x1f), plus a bus object for commanding several joints) is planned. The tools in `tools/` still use the `odrive` package and move to `xdrive` one at a time.

```python
from xdrive import usb
from xdrive.enums import AxisState
from xdrive.props import odrv

with usb.connect() as board:
    print(board.get(odrv.vbus_voltage))                      # 23.98 (float)
    print(board.get(odrv.axis0.current_state))               # AxisState.IDLE
    board.set(odrv.axis0.controller.config.vel_limit, 10.0)  # returns 10.0, read back from the board
```

## Setup

The library runs in the repo's Python env (Python 3.11, created by `make`; see [Development](development.md)). It needs pyusb, which needs libusb (macOS: `brew install libusb`). The package lives in `tools/`, so run from there or put that directory on the module path:

```sh
make venv
PYTHONPATH=tools .venv/bin/python -i -c "from xdrive import usb; from xdrive.props import odrv; from xdrive.enums import *; board = usb.connect()"
```

The second command is the interactive shell: `board.get(odrv.axis0.encoder.pos_estimate)` at the prompt.

One process at a time holds a board's USB interface. While a script, `odrivetool` or a tool from `tools/` is connected, `usb.connect()` fails with "can't claim the interface; is another tool connected?".

## Names

`xdrive.props.odrv` is the board's root object. Its tree mirrors the [property reference](reference.md): `odrv.axis0.controller.config.pos_gain` is `odrv0.axis0.controller.config.pos_gain` there. Each leaf is a typed handle:

| Handle | Meaning | Example |
|---|---|---|
| `Prop[T]` | Read-only property with values of type `T` | `odrv.axis0.encoder.pos_estimate`: `Prop[float]` |
| `RwProp[T]` | Property the host can also write | `odrv.axis0.requested_state`: `RwProp[AxisState]` |
| Function | Called with its arguments, typed, it returns a `Call` for `board.call` | `odrv.capture.add_channel(endpoint_id=80)`: `Call[bool]` |

Value types:
- `float`, `int` and `bool` for plain properties. 64-bit properties (`serial_number`, `axis0.motor.error`, `axis0.steps`) work over USB.
- An enum from `xdrive.enums` (`AxisState`, `ControlMode`, `InputMode`, ...). These are `enum.Enum` classes, so `AxisState.IDLE == 1` is false and a raw integer is rejected.
- An error flag class from `xdrive.enums` (`AxisError`, `MotorError`, `EncoderError`, ...), an `enum.IntFlag`: `AxisError.MOTOR_FAILED in board.get(odrv.axis0.error)`.
- `EndpointRef(endpoint_id, json_crc)` for the GPIO analog mappings (`config.gpio3_analog_mapping.endpoint`).

Because every name and type is in the source, mypy checks scripts before they run:

```python
board.get(odrv.axis0.encoder.pos_estimat)
# error: "Encoder" has no attribute "pos_estimat"; maybe "pos_estimate"?  [attr-defined]
board.set(odrv.vbus_voltage, 1.0)
# error: Argument 1 to "set" of "Board" has incompatible type "Prop[float]"; expected "RwProp[float]"  [arg-type]
x: str = board.get(odrv.axis0.encoder.pos_estimate)
# error: Incompatible types in assignment (expression has type "float", variable has type "str")  [assignment]
```

`make generate` writes `tools/xdrive/props.py` and `tools/xdrive/enums.py` from `src/odrive-interface.yaml` (`tools/gen_props.py`). Edit the interface file, never the generated files; CI fails when they differ from the generator's output.

## Operations

All of them are methods of `xdrive.board.Board`. Each `get` and `set` is a transfer you can see in the code; nothing is read behind the caller's back.

| Method | Does |
|---|---|
| `get(prop)` | Reads one property and returns its value, typed |
| `set(prop, value)` | Writes a property and returns the value it holds afterwards, read back from the board |
| `get_many([props])` | Reads the properties one after another; returns a `Reading` with the `values` and the host's `perf_counter()` time before and after the reads (`t_start`, `t_end`) |
| `call(func(args))` | Writes the function's inputs, runs it, reads its outputs: returns `None`, one value, or a tuple |
| `save()` | `save_configuration()`: the board stores its config and reboots. Returns once it answers again |
| `reboot()` | Reboots the board; returns once it answers again |
| `close()` | Releases the USB interface (also on leaving a `with` block) |

**`set` returns what the board stored,** which can differ from what was written. A setter can clamp a value, and some properties are consumed at once: after `set(odrv.axis0.requested_state, AxisState.CLOSED_LOOP_CONTROL)` the board has acted on the request and cleared it, so the call returns `AxisState.UNDEFINED`. Read `current_state` for the result.

**`get_many` doesn't give a snapshot.** Each read is its own transfer, about 0.2 ms apart over USB, so the values come from different control periods, and a USB stall can separate two of them by several milliseconds. Check `t_end - t_start` before treating a row as one instant. For values from one control period, use the [capture](capture.md).

**Functions** take their arguments by name or position, as the generated signature shows:

```python
c = board.call(odrv.axis0.encoder.get_correction(index=10))   # float: bin 10 of the correction table
board.call(odrv.axis0.controller.move_incremental(displacement=0.5, from_input_pos=True))   # motor moves (in closed loop)
board.call(odrv.clear_errors())
```

Call `save_configuration` and `reboot` through `board.save()` and `board.reboot()`: the board resets before it can reply, so a plain `call` ends in a timeout. Two more functions reset the board: `erase_configuration` and `enter_dfu_mode`. Use them through the tools that handle that (`tools/usb_flash.py` for DFU), not through `call`.

**Saving and rebooting:**
- **Motor moves:** after a reboot, the board runs its startup sequence (calibration, closed loop) as configured.
- `save()` works only while the motor is disarmed. Armed, the firmware refuses, stays up and returns false; `save()` then raises `Refused` with that reason. Put the axis in IDLE first.
- Both methods read `system_stats.uptime` before and after, and raise `LinkLost` if the board answers without its uptime having gone down.

## Errors

Every exception derives from `xdrive.errors.XdriveError`:

| Exception | Raised when |
|---|---|
| `LinkError` | No board on USB, several boards and no serial given, the interface already claimed, or a transfer failed |
| `LinkTimeout` (a `LinkError`) | The board didn't reply within the timeout (default 1 s) |
| `LinkLost` (a `LinkError`) | The board went away (rebooted or unplugged), the link is closed, or the interface JSON read back doesn't match its version ID |
| `Refused` | The board answered but refused: no such endpoint, a failed write, `save()` while armed |
| `InterfaceMismatch` | The board's firmware build lacks a name from `xdrive.props`, types it differently, or returns an enum value the class doesn't have |
| `TypeError`, `ValueError` | A value of the wrong Python type (`1` for an `AxisState`), or one that doesn't fit the property (`-1` for a `uint8`) |

A name that the board's build lacks fails only when it is used, so a script written for a newer build still runs on an older one up to the first missing property.

## Several boards

`usb.connect()` opens the only board on USB and fails if there are several. `usb.serials()` lists them; `usb.connect(serial="0123456789AB")` opens one. Each `Board` is independent, so a script can hold several.

## The interface JSON and its cache

The firmware embeds a JSON description of every endpoint (about 37 KB): name, endpoint ID, wire type and access. `Board` reads it at connect and looks names up in it, so the generated tree carries no endpoint IDs and works with any build that has the names.

The JSON's version ID changes with every build that changes the interface. The library keeps one copy per version ID in `~/.cache/xdrive/` (or `$XDG_CACHE_HOME/xdrive/`), so the JSON crosses the link once per firmware build: about 0.3 s over USB the first time, and a connect takes about 0.1 s after that. A cache that can't be written only produces a warning. Delete the directory to force a fresh read.

## Speed over USB

Measured on a Mini with this firmware on a Mac:

| Operation | Time |
|---|---|
| `get` of one property | 0.2 ms |
| `set` | 0.35 ms (the write, then a read-back) |
| First connect (JSON over USB) | 0.32 s |
| Connect with the JSON cached | 0.12 s |
| `reboot()`, from the call until the board answers | 1.2 s |

## The USB protocol

`tools/xdrive/usb.py` speaks the firmware's native protocol (`src/fibre-cpp/legacy_protocol.cpp`), for anyone writing a client in another language. The board's USB interface 2 has one bulk endpoint pair, 0x03 out and 0x83 in, with 64-byte packets. A request is one packet, little-endian:

| Bytes | Field |
|---|---|
| 0–1 | Sequence number (bit 15 clear) |
| 2–3 | Endpoint ID, with bit 15 set to ask for a reply |
| 4–5 | Reply length in bytes (the board sends at most 61) |
| 6– | Payload: a property's new value for a write, a uint32 byte offset for a buffer read, empty otherwise |
| last 2 | Trailer: the interface JSON's CRC-16, or 1 (the protocol version) for endpoint 0 |

The reply is the sequence number with bit 15 set, then the output: a property's value (its value before the write, for a write), or the buffer bytes at the offset. A packet with the wrong trailer gets no reply.

- **Endpoint 0** is the interface JSON as a buffer. Offset 0xFFFFFFFF returns its version ID, a uint32. The high 16 bits of that ID are the CRC that the trailers of all other requests carry.
- **The CRC** is CRC-16 with polynomial 0x3D65, MSB first, no reflection and no final XOR, seeded with 1 and run over the JSON. The version ID is `crc << 16 | crc16(json, seed=crc)`.
- **A refusal is visible only as a short reply.** A handler that fails writes no output. That's why the library's write asks for the old value as its reply: a write that asks for no reply can fail without any sign.
- **A function** is called by writing each input endpoint, sending its own endpoint ID with no payload, then reading each output endpoint. The endpoint IDs of the inputs and outputs are in the JSON, under the function.
