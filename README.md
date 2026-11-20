# xdrive-robotics

Firmware for the **MKS XDRIVE Mini** (an ODrive v3.6 clone) for robotics, based on **ODrive v0.5.6**, plus the host tools that flash, configure and bench-test it. It adds an encoder correction table, safety faults, impedance control with a CAN command, regen limits and 8 kHz capture, and it flashes over USB with no ST-Link.

This is an unofficial fork. It is not affiliated with ODrive Robotics or Makerbase.

> **Warning:** this firmware drives 60 V hardware, high-torque motors and brake resistors. A wrong setting can spin a motor at full speed, overheat it or pump the supply voltage up. Start with low `current_lim` and `vel_limit`, keep an idle command ready (`python xdrive/tools/idle.py`), and keep hands clear of anything attached to the motor. The software is provided as-is, without warranty (see `LICENSE.md`).

## Tested hardware

| | Tested | Not tested |
|---|---|---|
| Board | MKS XDRIVE Mini, reports hw 3.6, 56 V variant, onboard AS5047P | Other single-motor ODrive v3.6 clones (ODESC and others). Not supported: dual-motor boards such as the ODrive v3.6 itself |
| Motor | DJI 10018 (77 KV, 21 pole pairs) at 24 V, unloaded rotor on a bench stand | Other motors, motors under load |
| CAN | The impedance command's codec, against the firmware header on the host | A real bus |
| Host | macOS, Python 3.11 | Linux, Windows |

## What it adds to ODrive v0.5.6

- **One axis, matching the Mini.** The Mini has one motor channel, and the firmware has one axis (`axis0`): no second axis on USB or CAN, no errors from a missing second gate driver, and the second motor's code, RAM and per-cycle work removed (control loop 74 µs busy per 125 µs cycle, down from 86). Stock v0.5.6 doesn't drive the Mini at all: it keeps retrying the missing second driver over the SPI bus the encoder shares.
- **Encoder integrity:** AS5047 frame checks (error flag, parity) with counters, and rejection of impossible jumps.
- **Encoder correction table:** a calibration state (`AXIS_STATE_ENCODER_CORRECTION_CALIBRATION`, 14) measures the angle error of an off-center magnet over one turn, and the firmware corrects it at run time (256 bins, harmonics 1 to 12). On a bench stand it removed 92 % of a 4x-per-turn current ripple.
- **Boot without motion:** with a pre-calibrated encoder the board goes straight to closed loop about 2.5 s after power-up.
- **Safety faults**, all off by default:
  - watchdog decelerate-and-hold (`axis.config.watchdog_action = DECEL_HOLD`, the default action once the watchdog is enabled);
  - soft position limits (`controller.config.pos_min`, `pos_max`);
  - following-error faults (`max_pos_error`, `max_vel_error`), which zero the torque.
- **Closed-loop entry starts from rest:** zero velocity and torque setpoints, no running trajectory.
- **Impedance control** (`CONTROL_MODE_IMPEDANCE_CONTROL`, 4): torque = `input_kp` x position error + `input_kd` x velocity error + `input_torque`, with no integrator.
- **CAN impedance command** (CANSimple ID 0x1E): position, velocity, kp, kd and torque in 8 bytes, answered at once on the same ID with position, velocity, measured torque, flags, FET temperature and bus voltage. Layout: `Firmware/communication/can/impedance_frame.hpp`; host codec: `xdrive/tools/impedance_frame.py`.
- **Regen limits**, off by default: flux braking above a bus voltage (`motor.config.flux_brake_start_voltage`), and bus current soft limits (`motor.config.I_bus_soft_min`, `I_bus_soft_max`) that burn regen in the windings before cutting braking torque.
- **High-rate capture** (`odrv.capture`): up to 8 properties at the 8 kHz control rate into a 32 KiB RAM buffer, with a level, manual or immediate trigger, read back in about 0.2 s.

`git diff upstream/fw-v0.5.6 main -- Firmware` shows every firmware change. Developer notes (branches, toolchain, the build without tup, the byte-identical rebuild of Makerbase's firmware) are in `xdrive/README.md`. Facts about the board (pinouts, CAN wiring, bootloader, quirks) are in `xdrive/docs/board-findings.md`.

## Quick start

All commands run from the repository root. The tools write logs to `logs/` and flash backups to `backups/` under the working directory.

**Build**
1. Install GNU Arm Embedded 10.3-2021.10 and `uv` (details: `xdrive/README.md`).
2. `make -C xdrive -j8` (output: `Firmware/build/ODriveFirmware.{elf,hex,bin}`).

**Host tools**
1. `python3.11 -m venv .venv`
2. `.venv/bin/pip install -r xdrive/tools/requirements.txt` (pyusb also needs libusb; on macOS: `brew install libusb`).
3. `source .venv/bin/activate`

**Flash over USB** (Motor moves: every run, dry run included, ends with a reboot, and the startup sequence runs)
1. `python xdrive/tools/usb_flash.py --elf Firmware/build/ODriveFirmware.elf` (dry run: enters the STM32's DFU bootloader, backs up the whole flash, compares, reboots).
2. `python xdrive/tools/usb_flash.py --elf Firmware/build/ODriveFirmware.elf --write`
- The first backup under `backups/` is the only way back to the board's original firmware, so keep it. Restore with `--bin backups/<dir>/flash.bin --write`.
- The tool enters the bootloader through the running firmware's `enter_dfu_mode()` (tested from this firmware; not yet from Makerbase's). A board already in the bootloader also works.
- `xdrive/tools/swd_flash.py` flashes the same way over SWD (ST-Link and OpenOCD).
- Flashing from Makerbase's firmware, or across a major version, resets the board's config.

**Configure a DJI 10018** (for other motors, start from the example and change the motor values)
1. Read the comment at the top of `xdrive/examples/dji-10018.json`, and change the supply, brake resistor and encoder parity settings to match your setup.
2. `python xdrive/tools/set_config.py --file xdrive/examples/dji-10018.json`
3. `python xdrive/tools/set_config.py --save axis0.config.startup_encoder_offset_calibration=false` (the board saves and reboots, which applies the SPI encoder mode).
4. Motor moves: `python xdrive/tools/calibrate.py --motor --offset --correction`
5. Motor moves: `python xdrive/tools/set_config.py --save axis0.encoder.config.pre_calibrated=true axis0.config.startup_closed_loop_control=true` (the board reboots into closed loop).
6. `python xdrive/tools/dump_board.py --compare xdrive/examples/dji-10018.json` (lists any setting that differs, and the board's errors).

**CAN**
- J3 is a 2-pin GH1.25 connector: pin 1 CAN_L, pin 2 CAN_H, no ground pin. Wiring, termination and the adapter ground are in `xdrive/docs/board-findings.md`.
- Set `can.config.baud_rate` (e.g. 1000000) and `axis0.config.can.node_id`, then save.

## Host tools (`xdrive/tools/`)

Each tool's docstring gives its usage. "Motor moves" means the tool drives the motor or reboots the board.

| Tool | What it does |
|---|---|
| `dump_board.py` | Read-only snapshot of every property with decoded errors, plus a config backup; `--compare` diffs against a settings file |
| `set_config.py` | Changes settings safely: refuses unless IDLE, dumps first, reads back, optionally saves |
| `idle.py` | The stop command: puts axis0 in IDLE |
| `calibrate.py` | Motor moves. Motor, encoder offset and correction-table calibration, one state at a time |
| `reboot_watch.py` | Motor moves. Reboots and prints the startup state transitions and errors |
| `usb_flash.py`, `swd_flash.py` | Motor moves (reboot). Flash over USB DFU or SWD, with a whole-flash backup and read-back checks |
| `swd_backup.py` | Read-only whole-flash backup over SWD |
| `correction_table.py` | Reads, saves, restores or smooths the encoder correction table |
| `capture.py` | Records up to 8 properties at 8 kHz with the firmware's capture |
| `sample.py` | Read-only ~150 Hz sampler over USB |
| `move_test.py`, `hold_ab.py`, `disturb_test.py` | Motor moves. Trapezoidal moves, hold-noise comparisons and disturbance rejection, logged |
| `safety_test.py`, `impedance_test.py`, `regen_test.py`, `capture_test.py` | Bench tests of the added features with PASS/FAIL checks (all but `capture_test.py` move the motor) |
| `regress.py` | Motor moves. Regression suite compared with a saved baseline, at a fixed rotor angle (`--hold-at`) |
| `move_to.py` | Motor moves. Turns the rotor to a fractional-turn angle and leaves it IDLE |
| `spike_hunt.py`, `brake_check.py`, `profile_loop.py` | Motor moves. Diagnostics: current-measurement glitches, hard braking, control-loop timing |
| `analyze_*.py` | Offline analysis of the logs |
| `impedance_frame.py` | Host codec for the CAN impedance command (no I/O) |

`python -m pytest -q xdrive/tools/tests` checks the host codec and the bus current limits against the firmware headers (needs `clang++`).

## Versioning

Releases are numbered from 1.0.0, independently of ODrive, and each release states its ODrive base. Upstream ODrive firmware for v3.x boards ends at 0.5.6, so a v3.6 board reporting 1.x runs this firmware. A major version marks a config-layout change: flashing across it resets the board's config. A build of any commit after a release tag, or of a modified tree, reports that release's version with `fw_version_unreleased = 1`. Releases, with the ELF, BIN and HEX images and their SHA-256 sums, are on the GitHub releases page; `CHANGELOG.md` lists what each one changes.

## Support

Issues and feature requests are welcome, including uses beyond robot arms. Support is not promised.

## License

MIT (`LICENSE.md`), as is the ODrive code this builds on.
