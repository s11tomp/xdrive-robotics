# Migrating from Makerbase's firmware

A Mini ships with Makerbase's build of ODrive v0.5.1. This firmware is based on ODrive v0.5.6, so moving to it crosses ODrive's own changes from v0.5.1 to v0.5.6 as well as this firmware's. This page describes Makerbase's firmware, what to save before flashing, and what changes for an existing setup. The flashing itself is in [Getting started](getting-started.md#flash-the-firmware).

## Makerbase's firmware

Makerbase's source archive ([makerbase-motor/MKS-ODrive](https://github.com/makerbase-motor/MKS-ODrive), folder `MKS ODrive MINI`) is upstream ODrive `fw-v0.5.1` with three small patches:

1. The board configuration is `v3.6-56V`.
2. Only the first motor's gate driver is set up, because the second DRV8301 doesn't exist. The second axis, `axis1`, still exists on USB and CAN.
3. The AS5047 parity and error-flag checks are commented out, and a pre-calibrated absolute encoder is ready at boot without a calibration sweep.

Consequences for an existing setup:

- **The ghost `axis1`** reports errors of its own (it latches `CURRENT_MEASUREMENT_TIMEOUT` after a save) and sends CAN heartbeats and encoder estimates as node 1 by default, so a second board at node 1 collides with it.
- **Every encoder frame is used as a real position,** flagged or corrupted, and `encoder.spi_error_rate` always reads 0. A corrupted frame becomes a false jump and a large current demand, which fits reports of random current-limit faults.
- **`save_configuration()` doesn't reboot,** and afterwards the motor gets no current until a reboot: the current loop winds up to full voltage and nothing flows. `erase_configuration()` does reboot.
- **The brake resistor is always assumed connected** (v0.5.1 has no `enable_brake_resistor`). The firmware adds the computed brake current back into the bus-current sum, so regen always looks absorbed: `DC_BUS_OVER_REGEN_CURRENT` trips only once the brake duty cycle saturates at 95 % (about 0.95 × 24 V / 2 Ω ≈ 11 A with the stock resistor at 24 V). Without a resistor connected, regen pumps the bus voltage up to `dc_bus_overvoltage_trip_level`.
- **CANSimple implements commands 0x00 to 0x18.** The ODrive v0.5.x releases after it added cyclic encoder messages, the trajectory-done flag in the heartbeat, gains over CAN (0x1A, 0x1B), and heartbeat error flags with configurable cyclic rates; [CAN](can.md#messages) lists them all.

More than one v0.5.1 build circulates: Makerbase's release `ODriveMINI-fw-v0.5.1-20250326` and an earlier build share their vector table and strings, but the earlier one is 56 bytes larger. Both report firmware version 0.0.0, because Makerbase built outside git. [Development](development.md#rebuilding-makerbases-firmware) shows how to rebuild the 20250326 release byte for byte.

Stock ODrive v0.5.6 doesn't drive the Mini at all: it retries the missing second gate driver's setup every millisecond, flooding the SPI bus the encoder shares. This firmware has one axis and no second gate driver.

## Before flashing

- **The flash backup:** `usb_flash.py` reads the whole flash to `backups/<stamp>_<serial>_pre-flash/` before writing, the config sectors included. That image is the only way back to the board's own firmware and settings: `python tools/usb_flash.py --bin backups/<dir>/flash.bin --write`. Makerbase's published images are other v0.5.1 builds, not necessarily the one on a given board. Keep the backup.
- **The settings as values:** the tools in this repository talk only to this firmware, so they can't read a board on Makerbase's firmware. ODrive's `odrivetool backup-config`, from ODrive's Python package at version 0.5.1, writes a stock board's settings to a JSON file that `set_config.py --file` reads later; it is untested with this repository. Otherwise, write down the motor, encoder, limit and CAN settings by hand.
- **Entering the bootloader:** the tools can't ask Makerbase's firmware to enter the STM32's DFU bootloader. Hold S2 while pressing S1 (reset): the board starts in the bootloader, and `usb_flash.py` picks it up there. `swd_flash.py --no-usb` flashes over SWD instead, without the board on USB.

## What resets

Flashing resets the board's config: the stored config's layout differs between the two firmwares, so the new firmware starts from its defaults. Calibration results (phase resistance and inductance, the encoder offset) are part of the config, so the board needs configuring and calibrating again ([Getting started](getting-started.md#configure-and-calibrate)).

## Carrying settings over

`set_config.py --file <backup>.json` applies a config backup from the stock firmware, skips every key this firmware doesn't have, and lists them. The renamed ones carry the same meaning under a new name; set them by hand:

| Makerbase v0.5.1 | This firmware |
|---|---|
| `axis0.config.can_node_id` | `axis0.config.can.node_id` |
| `axis0.config.can_node_id_extended` | `axis0.config.can.is_extended` |
| `axis0.config.can_heartbeat_rate_ms` | `axis0.config.can.heartbeat_rate_ms` |
| `config.enable_i2c_instead_of_can` | `config.enable_i2c_a` and `config.enable_can_a` |
| `axis0.motor.config.direction` | `axis0.encoder.config.direction` |
| `axis0.encoder.config.offset` | `axis0.encoder.config.phase_offset` |
| `axis0.encoder.config.offset_float` | `axis0.encoder.config.phase_offset_float` |
| `axis0.controller.config.enable_current_mode_vel_limit` | `axis0.controller.config.enable_torque_mode_vel_limit` |
| `axis0.fet_thermistor.*` | `axis0.motor.fet_thermistor.*` |
| `axis0.motor.current_control.Ibus` (read-only) | `axis0.motor.I_bus` |
| `axis0.motor.gate_driver.drv_fault` (read-only) | `axis0.last_drv_fault` |

One setting keeps its name but changes its values: **`can.config.protocol`** is an enum on v0.5.1, where 0 is CANSimple; here it is a set of flags, where CANSimple is 1 and 0 turns CAN messaging off. A v0.5.1 backup carries 0, so set it to 1 after applying the backup. With 0, the CAN controller runs but the board neither sends nor answers anything.

Everything under `axis1` is gone. Every other setting is listed, with units, in the [property reference](reference.md).

## Behavior that changes

From ODrive v0.5.2 (adapted from ODrive's v0.5.1 to v0.5.2 migration notes):

- **Saving reboots.** `save_configuration()` saves and reboots the board, and its startup sequence runs. When the flash store fails, the board still reboots, on the config saved before, and `config_save_failed` reads true.
- **GPIO modes are explicit.** Each GPIO has a mode (`config.gpio1_mode` and so on, values in `GpioMode` in the [property reference](reference.md#gpiomode)), and a feature works only on a GPIO set to its mode: step and direction inputs, for example, need `GPIO_MODE_DIGITAL`. Changes take effect after a save and reboot. [Hardware](hardware.md#gpios) lists the Mini's GPIOs.
- **The brake resistor must be enabled:** `config.enable_brake_resistor = true`, then save (the board reboots).
- **Step/direction counts absolute steps.** It needs circular setpoints, and a step count per circular range replaces `axis0.config.turns_per_step`:

  ```sh
  python tools/set_config.py axis0.controller.config.circular_setpoints=true \
      axis0.controller.config.circular_setpoint_range=1.0 \
      axis0.controller.config.steps_per_circular_range=1024    # turns_per_step = 1/1024 on v0.5.1
  ```

  Powers of 2 for both values avoid rounding error.

From this firmware:

- **New host software.** ODrive's `odrivetool` and its `odrive` Python package do not work with this firmware. The [host tools](tools.md) and the [Python library](python-library.md) replace them.
- **One axis.** `axis1` doesn't exist. Each board is one CAN node, set by `axis0.config.can.node_id`.
- **AS5047 checks are settings** (`axis0.encoder.config.abs_spi_check_parity`, `abs_spi_reject_error_flag`), off by default, plus a jump check that is on: parity on for an AS5047P, off for an AS5047U, which sends none. [Encoders](encoders.md#frame-checks) has the details.
- **The watchdog's action** is decelerate-and-hold by default (`axis0.config.watchdog_action`) once the watchdog is enabled, instead of disarming the motor. Every other added safety and regen feature is off until set ([Safety and regen](safety-and-regen.md)).
- **Entering closed loop starts from rest:** zero velocity and torque setpoints, no running trajectory.
- **Removed:** `INPUT_MODE_MIRROR`, `controller.config.load_encoder_axis` and `GPIO_MODE_ENC1`, which served the second axis. `CHANGELOG.md` lists every difference from ODrive v0.5.6. A board with `gpio12_mode` or `gpio13_mode` at 12 (ENC1's number, which this firmware doesn't define) reports `misconfigured = True`; set both to 2 (`DIGITAL_PULL_DOWN`) and save.
