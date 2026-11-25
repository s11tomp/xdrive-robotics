# xdrive-robotics

Firmware for the **MKS XDRIVE Mini** (a single-motor ODrive v3.6 clone) for robotics, based on **ODrive v0.5.6**, with the host tools that flash, configure and bench-test it. It adds an encoder correction table, safety faults, impedance control with a one-frame CAN command, access to every setting over CAN, firmware updates over CAN, regen limits and 8 kHz capture, and it flashes over USB with no debug probe.

This is an unofficial fork. It is not affiliated with ODrive Robotics or Makerbase.

> **Warning:** this firmware drives 60 V hardware, high-torque motors and brake resistors. A wrong setting can spin a motor at full speed, overheat it or pump the supply voltage up. Start with low `current_lim` and `vel_limit`, keep an idle command ready (`python tools/idle.py`), and keep hands clear of anything attached to the motor. The software is provided as-is, without warranty (see `LICENSE.md`).

## Tested hardware

| | Tested | Untested |
|---|---|---|
| Board | MKS XDRIVE Mini: reports hw 3.6, 56 V variant; onboard AS5047 that behaves as an AS5047P | Other single-motor ODrive v3.6 clones (ODESC and others). Dual-motor boards such as the ODrive v3.6 itself are not supported |
| Motor | DJI 10018 (77 KV, 21 pole pairs) at 24 V, unloaded rotor | Other motors, motors under load |
| CAN | One board on a 1 Mbit/s bus (CANable 2.0 Pro, slcan): impedance command, endpoint access, CAN bootloader | Two or more boards on one bus |
| Host | macOS, Python 3.11 | Linux, Windows |

## What it adds to ODrive v0.5.6

- **One axis, matching the Mini.** The firmware has one axis (`axis0`): no second axis on USB or CAN, no errors from a missing second gate driver, and none of the second motor's code or per-cycle work (the control loop is busy 73 µs of each 125 µs period). Stock v0.5.6 doesn't drive the Mini at all: it keeps retrying the missing second gate driver over the SPI bus the encoder shares.
- **[Encoder integrity](docs/encoders.md#frame-checks):** AS5047 frame checks (error flag, parity) with counters, and rejection of impossible jumps.
- **[Encoder correction table](docs/encoders.md#correction-table):** a calibration state (`AXIS_STATE_ENCODER_CORRECTION_CALIBRATION`, 14) measures the angle error of an imperfectly placed magnet over one turn (256 bins, harmonics 1 to 12), and the firmware corrects it at run time. On a DJI 10018 it removes 92 % of a 4x-per-turn current ripple.
- **[Safety faults](docs/safety-and-regen.md#faults)**, off by default: soft position limits (`controller.config.pos_min`, `pos_max`) and following-error faults (`max_pos_error`, `max_vel_error`), which zero the torque. An expired watchdog, once enabled, decelerates and holds position by default (`axis.config.watchdog_action = DECEL_HOLD`) instead of dropping the load.
- **Closed-loop entry starts from rest:** zero velocity and torque setpoints, no running trajectory.
- **[Impedance control](docs/control.md#impedance-control)** (`CONTROL_MODE_IMPEDANCE_CONTROL`, 4): torque = `input_kp` × position error + `input_kd` × velocity error + `input_torque`, with no integrator. `input_torque` is torque feed-forward in every input mode, the trajectory planner included.
- **[CAN impedance command](docs/can.md#the-impedance-command-0x1e)** (CANSimple ID 0x1E): position, velocity, kp, kd and torque in 8 bytes, answered at once on the same ID with position, velocity, measured torque, flags, FET temperature and bus voltage.
- **[Endpoint access over CAN](docs/can.md#endpoint-access-0x1f)** (CANSimple ID 0x1F): read or write any property, call any function, and read the interface JSON and the capture buffer. A board can be configured, tuned, saved and rebooted with no USB connection.
- **[CAN bootloader](docs/bootloader.md):** firmware updates over CAN in about 16 s per board; an interrupted update leaves the board waiting in the bootloader, ready to try again.
- **[Regen limits](docs/safety-and-regen.md#regen-where-braking-energy-goes)**, off by default: flux braking above a bus voltage (`motor.config.flux_brake_start_voltage`), and bus current soft limits (`motor.config.I_bus_soft_min`, `I_bus_soft_max`) that burn regen in the windings before cutting braking torque.
- **[High-rate capture](docs/capture.md)** (`odrv.capture`): up to 8 properties at the 8 kHz control rate into a 32 KiB RAM buffer, with a level, manual or immediate trigger, read back in about 0.13 s.
- **Host side:** a typed [Python library](docs/python-library.md) for USB and CAN (ODrive's `odrivetool` and `odrive` Python package do not work with this firmware), [host tools](docs/tools.md) that flash with a whole-flash backup and read-back check, and [bench tests](docs/testing.md) for every added feature.

`CHANGELOG.md` lists every difference from ODrive v0.5.6, removals included. The rest of ODrive v0.5.6 (step/direction, UART, endstops, other encoders) is kept unchanged and untested on the Mini: [Hardware](docs/hardware.md#inherited-odrive-features) lists those features with their pins.

## Documentation

| Page | Contents |
|---|---|
| [Getting started](docs/getting-started.md) | Wiring, the first flash, configuring and calibrating a Mini, first moves |
| [Migrating from Makerbase's firmware](docs/migrating-from-stock.md) | How the stock v0.5.1 differs, what to save before flashing, carrying settings over |
| [Control](docs/control.md) | Control modes, input modes, impedance control, tuning |
| [CAN](docs/can.md) | Wiring and termination, the message table, the impedance command, endpoint access, bus load |
| [CAN bootloader](docs/bootloader.md) | Firmware updates over CAN, the flash layout, moving a board onto the bootloader |
| [Safety and regen](docs/safety-and-regen.md) | Faults, the watchdog hold, braking energy, ground loops |
| [Encoders](docs/encoders.md) | The onboard AS5047, frame checks, the correction table |
| [Hardware](docs/hardware.md) | Connectors, pinouts, GPIOs and the ODrive features that use them, sensing, timing, the STM32 bootloader, the tested motor |
| [Capture](docs/capture.md) | Recording properties at 8 kHz |
| [Host tools](docs/tools.md) | Every tool in `tools/`, and the checks the flash tools make |
| [Python library](docs/python-library.md) | `xdrive`: typed access to a board over USB and CAN, its errors, and the USB protocol |
| [Testing](docs/testing.md) | Host tests, the bench tests, validating a board or motor |
| [Troubleshooting](docs/troubleshooting.md) | Common errors on the Mini, connection and saving problems, symptoms |
| [Property reference](docs/reference.md) | Every property, function, enum and error bit (generated from `src/odrive-interface.yaml`) |
| [Development](docs/development.md) | Repository layout, toolchain, build, generated files, debugging over SWD, rebuilding Makerbase's firmware, releases |

## Quick start

[Getting started](docs/getting-started.md) has the full walk-through, with wiring figures and the settings to change for another motor. Run everything from the repository root; "Motor moves" marks a step that turns the rotor or reboots the board.

**Host tools**
1. Install `uv`; on macOS also `brew install libusb`.
2. `make venv` (creates `.venv` with Python 3.11 from `requirements.txt`).
3. `source .venv/bin/activate`

**Firmware:** download `xdrive-robotics-X.Y.Z-with-bootloader.bin` and `xdrive-robotics-X.Y.Z.elf` from the releases page, or build them: install GNU Arm Embedded 10.3-2021.10 ([Development](docs/development.md#toolchain)), then `make -j8` (output in `build/`).

**First flash** (the bootloader and the firmware together; flashing from Makerbase's firmware resets the board's config)
1. Hold S2 while pressing S1: the board starts in the STM32's DFU bootloader.
2. Motor moves (reboot): `python tools/usb_flash.py --bin xdrive-robotics-X.Y.Z-with-bootloader.bin` (dry run: backs up the whole flash to `backups/`, compares, writes nothing). Keep the first backup: it is the only way back to the board's original firmware.
3. S2 and S1 again, then motor moves (reboot): `python tools/usb_flash.py --bin xdrive-robotics-X.Y.Z-with-bootloader.bin --write`

**Later updates:** `python tools/usb_flash.py --elf xdrive-robotics-X.Y.Z.elf --write` (the tool enters the bootloader itself), or over CAN with `tools/can_flash.py`.

**Configure a DJI 10018** (for another motor, start from the example and change the motor values)
1. Read the comment at the top of `examples/dji-10018.json`, and change the supply, brake resistor and encoder parity settings to match your setup.
2. `python tools/set_config.py --file examples/dji-10018.json`
3. Motor moves (reboot): `python tools/set_config.py --save axis0.config.startup_encoder_offset_calibration=false` (applies the SPI encoder mode).
4. Motor moves: `python tools/calibrate.py --motor --offset --correction`
5. Motor moves (reboot): `python tools/set_config.py --save axis0.encoder.config.pre_calibrated=true axis0.config.startup_closed_loop_control=true` (the board reboots into closed loop, holding position).
6. `python tools/dump_board.py --compare examples/dji-10018.json` (lists any setting that differs, and the board's errors).

**CAN:** set `can.config.baud_rate` and a distinct `axis0.config.can.node_id` per board, then wire the bus as [CAN](docs/can.md#wiring) shows (J3 has no ground pin).

## Repository layout

| Path | Contents |
|---|---|
| `src/` | The firmware: ODrive v0.5.6's firmware tree with this firmware's changes, the CAN bootloader (`bootloader/`), the vendored libraries (`ThirdParty/`, `fibre-cpp/`), the interface definition (`odrive-interface.yaml`) and unit tests (`tests/`) |
| `tools/` | Host tools, the host library (`xdrive/`), their tests (`tests/`), and the code generators |
| `docs/` | Documentation and figures, the generated property reference and the CAN database (`cansimple.dbc`) |
| `examples/` | Example settings for a DJI 10018 and a CAN example |
| `build/` | Build output: firmware images, generated headers, unit-test binary (not committed) |

`make test` runs the firmware's unit tests on the host, mypy on the host library, and the host tools' tests; none needs a board ([Testing](docs/testing.md)). `git diff -M upstream/fw-v0.5.6 main -- Firmware src` shows every firmware change (upstream's `Firmware/` is `src/` here).

## Versioning

Releases are numbered from 1.0.0, independently of ODrive, and each release states its ODrive base. Upstream ODrive firmware for v3.x boards ends at 0.5.6, so a v3.6 board reporting 1.x runs this firmware. A major version marks a config-layout change: flashing across it resets the board's config. A build of any commit after a release tag, or of a modified tree, reports that release's version with `fw_version_unreleased = 1`. Releases, with their images and SHA-256 sums, are on the GitHub releases page; `CHANGELOG.md` lists what each one changes.

## Support

Issues and feature requests are welcome, including uses beyond robot arms. Support is not promised. A bug report needs the board, motor, firmware version and a `python tools/dump_board.py` dump.

## License

MIT (`LICENSE.md`), as is the ODrive code this builds on.
