# Hardware

The MKS XDRIVE Mini is a single-motor clone of the ODrive v3.6: an STM32F405, one DRV8301 gate driver, 60 V FETs, low-side current shunts on phases B and C, an onboard AS5047 encoder and a brake half-bridge. It reports itself as an ODrive v3.6, 56 V variant, so the firmware uses ODrive v3.6's pin assignments. Facts here come from Makerbase's schematic ([makerbase-motor/MKS-ODrive](https://github.com/makerbase-motor/MKS-ODrive), `Hardware/MKS ODrive MINI`) unless marked as checked on a board; `docs/board-findings.md` records how each board fact was established.

## Connectors

| Connector | Pins | Use |
|---|---|---|
| Power and motor terminal | 5 positions, pluggable screw terminal | DC+ and DC− from the supply, and the three motor phases (checked on a board) |
| Brake resistor terminal | 2 | The brake resistor, driven by a half-bridge (two FETs and an LM5109B driver) |
| USB | | odrivetool and the host tools; the board is visible only while the DC bus is powered (checked on a board) |
| J1 | 2, jumper | Fits the onboard 120 Ω CAN terminator (R18): only on the board at the end of the bus |
| J2 | 5, JST-GH 1.25 mm | SWD (checked on a board) |
| J3 | 2, JST-GH 1.25 mm | CAN |
| J4 | 6, JST-GH 1.25 mm | SPI, for an external SPI encoder |
| J5 | 5, JST-GH 1.25 mm | Incremental encoder (A, B, Z) |
| J6 | 6, JST-GH 1.25 mm | GPIO1 to GPIO4 |
| S1 | button | Reset |
| S2 | button | Pulls BOOT0 high: held through a reset (S1), the board starts in the STM32's built-in DFU bootloader |

### Header pinouts

| Pin | J2 SWD | J3 CAN | J4 SPI | J5 encoder | J6 GPIO |
|---|---|---|---|---|---|
| 1 | 3V3 | CAN_L | 3V3 | 5V | GND |
| 2 | SWCLK | CAN_H | GPIO6 (chip select) | Z (GPIO11) | 5V |
| 3 | GND | | SCK | B (GPIO10) | GPIO4 |
| 4 | SWDIO | | MISO | A (GPIO9) | GPIO3 |
| 5 | NRST | | MOSI | GND | GPIO2 |
| 6 | | | GND | | GPIO1 |

- J2 is checked on a board; the other headers are from the schematic.
- J3 has no ground pin: see [CAN](can.md#wiring).
- J4 shares SPI3 with the onboard encoder and the gate driver. An external encoder on it needs its own chip select: GPIO6.
- J5's A, B and Z lines have 3.3 kΩ pull-ups to 3.3 V; the connector supplies 5 V to the encoder.

## GPIOs

The firmware numbers GPIOs as ODrive v3.6 does. On the Mini:

| GPIO | MCU pin | Reaches | Input filter | Default mode | Other modes |
|---|---|---|---|---|---|
| 1 | PA0 | J6 pin 6 | 3.3 kΩ, 100 pF | `UART_A` (TX) | digital, analog in, PWM input, mechanical brake |
| 2 | PA1 | J6 pin 5 | 3.3 kΩ, 100 pF | `UART_A` (RX) | digital, analog in, PWM input, mechanical brake |
| 3 | PA2 | J6 pin 4 | none | `ANALOG_IN` | digital, `UART_B` (TX), PWM input, mechanical brake |
| 4 | PA3 | J6 pin 3 | none | `ANALOG_IN` | digital, `UART_B` (RX), PWM input, mechanical brake |
| 5 | PC4 | not connected | | `ANALOG_IN` | |
| 6 | PB2 | J4 pin 2 | 3.3 kΩ, 100 pF | `DIGITAL` | chip select for an external SPI encoder, digital |
| 7 | PA15 | the onboard AS5047's chip select | 3.3 kΩ, 100 pF | `DIGITAL` | reserved: `encoder.config.abs_spi_cs_gpio_pin = 7` |
| 8 | PB3 | not connected | | `DIGITAL` | |
| 9, 10 | PB4, PB5 | J5 A, B | 3.3 kΩ pull-up | `ENC0` | digital |
| 11 | PC9 | J5 Z | 3.3 kΩ pull-up | `DIGITAL_PULL_DOWN` | encoder index |
| 12 to 14 | PB6, PB7, PC15 | not connected (the second encoder on dual-motor boards) | | `DIGITAL_PULL_DOWN` | |
| 15, 16 | PB8, PB9 | the CAN transceiver | | `CAN_A` | |

- Modes are set by `odrv0.config.gpioN_mode` (values in the [property reference](reference.md#gpiomode)) and take effect after a save and reboot. A feature works only on a GPIO set to its mode, and needs its own enable as well (`config.enable_uart_a`, for example).
- "Digital" covers step and direction inputs, enable inputs, endstops and encoder chip selects.
- Drive the GPIOs with 3.3 V logic: whether the Mini's GPIOs tolerate 5 V isn't checked. They share the board's ground, the DC bus negative: see [ground loops](safety-and-regen.md#ground-loops).
- The second motor's gate drive and chip select pins (PA7, PB0, PB1, PC6 to PC8, PC14) and current sense inputs (PC2, PC3) are not connected on the Mini.

## Sensing

- **Phase currents:** two low-side shunts (phases B and C) through the DRV8301's amplifiers, sampled by ADC2 and ADC3 at each update of TIM1, the PWM timer. `motor.config.requested_current_range` sets the amplifier gain: at 20 A, the measurement saturates at about 33.8 A.
- **Bus voltage:** ADC1, sampled with the phase currents.
- **FET temperature:** an onboard thermistor (`motor.fet_thermistor`).

## Timing

PWM runs at 24 kHz, center-aligned on TIM1. Every second TIM1 update (8 kHz), at the bottom of its count where the low-side FETs conduct, ADC1's end-of-conversion interrupt samples the encoder and starts the control loop. The top-of-count sample (high-side FETs on, no shunt current) calibrates the current amplifiers' offsets. The loop takes about 73 µs of the 125 µs period on the test stand.
