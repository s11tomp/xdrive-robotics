# Migrating from Makerbase's firmware

A Mini ships with Makerbase's build of ODrive v0.5.1. This firmware is based on ODrive v0.5.6, so moving to it crosses ODrive's own changes from v0.5.1 to v0.5.6 as well as this firmware's. This page lists what changes for an existing setup and how to carry a board's settings over.

## Before flashing

- **Back up the board's config:** the tools talk only to this firmware. A stock board's config can be dumped with the tools at the tag `xdrive/v0.5.1`: `python tools/dump_board.py --label stock` writes every property to `logs/<stamp>_<serial>_stock_dump.json` and a config backup next to it. The flash backup below also holds the config sectors.
- **Keep the flash backup:** in the bootloader, `usb_flash.py` reads the whole flash to `backups/` before writing. That image is the only way back to Makerbase's firmware: `python tools/usb_flash.py --bin backups/<dir>/flash.bin --write`. Makerbase's published images are other v0.5.1 builds, not necessarily the one on a given board.
- **Entering the bootloader:** hold S2 while pressing S1 (reset): the board starts in the STM32's DFU bootloader, and `usb_flash.py` picks it up there. From this firmware, `usb_flash.py` also enters the bootloader itself (`enter_dfu_mode()`); `swd_flash.py --no-usb` flashes over SWD without a board on USB.

## What resets

Flashing resets the board's config: the stored config's layout differs between the two firmwares. Calibration results (phase resistance and inductance, the encoder offset) are part of the config, so the board needs calibrating again ([Getting started](getting-started.md)).

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

Everything under `axis1` is gone (see below). Every other setting this firmware has is listed, with units, in the [property reference](reference.md).

## Behavior that changes

From ODrive v0.5.2 (the notes below adapt ODrive's v0.5.1 to v0.5.2 migration guide):

- **Saving reboots.** `save_configuration()` saves and reboots the board, and its startup sequence runs. On v0.5.1 it saved without rebooting, and afterwards the motor got no current until a manual reboot.
- **GPIO modes are explicit.** Each GPIO has a mode (`odrv0.config.gpio1_mode` and so on, values in `GpioMode` in the [property reference](reference.md#gpiomode)), and a feature works only on a GPIO set to its mode: step and direction inputs, for example, need `GPIO_MODE_DIGITAL`. Changes take effect after a save and reboot.
- **The brake resistor must be enabled:** `odrv0.config.enable_brake_resistor = True`, then save (the board reboots). v0.5.1 always assumed a resistor was connected.
- **Step/direction counts absolute steps.** It needs circular setpoints, and `axis0.config.turns_per_step` is replaced by a step count per circular range:

  ```python
  odrv0.axis0.controller.config.circular_setpoints = True
  odrv0.axis0.controller.config.circular_setpoint_range = 1.0
  odrv0.axis0.controller.config.steps_per_circular_range = 1024   # was turns_per_step = 1/1024
  ```

  Powers of 2 for both values avoid rounding error.

From this firmware:

- **One axis.** `axis1`, the ghost of the Mini's missing second motor, is gone. On v0.5.1 it reported errors of its own and sent CAN heartbeats and encoder estimates as node 1 by default, so a second board at node 1 collided with it. Each board is now one CAN node, set by `axis0.config.can.node_id`.
- **AS5047 checks are configurable.** Makerbase's build turned off the encoder's parity and error-flag checks. Here they are settings (`axis0.encoder.config.abs_spi_check_parity`, `abs_spi_reject_error_flag`): parity on for an AS5047P, off for an AS5047U, which sends none. [Encoders](encoders.md) has the details.
- **The watchdog's action** is decelerate-and-hold by default (`axis0.config.watchdog_action`) once the watchdog is enabled; v0.5.1 disarmed the motor. Every other added safety and regen feature is off until set ([Safety and regen](safety-and-regen.md)).
- **Entering closed loop starts from rest:** zero velocity and torque setpoints, no running trajectory.
- **Removed:** `INPUT_MODE_MIRROR`, `controller.config.load_encoder_axis` and `GPIO_MODE_ENC1`, which served the second axis. `CHANGELOG.md` lists every change. A board that saved `gpio12_mode`/`gpio13_mode = 12` (ENC1) under stock firmware keeps that number after the flash and reports `misconfigured = True`; set both to 2 (`DIGITAL_PULL_DOWN`) and save.
