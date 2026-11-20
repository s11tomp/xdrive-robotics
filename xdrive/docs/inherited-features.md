# Inherited features

The firmware keeps ODrive v0.5.6's other interfaces and features unchanged. None of them is tested on the Mini; ODrive's v0.5.6 documentation describes them, with two differences that apply throughout:

- The Mini has one axis, so ignore everything about `axis1` and the second motor.
- The Mini exposes fewer GPIOs than an ODrive v3.6: GPIO1 to GPIO4 on J6, GPIO6 on J4, and the encoder inputs on J5. [Hardware](hardware.md#gpios) lists which modes each one supports.

| Feature | ODrive v0.5.6 page | Pins on the Mini |
|---|---|---|
| Step and direction input | [Step & Direction](https://docs.odriverobotics.com/v/0.5.6/step-direction.html) | Any digital GPIO on J6 or J4; needs circular setpoints ([Migrating](migrating-from-stock.md#behavior-that-changes)) |
| RC PWM input | [RC PWM input](https://docs.odriverobotics.com/v/0.5.6/rc-pwm.html) | GPIO1 to GPIO4 (J6) |
| UART and the ASCII protocol | [UART Interface](https://docs.odriverobotics.com/v/0.5.6/uart.html), [ASCII Protocol](https://docs.odriverobotics.com/v/0.5.6/ascii-protocol.html) | UART_A on GPIO1 (TX) and GPIO2 (RX), the default; UART_B on GPIO3 and GPIO4 |
| Endstops and homing | [Endstops and Homing](https://docs.odriverobotics.com/v/0.5.6/endstops.html) | Any digital GPIO on J6 or J4 |
| Analog input | [Analog Input](https://docs.odriverobotics.com/v/0.5.6/analog-input.html) | GPIO1 to GPIO4 (J6) |
| Motor thermistor | [Thermistors](https://docs.odriverobotics.com/v/0.5.6/thermistors.html) | An analog GPIO on J6; the FET thermistor is onboard |
| Incremental, hall and other SPI encoders | [Encoders](https://docs.odriverobotics.com/v/0.5.6/encoders.html) | J5 (A, B, Z) or J4 (SPI, chip select GPIO6) |
| The native USB protocol | [Native Protocol](https://docs.odriverobotics.com/v/0.5.6/native-protocol.html) | USB |

`odrivetool` itself is ODrive's: its [v0.5.6 page](https://docs.odriverobotics.com/v/0.5.6/odrivetool.html) covers the interactive shell, config backup and the liveplotter. Don't use its firmware update (`odrivetool dfu`) on the Mini: [Getting started](getting-started.md#flash-the-firmware) explains why and what to use instead.
