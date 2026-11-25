# Python library (`xdrive`)

`tools/xdrive` is the host library for this firmware: typed reads, writes and function calls on a board, by names generated from the firmware's interface file. It replaces ODrive's `odrive` Python package and `odrivetool`, which do not work with this firmware. It talks to the board over USB with its own client for the firmware's packet protocol, and over [CAN](#can) with python-can: the same `Board` through [endpoint access](can.md#endpoint-access-0x1f), plus a `Bus` that commands several joints per control cycle. The CAN part is tested against fake boards on python-can's virtual bus and, through `tools/can_test.py`, on a real bus with one board. Every tool in `tools/` uses this library.

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

One process at a time holds a board's USB interface. While a script or a tool from `tools/` is connected, `usb.connect()` fails with "can't claim the interface; is another tool connected?".

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
| `save()` | `save_configuration()`: the board stores its config and reboots. Returns once it answers again; raises `Refused` when the motor is armed (no save, no reboot) or when the store failed (`config_save_failed` after the reboot) |
| `reboot()` | Reboots the board; returns once it answers again |
| `close()` | Releases the USB interface, or ends the CAN link (the bus stays open); also on leaving a `with` block |

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
| `LinkLost` (a `LinkError`) | The board went away (rebooted or unplugged), the link or the CAN bus is closed, the CAN adapter failed, or the interface JSON read back doesn't match its version ID |
| `Refused` | The board answered but refused: no such endpoint, a failed write, `save()` while armed; over CAN also a property wider than 4 bytes, without a request |
| `InterfaceMismatch` | The board's firmware build lacks a name from `xdrive.props`, types it differently, or returns an enum value the class doesn't have |
| `TypeError`, `ValueError` | A value of the wrong Python type (`1` for an `AxisState`), or one that doesn't fit the property (`-1` for a `uint8`) |

A name that the board's build lacks fails only when it is used, so a script written for a newer build still runs on an older one up to the first missing property.

## Several boards

`usb.connect()` opens the only board on USB and fails if there are several. `usb.serials()` lists them; `usb.connect(serial="0123456789AB")` opens one. Each `Board` is independent, so a script can hold several.

## CAN

`xdrive.can.open()` passes its arguments to python-can's `can.Bus` and returns an `xdrive.can.Bus`, which owns it. Any python-can interface works; on macOS a candleLight (gs_usb) adapter such as a CANable is `interface="gs_usb"`, with pyusb and libusb as for USB, plus python-can's driver package `gs_usb` (in `requirements.txt`).

```python
from xdrive import can
from xdrive.enums import AxisState, ControlMode, InputMode
from xdrive.props import odrv

with can.open(interface="gs_usb", channel=0, bitrate=1_000_000) as bus:
    print(bus.scan())                     # [1, 2]: node IDs heard in heartbeats within 0.3 s
    j1 = bus.connect(1)                   # a Board, as over USB; reads the node's impedance ranges too
    j1.set(odrv.axis0.controller.config.control_mode, ControlMode.IMPEDANCE_CONTROL)
    j1.set(odrv.axis0.controller.config.input_mode, InputMode.PASSTHROUGH)
    j1.set(odrv.axis0.requested_state, AxisState.CLOSED_LOOP_CONTROL)   # motor moves
    replies = bus.cycle({1: can.Impedance(pos=0.25, kp=20.0, kd=0.3)}, timeout=0.002)
    if (r := replies[1]) is not None:
        print(r.pos, r.vel, r.torque, r.armed, r.error, r.timeout)
```

- **`bus.connect(node)`** returns a `Board` with every operation above. Each request is one 8-byte frame pair, 4 bytes of value, so properties wider than 4 bytes (`serial_number`, `motor.error`, `axis0.steps`) raise `Refused` without a request; read `motor.error` with the Get Motor Error message. The first connect to a firmware build reads the 37 KB interface JSON 4 bytes at a time (about 9,300 frame pairs), then the cache serves it. A node has one request in flight at a time, and a request that timed out can leave a late reply that the next request with the same opcode and endpoint takes. Several threads can use one `Bus`.
- **`save()` and `reboot()`** wait for the request's timeout (default 1 s, `can.open(timeout=...)`), since the board resets before it replies, then poll the node until it answers; they don't need its heartbeat. A board whose `node_id` was changed and saved answers on the new ID, so `save()` raises `LinkTimeout` after its 15 s although the save worked: `bus.connect(new_id)`.
- **`bus.cycle(commands, timeout)`** sends one [impedance command](can.md#the-impedance-command-0x1e) per node and returns each node's reply, decoded with that node's ranges, or `None` for a node that didn't answer within `timeout`. It returns as soon as every node has answered. `timeout` bounds the wait for replies; handing each command to the adapter can take up to the bus's own timeout (`can.open(timeout=...)`), since a USB adapter can stall for a few milliseconds. A reply that arrives after its cycle's timeout but during the next cycle can be taken as that cycle's reply, one cycle old; outside a cycle, replies are dropped. The command only sets the inputs: set the control mode and closed loop first, as above.
- **`bus.ranges`** holds each connected node's `axis0.config.can.impedance_*` ranges, read by `connect()`. After changing them on a board, connect to it again.
- **`bus.heartbeat(node)`** returns the latest heartbeat (`state`, `axis_error`, the motor, encoder and controller error flags, `trajectory_done`, and the host's `time.monotonic()` at receipt `t`), or `None`. `bus.scan(timeout)` lists the nodes heard during `timeout`.
- **`bus.send_raw(arb_id, data)`** sends one standard-ID frame as given and awaits nothing: traffic for bus-load tests. `board.read_buffer(endpoint_id, size, offset)` reads part of a buffer endpoint, such as a window of the capture.
- **One reader thread** takes every frame off the bus. Frames this host sent are never taken as replies (gs_usb adapters hand them back). If the adapter fails, every later request raises `LinkLost` with the failure.

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
