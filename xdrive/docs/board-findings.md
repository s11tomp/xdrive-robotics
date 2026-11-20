# MKS XDRIVE Mini: board findings

Facts about the MKS XDRIVE Mini, Makerbase's stock firmware and this firmware's behavior on it. Each fact says how it is known: **verified** (checked on a board, in source code or in a build), **schematic** (read from Makerbase's schematic, not checked on a board) or **measured** (on one board with a DJI 10018 at 24 V).

## Hardware
- **MCU and power stage:** STM32F405, one DRV8301 gate driver, two 0.5 mΩ low-side shunts (phases B and C), 60 V FETs, an onboard AS5047 encoder, and a brake half-bridge (two FETs driven by an LM5109B) with a 2-pin screw terminal. One motor channel. Schematic and BOM: [makerbase-motor/MKS-ODrive](https://github.com/makerbase-motor/MKS-ODrive), folder `MKS ODrive MINI`.
- **The MCU runs off the DC bus:** the board appears on USB only while the supply is on (verified).
- **Identity:** the board reports hw 3.6, 56 V variant (`hw_version_variant` 56), so ODrive firmware treats it as an ODrive v3.6-56V (verified).
- **SWD header J2** (JST-GH 1.25 mm, 5-pin): 1 = 3V3, 2 = SWCLK, 3 = GND, 4 = SWDIO, 5 = NRST (verified). With the board powered, SWCLK reads about 0 V (pull-down) and SWDIO about 3.3 V (pull-up), which tells the two apart. GND, SWCLK and SWDIO suffice for reading; wire NRST to the probe's RST for connect-under-reset.
- **CAN connector J3** (GH1.25, 2-pin): see CAN below.
- **SPI header** (GH1.25, 6-pin: MOSI, MISO, SCK, a GPIO for chip select, 3V3, GND): a candidate for an external encoder (schematic; pinout not checked).
- **The second motor's MCU pins are unconnected** (schematic): the M1 nets (gate drive PA7, PB0, PB1, PC6 to PC8; current sense PC2, PC3; chip select PC14; encoder index PC15; thermistor) appear only as labels at the MCU, while every M0 net also appears at the gate driver or its sensors.
- **Buttons:** S1 is reset; S2 pulls BOOT0 to 3V3 (R30 pulls it down), so holding S2 through a reset starts the STM32's built-in bootloader even with broken firmware (schematic).

## Makerbase's stock firmware
- **It is ODrive v0.5.1 with small patches** (verified by diffing Makerbase's source archive against upstream `fw-v0.5.1`):
  1. `tup.config`: `CONFIG_BOARD_VERSION=v3.6-56V`.
  2. `main.cpp`: only `axes[0]->motor_.setup()` runs, because the second DRV8301 doesn't exist. `axis1` still exists in the interface and on CAN as a ghost.
  3. `encoder.cpp`: the AS5047 parity and error-flag checks are commented out; `check_pre_calibrated()` no longer clears `pre_calibrated`; and a `pre_calibrated` encoder of any non-incremental mode is ready at boot (upstream: hall and sincos only).
- **Makerbase changed no pins.** Stock ODrive v0.5.6 fails on the Mini because it retries the missing second gate driver's setup every millisecond, flooding the SPI bus the encoder shares (verified in source; this firmware has no second gate driver).
- **More than one v0.5.1 build is in circulation.** Makerbase's 2025-03-26 release (`ODriveMINI-fw-v0.5.1-20250326`) and an earlier build share their vector table and strings, but the earlier one is 56 bytes larger around `check_pre_calibrated()` (verified). Both report fw 0.0.0, because Makerbase built outside git.
- **The ghost `axis1`** of Makerbase's firmware reports errors of its own: on v0.5.1 it latches `CURRENT_MEASUREMENT_TIMEOUT` after a save, and on a stock v0.5.6 build it reports the missing gate driver (verified). It also sends CAN heartbeats and encoder estimates as node 1 by default, so on a shared bus its node ID must not collide with a real board's. This firmware has no `axis1`.
- **v0.5.1 `save_configuration()` does not reboot,** and afterwards the motor gets no current until a reboot: the current loop winds up to full voltage and nothing flows (verified). Save, then reboot. `erase_configuration()` reboots. On v0.5.2 and later, including this firmware, a save reboots the board and its startup sequence runs.

## Encoder
- **The BOM says AS5047U; the board checked behaves as an AS5047P** (measured): bit 15 was even parity in 600 of 600 frames, and the error flag (bit 14) never appeared in millions of frames. An AS5047U frame has no parity (bit 15 is a warning flag), so check each board: with `encoder.config.abs_spi_check_parity` off, `encoder.spi_parity_error_count` staying at 0 means the chip sends parity.
- **The stock firmware uses every frame as a real position,** flagged or corrupted, and `encoder.spi_error_rate` always reads 0 (verified in source). A false jump becomes a large current demand, which fits reports of random current-limit faults.
- **Commutation uses the raw encoder count** (plus interpolation), not the PLL estimate, so `encoder.bandwidth` affects only the position and velocity loops (verified in source).
- **Magnet placement matters.** An off-center magnet gives an angle error that repeats every turn. One measured mount had 1.34° at 4x per turn and 0.28° at 2x, the same over two days. The error leaks back-EMF into the d axis, and the resulting current ripple grows with speed squared: at 24 V with no correction it caused `MOTOR_ERROR_CURRENT_LIMIT_VIOLATION` at about 12 turn/s.
- **Correction table results** (measured, this firmware's `AXIS_STATE_ENCODER_CORRECTION_CALIBRATION`):
  - ripple at 6 turn/s: velocity −94 %, Iq −92 %; peak current at cruise 7.5 → 1.4 A;
  - with the table, a DJI 10018 ran cleanly up to 21 turn/s at 24 V;
  - the table must be limited to harmonics 1 to 12: the raw bins also record cogging (36x and 42x per turn on a 36-slot, 42-magnet motor) as encoder error, which makes things worse;
  - a table can't fix a magnet that shifts, errors not locked to angle (noise, SPI glitches), or an air gap that changes with load or temperature. Each motor and mount needs its own table.

## Brake resistor and bus current (stock v0.5.1)
- **v0.5.1 has no `enable_brake_resistor`** (added in v0.5.2) and always assumes a resistor is connected (verified in source). `update_brake_current()` computes a brake duty for `brake_resistance` and adds that current back to the bus-current sum, so regen always looks absorbed: `DC_BUS_OVER_REGEN_CURRENT` can only trip once the brake duty saturates at 95 % (about 0.95 × Vbus / 2 Ω ≈ 11 A at 24 V).
- **Without a resistor connected,** regen pumps the bus voltage, and a supply that can't sink current with it, up to `dc_bus_overvoltage_trip_level`. Keep the trip level a few volts above the supply voltage.
- `DC_BUS_OVER_CURRENT` (the drawing direction) is not compensated: it trips on the raw per-cycle bus current against `dc_max_positive_current`.

| Error (v0.5.1 name) | Trips when |
|---|---|
| `MOTOR_ERROR_CURRENT_LIMIT_VIOLATION` 0x1000 | \|I_dq\| > `effective_current_lim` + `current_lim_margin` (default 8 A) |
| `MOTOR_ERROR_DC_BUS_OVER_CURRENT` 0x8000 | raw bus current > `dc_max_positive_current` |
| `MOTOR_ERROR_DC_BUS_OVER_REGEN_CURRENT` 0x4000 | bus current < `dc_max_negative_current` after brake compensation (only when the brake saturates) |
| `MOTOR_ERROR_CURRENT_SENSE_SATURATION` 0x400 | phase current beyond the amplifier range (about 33.8 A with `requested_current_range = 20`) |
| `MOTOR_ERROR_MODULATION_MAGNITUDE` 0x80 | out of voltage |
| `AXIS_ERROR_DC_BUS_OVER_VOLTAGE` 0x4 | bus voltage > trip level |
| `CONTROLLER_ERROR_OVERSPEED` 0x1 | speed > `vel_limit` × `vel_limit_tolerance` |

## CAN
- **Connector J3** (schematic): GH1.25 2-pin, pin 1 = CAN_L, pin 2 = CAN_H, **no ground pin**. Transceiver: SN65HVD232 (3.3 V).
- **Onboard terminator** (schematic): R18 (120 Ω) across CAN_H/CAN_L in series with jumper J1. Fit it only on the board at the far end of the bus. With the adapter's terminator also on, CAN_H to CAN_L measures about 60 Ω with the power off (40 Ω means three terminators, 120 Ω means one).
- **Topology:** each board has one CAN connector, so boards tap off a twisted-pair trunk on short stubs (at most about 0.3 m at 1 Mbit/s) instead of daisy-chaining.
- **Ground:** the USB-CAN adapter's ground must reach the boards' ground some other way, since J3 doesn't carry it: the supply negative, at one point.
- **Protocol versions** (verified in source): v0.5.1's CANSimple implements commands 0x00–0x18. The v0.5.x line then added cyclic encoder messages (0.5.2), the trajectory-done flag (0.5.3), gains over CAN (0.5.4), and heartbeat error flags with configurable cyclic rates (0.5.6). This firmware adds the impedance command (0x1E).
- **The ODriveArduino library's `ODriveCAN` speaks the 0.6.x protocol** (verified in source). Against v0.5.1, `setPosGain()` (0x1A) and `setVelGains()` (0x1B) are silently ignored, `setLimits()` applies only the velocity limit, `Get_Bus_Voltage_Current` returns voltage only, and the heartbeat lacks the 0.6 fields.

## Bootloader and flashing
- **Flash layout:** 1 MB; sectors 0–3 are 16 KB, sector 4 is 64 KB, sectors 5–11 are 128 KB. ODrive keeps its config in sectors 10–11, so flashing only the image's sectors keeps the config (verified).
- **No protection out of the box** on the board checked: RDP level 0, no write-protected sectors (verified).
- **The STM32's built-in DFU bootloader** (verified): USB 0483:df11, bcdDevice 0x2200, with the same USB serial as the firmware, so a board is found by serial in either mode. Alternate settings: 0 internal flash (`04*016Kg,01*064Kg,07*128Kg`), 1 option bytes, 2 OTP, 3 device feature. The DFU functional descriptor (wTransferSize 2048) follows alternate 3, not alternate 0. Flash reads run at about 319 KiB/s.
- **Entering the bootloader is safe on the Mini** (schematic): the bootloader pulls up PB10/PB11 (USART3), which are AUX_L/AUX_H, the brake half-bridge's inputs. 3.3 kΩ pull-downs (R24 on AUX_L, R21 on AUX_H) hold them near 0.25 V, as on ODrive v3.5 and later. Without them both brake FETs would turn on and short the bus.
- **`odrive.dfuse` in the odrive 0.5.1 Python package is broken on Python 3.9 and later** (verified): it calls `fractions.gcd`. `xdrive/tools/usb_flash.py` has its own DfuSe client.
- **Don't use `st-info` or `st-flash` on a running board:** they halt the core on connect, which freezes the PWM on the windings. OpenOCD with `reset_config none` reads without halting (`xdrive/tools/swd_backup.py`).

## Firmware details
- Writing `motor.config.current_control_bandwidth` recomputes the current-loop gains live (p = bw × L, i = R × bw) (verified).
- The stock `get_oscilloscope_val()` buffer is hard-wired (Ialpha, triggered on the d-axis voltage integral). This firmware replaces it with `odrv.capture`.
- fibre v0.5's `SimpleSerializer::read` treats a null end pointer as an unbounded buffer: calling a generated endpoint handler with a default-constructed (null) input buffer decodes bytes from address 0 into a read-write property. An empty input needs a non-null pointer with zero length (verified).
- `controller.config.load_encoder_axis` switches both position and velocity to the other encoder (`select_encoder()` in `controller.cpp`), so stock firmware can't run position from an output encoder and velocity from the motor encoder.

## DJI 10018 on the Mini
- 77 KV, 42 magnets (`pole_pairs = 21`), 36 slots. Torque constant 8.27 / 77 ≈ 0.1074 Nm/A (the ODrive default of 0.04 makes every gain act 2.7x stronger in amps).
- Voltage ceiling at 24 V: about 23.4 turn/s (measured); faster needs a higher bus voltage or field weakening.
- These are propeller-cooled drone motors. Without airflow, copper loss is 1.5 × R × I²: about 8 W at 10 A and 19 W at 15 A. Give the motor and the brake resistor somewhere to shed heat.
- Settings used on the bench: `xdrive/examples/dji-10018.json`.

## Sources
- Makerbase: https://github.com/makerbase-motor/MKS-ODrive (MINI source, binaries, schematic)
- Upstream ODrive: https://github.com/odriverobotics/ODrive (tags `fw-v0.5.1`, `fw-v0.5.6`)
- A setup and tuning guide for the Mini: https://github.com/justlovescience/MKS-XDRIVE-MINI
- SimpleFOC firmware for the Mini: https://github.com/simplefoc/mks_xdrive_mini_firmware
