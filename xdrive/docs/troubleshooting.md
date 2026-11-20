# Troubleshooting

## Reading errors

`python xdrive/tools/dump_board.py` prints every error on the board, decoded, along with the full config. Errors live in RAM: they clear on `odrv0.clear_errors()` (CAN: Clear Errors, 0x018) or a power cycle. Every error bit is described in the [property reference](reference.md#enums-and-error-bits), under `Error` (the board), `Axis.Error`, `Motor.Error`, `Encoder.Error` and `Controller.Error`.

`python xdrive/tools/idle.py` puts the axis in IDLE (no torque) and prints the errors.

## Common errors on the Mini

| Error | Likely cause | What to do |
|---|---|---|
| `MOTOR_ERROR_CURRENT_LIMIT_VIOLATION` at speed | An off-center encoder magnet: the 4x-per-turn current ripple grows with speed squared | Record a [correction table](encoders.md#correction-table); check the magnet's centering |
| `MOTOR_ERROR_CURRENT_SENSE_SATURATION` | Phase current beyond the amplifier's range (about 33.8 A at `requested_current_range = 20`) | Raise `requested_current_range` (save and reboot), or lower `current_lim` |
| `ENCODER_ERROR_CPR_POLEPAIRS_MISMATCH` during offset calibration | The encoder moved a different distance than `pole_pairs` and `cpr` predict, by more than `calib_range` | Check `pole_pairs` (magnets / 2) and `cpr` (16384); a rotor that stalls or slips during the scan (too little `calibration_current`, or a load) does this too |
| `ODRIVE_ERROR_DC_BUS_OVER_VOLTAGE` after a stop | Regen with nowhere to go | Enable and size the brake resistor, or set regen limits ([Safety and regen](safety-and-regen.md#regen-where-braking-energy-goes)) |
| `AXIS_ERROR_WATCHDOG_TIMER_EXPIRED`, or `controller.timeout_active` | No feed (USB `watchdog_feed()` or any CAN frame to the board) within `watchdog_timeout` | Feed faster than the timeout; after a hold, feed and then `clear_errors()` |
| `CONTROLLER_ERROR_POS_FOLLOWING_ERROR` or `VEL_FOLLOWING_ERROR` | The joint couldn't follow: a jam, a collision, too little current for the move, or encoder slip | Find the cause before raising `max_pos_error` or `max_vel_error` |
| `CONTROLLER_ERROR_POS_LIMIT_VIOLATION` | Torque or impedance control drove past `pos_min`/`pos_max` by more than `pos_limit_margin`, or closed loop was entered outside the limits | Move the joint inside the limits in IDLE, then enter closed loop |

## Connection

- **No board on USB:** the MCU runs off the DC bus, so the board appears on USB only while the supply is on.
- **Is it running this firmware?** Releases report version 1.0.0 or later (`odrv0.fw_version_major`, `fw_version_minor`, `fw_version_revision`); Makerbase's firmware reports 0.0.0. `odrv0.axis1` doesn't exist on this firmware.
- **Unresponsive or crashed firmware:** hold S2 while pressing S1 (reset) to start the STM32's built-in bootloader, then flash with `usb_flash.py`, which picks up a board already in the bootloader. Over SWD, `swd_flash.py` can reach a crashed build when NRST is wired (J2 pin 5). The whole-flash backups in `backups/` restore any earlier state: `usb_flash.py --bin backups/<dir>/flash.bin --write`.
- **USB drops under load:** route the USB cable away from the motor and supply cables, and see [ground loops](safety-and-regen.md#ground-loops).

## Symptoms without an error

| Symptom | Likely cause | What to do |
|---|---|---|
| The motor vibrates or hums while holding | `vel_gain` too high, or encoder noise reaching the velocity loop | Follow the [tuning procedure](control.md#tuning); lower `encoder.config.bandwidth` (the 10018 settled at 500 rad/s) |
| Moves overshoot or oscillate | `pos_gain` too high for the current limit | Lower `pos_gain`, or raise `current_lim` |
| A 4x-per-turn whine or ripple that grows with speed | Encoder angle error from magnet placement | [Correction table](encoders.md#correction-table) |
| Less torque than expected, heat while holding without load | The commutation angle is off: the magnet or rotor bell slipped since the offset calibration, or the table is stale | Fix the mechanical slip, then run the offset calibration (and the correction table) again |
| The motor creeps faster and faster | The encoder slipped | As above |
| Stiffness or hold noise changes from one position to the next | Cogging (about 0.09 Nm on the 10018) | Expected; compare measurements at the same rotor angle ([Testing](testing.md)) |
| False steps with step/direction | Noise coupled into the step and direction wires | Twisted pair to the controller, away from motor and supply wires |
