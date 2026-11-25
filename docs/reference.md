# Property reference

Every object, property, function, enum and error bit the firmware exposes over USB, as the host tools and the `xdrive` library see them (`odrv.axis0.controller.config.pos_gain`). Items marked *(added)* are not in ODrive v0.5.6. Access: `rw` can be written, `ro` is read-only. Settings under a `config` object persist after `save_configuration()`; everything else resets at boot.

This file is generated from `src/odrive-interface.yaml` by `tools/gen_reference.py`; edit the interface file and run `make generate` instead of editing this file.

## Objects

### odrv0

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Error](#error) |  | rw | Board-level errors (bits in `Error`). `clear_errors()` clears them. |
| `vbus_voltage` | float32 | V | ro | Voltage on the DC bus as measured by the ODrive. |
| `ibus` | float32 | A | ro | Current on the DC bus as calculated by the ODrive.<br>A positive value means that the ODrive is consuming power from the power supply, a negative value means that the ODrive is sourcing power to the power supply.<br>This value is equal to the sum of the motor currents and the brake resistor currents. The motor currents are measured, the brake resistor current is calculated based on `config.brake_resistance`. |
| `ibus_report_filter_k` | float32 |  | rw | Filter gain for the reported `ibus`. Set to a value below 1.0 to get a smoother line when plotting `ibus`. Set to 1.0 to disable. This filter is only applied to the reported value and not for internal calculations. |
| `serial_number` | uint64 |  | ro | The MCU's unique ID, folded to 48 bits. The USB serial number is this value in hex. |
| `hw_version_major` | uint8 |  | ro | 3 on the MKS XDRIVE Mini, which reports itself as an ODrive v3.6. |
| `hw_version_minor` | uint8 |  | ro | 6 on the MKS XDRIVE Mini. |
| `hw_version_variant` | uint8 |  | ro | The board's voltage variant: 56 on the MKS XDRIVE Mini. |
| `fw_version_major` | uint8 |  | ro | Firmware version, major part. Releases of this firmware start at 1.0.0; Makerbase's stock firmware reports 0.0.0. |
| `fw_version_minor` | uint8 |  | ro | Firmware version |
| `fw_version_revision` | uint8 |  | ro | Firmware version |
| `fw_version_unreleased` | uint8 |  | ro | 0 for a build of a release tag, 1 for any other commit or a modified tree (which reports the last release's version). |
| `brake_resistor_armed` | bool |  | ro | True while the brake resistor's PWM runs. A system error disarms it; a reboot or `clear_errors()` re-arms it. |
| `brake_resistor_saturated` | bool |  | ro | Latched true once the brake duty cycle reached its 95 % limit: the resistor couldn't absorb all the regen current. |
| `brake_resistor_current` | float32 |  | ro | Commanded brake resistor current |
| `n_evt_sampling` | uint32 |  | ro | Number of input sampling events since startup (modulo 2^32) |
| `n_evt_control_loop` | uint32 |  | ro | Number of control loop iterations since startup (modulo 2^32) |
| `task_timers_armed` | bool |  | rw | Set by a profiling application to trigger sampling of a single control iteration. Cleared by the device as soon as the sampling is complete. |
| `user_config_loaded` | uint32 | bytes | ro | Size of the config loaded from flash at boot; 0 when none was loaded (for example after a flash that changed the config layout) and the defaults apply. |
| `config_save_failed` (added) | bool |  | ro | True when the `save_configuration()` call that caused this boot failed to store the config. The board reboots after every save, so after a failed one it runs on the config saved before. Any other boot clears it. |
| `misconfigured` | bool |  | ro | True when the config at boot has a problem the board could work around. The board still runs, but a feature can be missing. Causes: a GPIO in a mode it doesn't support (such as `GPIO_MODE_ENC1`'s number 12, which this firmware doesn't define); a GPIO in a mode whose feature isn't enabled (`GPIO_MODE_UART_A` without `config.enable_uart_a`); a feature the hardware lacks (`config.enable_uart_c`); or one GPIO used as an interrupt input twice (`axis0.config.step_gpio_pin` and an endstop's `gpio_num` on the same GPIO). It doesn't catch every misconfiguration. |
| `test_property` | uint32 |  | rw | A scratch value for testing the USB and CAN protocols; it has no effect. |
| `otp_valid` | bool |  | ro | True when the MCU's one-time-programmable memory holds a hardware version record. |
| `adc1_scan_enabled` (added) | bool |  | ro | Diagnostics: whether ADC1's free-running 16-channel scan (thermistors, GPIO analog inputs) runs. See `set_adc1_scan`. |

| Function | Description |
|---|---|
| `set_adc1_scan(enable: bool)` (added) | Diagnostics (RAM only): stop or restart ADC1's free-running regular scan. The bus-voltage sample (ADC1 injected, timer-triggered) keeps running. While stopped, thermistor and analog-input readings are frozen at their last value. |
| `test_function(delta: int32)` -> int32 | Adds delta to an internal counter and returns it; for testing the protocols. |
| `get_adc_voltage(gpio: uint32)` -> float32 | Reads the ADC voltage of the specified GPIO. The GPIO must be in `GPIO_MODE_ANALOG_IN`. |
| `save_configuration()` -> bool | Saves the current configuration to non-volatile memory and reboots the board, whether or not the store succeeded: check `config_save_failed` once it is back up. Returns false without saving or rebooting while the motor is armed. |
| `erase_configuration()` | Resets all `config` variables to their default values and reboots the controller |
| `reboot()` | Reboots the board without saving the current configuration. |
| `enter_dfu_mode()` | Resets into the STM32's built-in USB DFU bootloader (USB ID 0483:df11). Use it through `tools/usb_flash.py`, which puts the axis in IDLE first and flashes the board. |
| `enter_can_bootloader()` -> bool (added) | Resets into the CAN bootloader (flash sectors 0-1), which then waits for a firmware update over CAN at this board's node ID and bit rate (`tools/can_flash.py`). Returns false without resetting while the motor is armed, or when the board has no CAN bootloader. |
| `get_interrupt_status(irqn: int32)` -> uint32 | Returns information about the specified interrupt number. |
| `get_dma_status(stream_num: uint8)` -> uint32 | Returns information about the specified DMA stream. |
| `get_gpio_states()` -> uint32 | Returns the logic states of all GPIOs. Bit i represents the state of GPIOi. |
| `get_drv_fault()` -> uint32 | The DRV8301 gate driver's fault status word, read now (0: no fault). |
| `clear_errors()` | Clear all the errors of this device including all contained submodules. |

Objects: [task_times](#odrv0task_times), [system_stats](#odrv0system_stats), [capture](#odrv0capture), [can](#odrv0can), [config](#odrv0config), [axis0](#odrv0axis0)

### odrv0.task_times

Objects: [sampling](#odrv0task_timessampling), [control_loop_misc](#odrv0task_timescontrol_loop_misc), [control_loop_checks](#odrv0task_timescontrol_loop_checks), [dc_calib_wait](#odrv0task_timesdc_calib_wait), [capture_update](#odrv0task_timescapture_update)

### odrv0.task_times.sampling

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.task_times.control_loop_misc

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.task_times.control_loop_checks

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.task_times.dc_calib_wait

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.task_times.capture_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` (added) | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` (added) | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` (added) | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` (added) | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.system_stats

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `uptime` | uint32 | ms | ro | Time since boot. |
| `min_heap_space` | uint32 | bytes | ro | The smallest free heap seen since boot. |
| `max_stack_usage_axis` | uint32 | bytes | ro | Highest stack use of the axis thread since boot. |
| `max_stack_usage_usb` | uint32 | bytes | ro | Highest stack use of the USB thread since boot. |
| `max_stack_usage_uart` | uint32 | bytes | ro | Highest stack use of the UART thread since boot. |
| `max_stack_usage_can` | uint32 | bytes | ro | Highest stack use of the CAN thread since boot. |
| `max_stack_usage_startup` | uint32 | bytes | ro | Highest stack use of the startup thread. |
| `max_stack_usage_analog` | uint32 | bytes | ro | Highest stack use of the analog-input thread since boot. |
| `stack_size_axis` | uint32 | bytes | ro | Stack size of the axis thread. |
| `stack_size_usb` | uint32 | bytes | ro | Stack size of the USB thread. |
| `stack_size_uart` | uint32 | bytes | ro | Stack size of the UART thread. |
| `stack_size_startup` | uint32 | bytes | ro | Stack size of the startup thread. |
| `stack_size_can` | uint32 | bytes | ro | Stack size of the CAN thread: 4 KB, as USB's, because CAN endpoint access runs the same handlers. |
| `stack_size_analog` | uint32 | bytes | ro | Stack size of the analog-input thread. |
| `prio_axis` | int32 |  | ro | FreeRTOS priority of the axis thread. |
| `prio_usb` | int32 |  | ro | FreeRTOS priority of the USB thread. |
| `prio_uart` | int32 |  | ro | FreeRTOS priority of the UART thread. |
| `prio_startup` | int32 |  | ro | FreeRTOS priority of the startup thread. |
| `prio_can` | int32 |  | ro | FreeRTOS priority of the CAN thread. |
| `prio_analog` | int32 |  | ro | FreeRTOS priority of the analog-input thread. |

Objects: [usb](#odrv0system_statsusb), [i2c](#odrv0system_statsi2c)

### odrv0.system_stats.usb

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `rx_cnt` | uint32 |  | ro | USB packets received since boot. |
| `tx_cnt` | uint32 |  | ro | USB packets sent since boot. |
| `tx_overrun_cnt` | uint32 |  | ro | USB packets dropped because the transmit buffer was full. |

### odrv0.system_stats.i2c

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `addr` | uint8 |  | ro | The board's I2C address (I2C shares its pins with CAN; see `config.enable_i2c_a`). |
| `addr_match_cnt` | uint32 |  | ro | I2C transactions addressed to this board since boot. |
| `rx_cnt` | uint32 |  | ro | I2C transactions received since boot. |
| `error_cnt` | uint32 |  | ro | I2C errors since boot. |

### odrv0.capture

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `decimation` (added) | uint32 |  | rw | Record one sample every `decimation` control periods. |
| `trigger_mode` (added) | [Capture.CaptureTrigger](#capturecapturetrigger) |  | rw | What starts the post-trigger recording: `IMMEDIATE`, a `RISING` or `FALLING` level crossing, or `MANUAL` (`trigger()`). |
| `trigger_channel` (added) | uint32 |  | rw | Channel (in add_channel order) watched by the RISING and FALLING triggers. |
| `trigger_level` (added) | float32 |  | rw | Level for the RISING and FALLING triggers, in the channel's own unit. |
| `post_trigger` (added) | uint32 |  | rw | Samples recorded after the trigger sample; start() clamps it to capacity - 1. |
| `state` (added) | [Capture.CaptureState](#capturecapturestate) |  | ro | `IDLE`, `ARMED`, `TRIGGERED` or `DONE`. |
| `n_channels` (added) | uint32 |  | ro | Channels added with `add_channel`. |
| `capacity` (added) | uint32 |  | ro | Frames the buffer holds: 8192 / n_channels. |
| `n_samples` (added) | uint32 |  | ro | Frames recorded (at most capacity). |
| `trigger_index` (added) | uint32 |  | ro | Frame of the trigger sample, in readout order. Valid when DONE. |
| `readout_endpoint` (added) | uint16 |  | ro | Endpoint ID of the recorded buffer (0x7F00), read with a buffer read over USB or CAN endpoint access. |

| Function | Description |
|---|---|
| `add_channel(endpoint_id: uint32)` -> bool (added) | Append a property (float32, bool, uint8, uint16, uint32 or int32) by endpoint ID. Fails while recording, for an unknown ID, a function or another type, and beyond 8 channels. Discards the recorded data. |
| `clear_channels()` (added) | Remove all channels, stop any recording and discard the data. |
| `start()` -> bool (added) | Discard the data and record until the trigger plus post_trigger samples. Fails with no channels, an unknown trigger_mode, or a level trigger on a missing channel. |
| `trigger()` (added) | Trigger the armed capture now (any trigger_mode). |

### odrv0.can

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Can.Error](#canerror) |  | rw | CAN errors (bits in `Can.Error`). |

Objects: [config](#odrv0canconfig)

### odrv0.can.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `baud_rate` | uint32 | bit/s | rw | CAN bit rate: a rate that divides 2 MHz evenly, such as 1000000, 500000 or 250000 (the default). Other values are ignored. |
| `protocol` | [Can.Protocol](#canprotocol) |  | rw | Protocols on the bus: 1 (`SIMPLE`, CANSimple; the default). 0 turns CAN messaging off. Makerbase's v0.5.1 numbered CANSimple 0, so a config carried over from it needs this set to 1. |

### odrv0.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `enable_uart_a` | bool |  | rw | Enables/disables UART_A.<br>The GPIOs must be in `GPIO_MODE_UART_A` as well (GPIO1 TX and GPIO2 RX, the default). [Hardware](hardware.md#gpios) lists the pins. Takes effect after a save and reboot. |
| `enable_uart_b` | bool |  | rw | Enables/disables UART_B.<br>The GPIOs must be in `GPIO_MODE_UART_B` as well (GPIO3 TX and GPIO4 RX). [Hardware](hardware.md#gpios) lists the pins. Takes effect after a save and reboot. |
| `enable_uart_c` | bool |  | rw | Not supported on ODrive v3.x. |
| `uart_a_baudrate` | uint32 | baud/s | rw | Defines the baudrate used on the UART interface.<br>The UART clock (42 MHz) gives some rates a small error: 9600 and below are exact, 19200 to 57600 are off by 0.02 %, 115200 by 0.11 %, 230400 and 460800 by 0.16 %, 921600 by 0.93 %. The STM32F405 reference manual (RM0090, the USART baud rate tables for f_PCLK = 42 MHz) lists every rate. |
| `uart_b_baudrate` | uint32 | baud/s | rw | Defines the baudrate used on the UART interface.<br>See `uart_a_baudrate` for details. |
| `uart_c_baudrate` | uint32 |  | rw | Not supported on ODrive v3.x. |
| `enable_can_a` | bool |  | rw | Enables CAN. Changing this setting requires a reboot. |
| `enable_i2c_a` | bool |  | rw | Enables I2C. The I2C pins on ODrive v3.x are in conflict with CAN. This setting has no effect if `enable_can_a` is also true. This setting has no effect on ODrive v3.2 or earlier. Changing this setting requires a reboot. |
| `usb_cdc_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw | The protocol on the board's USB virtual COM port. The board has a second, vendor-specific USB interface that always runs Fibre, which the host tools use, so this setting doesn't affect them. |
| `uart0_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw | Protocol on UART_A. |
| `uart1_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw | Protocol on UART_B. |
| `uart2_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw | Protocol on UART_C |
| `max_regen_current` | float32 | Amps | rw | The bus current allowed to flow back to the power supply before the brake resistor starts absorbing current. 0 (the default) for a supply that can't sink current. |
| `brake_resistance` | float32 | ohm | rw | Value of the brake resistor connected to the ODrive.<br>Set lower than the true resistance, the board pushes more than `max_regen_current` back into the power supply while braking. Set higher, it burns more power in the resistor than needed. |
| `enable_brake_resistor` | bool |  | rw | Enable/disable the use of a brake resistor.<br>False (the default) with a resistor connected is harmless. True with no resistor connected leaves regen nowhere to go but the supply. Takes effect after a save and reboot. |
| `dc_bus_undervoltage_trip_level` | float32 | V | rw | Minimum voltage below which the motor stops operating. |
| `dc_bus_overvoltage_trip_level` | float32 | V | rw | Maximum voltage above which the motor stops operating.<br>Every motor disarms above it (`DC_BUS_OVER_VOLTAGE`). The default is 1.07 times the board's voltage variant: 59.92 V on the Mini, next to its 60 V parts. Set it a few volts above the supply voltage. |
| `enable_dc_bus_overvoltage_ramp` | bool |  | rw | Enables the DC bus overvoltage ramp feature.<br>Above `dc_bus_overvoltage_ramp_start`, the brake duty cycle rises linearly with the bus voltage, by 0 % at the start voltage up to 100 % at `dc_bus_overvoltage_ramp_end`, on top of the regen current. It works with every motor disarmed, and needs a positive `brake_resistance`. |
| `dc_bus_overvoltage_ramp_start` | float32 |  | rw | See `enable_dc_bus_overvoltage_ramp`.<br>Set it above the supply voltage; below it, the brake resistor runs continuously. |
| `dc_bus_overvoltage_ramp_end` | float32 |  | rw | See `enable_dc_bus_overvoltage_ramp`.<br>Must be larger than `dc_bus_overvoltage_ramp_start`, otherwise the ramp feature is disabled. |
| `dc_max_positive_current` | float32 | A | rw | Max current the power supply can source. |
| `dc_max_negative_current` | float32 | A | rw | Max current the power supply can sink.<br>Zero or negative. -inf disables the check. Its magnitude must exceed `max_regen_current`. |
| `error_gpio_pin` | uint32 |  | rw | GPIO in `GPIO_MODE_STATUS` that signals an error; 0 (the default) for none. |
| `gpio1_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO1 (changes take effect after reboot) |
| `gpio2_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO2 (changes take effect after reboot) |
| `gpio3_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO3 (changes take effect after reboot) |
| `gpio4_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO4 (changes take effect after reboot) |
| `gpio5_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO5 (changes take effect after reboot) |
| `gpio6_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO6 (changes take effect after reboot) |
| `gpio7_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO7 (changes take effect after reboot) |
| `gpio8_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO8 (changes take effect after reboot) |
| `gpio9_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO9 (changes take effect after reboot) |
| `gpio10_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO10 (changes take effect after reboot) |
| `gpio11_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO11 (changes take effect after reboot) |
| `gpio12_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO12 (changes take effect after reboot) |
| `gpio13_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO13 (changes take effect after reboot) |
| `gpio14_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO14 (changes take effect after reboot) |
| `gpio15_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO15 (changes take effect after reboot) |
| `gpio16_mode` | [GpioMode](#gpiomode) |  | rw | Mode of GPIO16 (changes take effect after reboot) |

Objects: [gpio3_analog_mapping](#odrv0configgpio3_analog_mapping), [gpio4_analog_mapping](#odrv0configgpio4_analog_mapping), [gpio1_pwm_mapping](#odrv0configgpio1_pwm_mapping), [gpio2_pwm_mapping](#odrv0configgpio2_pwm_mapping), [gpio3_pwm_mapping](#odrv0configgpio3_pwm_mapping), [gpio4_pwm_mapping](#odrv0configgpio4_pwm_mapping)

### odrv0.config.gpio3_analog_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw | The property the input drives (for example `axis0.controller.input_pos`). |
| `min` | float32 |  | rw | The property's value at the input's lowest level. |
| `max` | float32 |  | rw | The property's value at the input's highest level. |

### odrv0.config.gpio4_analog_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw | The property the input drives (for example `axis0.controller.input_pos`). |
| `min` | float32 |  | rw | The property's value at the input's lowest level. |
| `max` | float32 |  | rw | The property's value at the input's highest level. |

### odrv0.config.gpio1_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw | The property the input drives (for example `axis0.controller.input_pos`). |
| `min` | float32 |  | rw | The property's value at the input's lowest level. |
| `max` | float32 |  | rw | The property's value at the input's highest level. |

### odrv0.config.gpio2_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw | The property the input drives (for example `axis0.controller.input_pos`). |
| `min` | float32 |  | rw | The property's value at the input's lowest level. |
| `max` | float32 |  | rw | The property's value at the input's highest level. |

### odrv0.config.gpio3_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw | The property the input drives (for example `axis0.controller.input_pos`). |
| `min` | float32 |  | rw | The property's value at the input's lowest level. |
| `max` | float32 |  | rw | The property's value at the input's highest level. |

### odrv0.config.gpio4_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw | The property the input drives (for example `axis0.controller.input_pos`). |
| `min` | float32 |  | rw | The property's value at the input's lowest level. |
| `max` | float32 |  | rw | The property's value at the input's highest level. |

### odrv0.axis0

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Axis.Error](#axiserror) |  | rw | The axis's errors (bits in `Axis.Error`); also sent in the CAN heartbeat. `MOTOR_FAILED`, `ENCODER_FAILED` and `CONTROLLER_FAILED` point to the sub-object's own `error`. |
| `step_dir_active` | bool |  | ro | True while the step/direction input drives `input_pos`. |
| `last_drv_fault` | uint32 |  | ro | The gate driver's fault word, latched when the motor last disarmed with `DRV_FAULT`. |
| `steps` | int64 |  | ro | The current commanded position, in steps, while in `step_dir` mode |
| `current_state` | [Axis.AxisState](#axisaxisstate) |  | ro | The current state of the axis |
| `requested_state` | [Axis.AxisState](#axisaxisstate) |  | rw | The user's commanded axis state<br>This is used to command the axis to change state or perform certain routines. Values input here will be "consumed" and queued by the state machine handler. Thus, reading this value back will usually show `UNDEFINED` (0). |
| `is_homed` | bool |  | rw | Whether or not the axis has been successfully homed. |

| Function | Description |
|---|---|
| `watchdog_feed()` | Feed the watchdog to prevent watchdog timeouts. |

Objects: [config](#odrv0axis0config), [motor](#odrv0axis0motor), [controller](#odrv0axis0controller), [encoder](#odrv0axis0encoder), [acim_estimator](#odrv0axis0acim_estimator), [sensorless_estimator](#odrv0axis0sensorless_estimator), [trap_traj](#odrv0axis0trap_traj), [min_endstop](#odrv0axis0min_endstop), [max_endstop](#odrv0axis0max_endstop), [mechanical_brake](#odrv0axis0mechanical_brake), [task_times](#odrv0axis0task_times)

### odrv0.axis0.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `startup_motor_calibration` | bool |  | rw | Run motor calibration at startup, skip otherwise |
| `startup_encoder_index_search` | bool |  | rw | Run encoder index search after startup, skip otherwise this only has an effect if encoder.config.use_index is also true |
| `startup_encoder_offset_calibration` | bool |  | rw | Run encoder offset calibration after startup, skip otherwise |
| `startup_closed_loop_control` | bool |  | rw | Enable closed loop control after calibration/startup |
| `startup_homing` | bool |  | rw | Enable homing after calibration/startup |
| `enable_step_dir` | bool |  | rw | Enable step/dir input after calibration. Make sure to set the corresponding GPIO's mode to `GPIO_MODE_DIGITAL`. |
| `step_dir_always_on` | bool |  | rw | Keep step/dir enabled while the motor is disabled. This is ignored if enable_step_dir is false. This setting only takes effect on a state transition into idle or out of closed loop control. |
| `enable_sensorless_mode` | bool |  | rw | Run closed loop from the sensorless estimator instead of the encoder (untested on the Mini). |
| `watchdog_timeout` | float32 | s | rw | The watchdog expires when nothing feeds it for this long. USB `watchdog_feed()` and every CAN frame addressed to the board feed it. |
| `enable_watchdog` | bool |  | rw | Arms the watchdog (default false). `watchdog_action` sets what an expiry does. |
| `watchdog_action` (added) | [Axis.WatchdogAction](#axiswatchdogaction) |  | rw | What the axis does in closed loop when the watchdog expires. Default: `DECEL_HOLD`. |
| `watchdog_decel` (added) | float32 | turn/s^2 | rw | Deceleration for `watchdog_action` = `DECEL_HOLD`. Default 10. |
| `watchdog_torque_lim` (added) | float32 | N·m | rw | Torque cap while decelerating and holding after a watchdog timeout. Infinity (the default) keeps the normal limit. |
| `step_gpio_pin` | uint16 |  | rw | GPIO of the step input; it must be in a `GPIO_MODE_DIGITAL` mode. |
| `dir_gpio_pin` | uint16 |  | rw | GPIO of the direction input; it must be in a `GPIO_MODE_DIGITAL` mode. |

Objects: [calibration_lockin](#odrv0axis0configcalibration_lockin), [sensorless_ramp](#odrv0axis0configsensorless_ramp), [general_lockin](#odrv0axis0configgeneral_lockin), [can](#odrv0axis0configcan)

### odrv0.axis0.config.calibration_lockin

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `current` | float32 | A | rw | Current of the open-loop vector that turns the rotor during encoder direction search. |
| `ramp_time` | float32 | s | rw | Time to ramp the current up. |
| `ramp_distance` | float32 | rad | rw | Electrical angle covered while the current ramps up. |
| `accel` | float32 | rad/s^2 | rw | Electrical acceleration after the ramp. |
| `vel` | float32 | rad/s | rw | Final electrical velocity. |

### odrv0.axis0.config.sensorless_ramp

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `current` | float32 | A | rw | Current of the open-loop vector that turns the rotor. |
| `ramp_time` | float32 | s | rw | Time to ramp the current up at standstill. |
| `ramp_distance` | float32 | rad | rw | Electrical angle covered while the current ramps up. |
| `accel` | float32 | rad/s^2 | rw | Electrical acceleration after the ramp. |
| `vel` | float32 | rad/s | rw | Electrical velocity at which the lock-in stops accelerating. |
| `finish_distance` | float32 | rad | rw | Electrical angle after which the lock-in ends, when `finish_on_distance` is set. |
| `finish_on_vel` | bool |  | rw | End the lock-in on reaching `vel`. |
| `finish_on_distance` | bool |  | rw | End the lock-in after `finish_distance`. |
| `finish_on_enc_idx` | bool |  | rw | End the lock-in when the encoder index is found. |

### odrv0.axis0.config.general_lockin

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `current` | float32 | A | rw | Current of the open-loop vector that turns the rotor. |
| `ramp_time` | float32 | s | rw | Time to ramp the current up at standstill. |
| `ramp_distance` | float32 | rad | rw | Electrical angle covered while the current ramps up. |
| `accel` | float32 | rad/s^2 | rw | Electrical acceleration after the ramp. |
| `vel` | float32 | rad/s | rw | Electrical velocity at which the lock-in stops accelerating. |
| `finish_distance` | float32 | rad | rw | Electrical angle after which the lock-in ends, when `finish_on_distance` is set. |
| `finish_on_vel` | bool |  | rw | End the lock-in on reaching `vel`. |
| `finish_on_distance` | bool |  | rw | End the lock-in after `finish_distance`. |
| `finish_on_enc_idx` | bool |  | rw | End the lock-in when the encoder index is found. |

### odrv0.axis0.config.can

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `node_id` | uint32 |  | rw | The board's CAN node ID: 0 to 63 with standard IDs, different on every board on a bus. Default 0. |
| `is_extended` | bool |  | rw | Use 29-bit extended IDs instead of 11-bit standard IDs (default false). |
| `heartbeat_rate_ms` | uint32 | ms | rw | Period of the cyclic Heartbeat message (0x001); 0 turns it off. Default 100. |
| `encoder_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Encoder Estimates message (0x009); 0 turns it off. Default 10. |
| `motor_error_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Motor Error message (0x003); 0 (the default) turns it off. |
| `encoder_error_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Encoder Error message (0x004); 0 (the default) turns it off. |
| `controller_error_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Controller Error message (0x01D); 0 (the default) turns it off. |
| `sensorless_error_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Sensorless Error message (0x005); 0 (the default) turns it off. |
| `encoder_count_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Encoder Count message (0x00A); 0 (the default) turns it off. |
| `iq_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Iq message (0x014); 0 (the default) turns it off. |
| `sensorless_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Sensorless Estimates message (0x015); 0 (the default) turns it off. |
| `bus_vi_rate_ms` | uint32 | ms | rw | Period of the cyclic Get Bus Voltage and Current message (0x017); 0 (the default) turns it off. |
| `impedance_pos_range` (added) | float32 | turn | rw | Full scale (+/-) of the position fields of the CAN impedance command and reply (0x01E, 16 bit). Positions beyond it saturate. Default 16. |
| `impedance_vel_range` (added) | float32 | turn/s | rw | Full scale (+/-) of the velocity fields of the impedance command and reply (12 bit). Default 32. |
| `impedance_kp_max` (added) | float32 | N·m/turn | rw | Full scale of the impedance command's kp field (12 bit, 0 to max). Default 200. |
| `impedance_kd_max` (added) | float32 | N·m/(turn/s) | rw | Full scale of the impedance command's kd field (12 bit, 0 to max). Default 2. |
| `impedance_torque_range` (added) | float32 | N·m | rw | Full scale (+/-) of the torque fields of the impedance command and reply (12 bit). Default 4. |

### odrv0.axis0.motor

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `last_error_time` | float32 | s | rw | Time since boot of the motor's last error. |
| `error` | [Motor.Error](#motorerror) |  | rw | The motor's errors (bits in `Motor.Error`, 64 bits wide: CAN endpoint access can't read it; use Get Motor Error, 0x003). |
| `is_armed` | bool |  | ro | True while the gate driver switches the motor's phases. |
| `is_calibrated` | bool |  | ro | True once phase resistance and inductance are known (measured |
| `current_meas_phA` | float32 | A | ro | Phase A current; the Mini has no phase A shunt, so this is -(B + C). |
| `current_meas_phB` | float32 | A | ro | Phase B current |
| `current_meas_phC` | float32 | A | ro | Phase C current |
| `DC_calib_phA` | float32 | A | rw | Offset of the phase A current measurement |
| `DC_calib_phB` | float32 | A | rw | Offset of the phase B current measurement. |
| `DC_calib_phC` | float32 | A | rw | Offset of the phase C current measurement. |
| `I_bus` | float32 | A | ro | The current in the ODrive DC bus. This is also the current seen by the power supply in most systems. |
| `phase_current_rev_gain` | float32 |  | rw | Inverse gain of the current sense amplifiers, set from `config.requested_current_range`. |
| `effective_current_lim` | float32 | A | ro | This value is the internally-limited value of phase current allowed according to the set current limit and the FET and Motor thermistor limits. |
| `max_allowed_current` | float32 | A | ro | Indicates the maximum current that can be measured by the current sensors in the current hardware configuration. This value depends on `config.requested_current_range`. |
| `max_dc_calib` | float32 | A | ro | Largest current-measurement offset accepted as valid: 10 % of `max_allowed_current`. |
| `n_evt_current_measurement` | uint32 |  | ro | Number of current measurement events since startup (modulo 2^32) |
| `n_evt_pwm_update` | uint32 |  | ro | Number of PWM update events since startup (modulo 2^32) |
| `spike_count` (added) | uint32 |  | ro | Diagnostics: control periods (while armed) in which the measured current vector jumped by more than spike_threshold from the previous period. A one-period glitch counts twice (out and back). |
| `spike_threshold` (added) | float32 | A | rw | Diagnostics (RAM only): jump threshold for `spike_count`. |

| Function | Description |
|---|---|
| `get_spike_n(index: uint32)` -> uint32 (added) | Diagnostics: `n_evt_control_loop` at spike event `index` (0..31, ring buffer; event k is at k % 32). |
| `get_spike_db(index: uint32)` -> float32 (added) | Diagnostics: phase B current change [A] at spike event `index`. |
| `get_spike_dc(index: uint32)` -> float32 (added) | Diagnostics: phase C current change [A] at spike event `index`. |

Objects: [fet_thermistor](#odrv0axis0motorfet_thermistor), [motor_thermistor](#odrv0axis0motormotor_thermistor), [current_control](#odrv0axis0motorcurrent_control), [config](#odrv0axis0motorconfig)

### odrv0.axis0.motor.fet_thermistor

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `temperature` | float32 | °C | ro | Temperature of the power stage, from the onboard FET thermistor. |

Objects: [config](#odrv0axis0motorfet_thermistorconfig)

### odrv0.axis0.motor.fet_thermistor.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `temp_limit_lower` | float32 |  | rw | The lower limit when the controller starts limiting current. |
| `temp_limit_upper` | float32 |  | rw | The upper limit when current limit reaches 0 Amps and an over temperature error is triggered. |
| `enabled` | bool |  | rw | Whether this thermistor is enabled. |

### odrv0.axis0.motor.motor_thermistor

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `temperature` | float32 | °C | ro | Temperature from a motor thermistor on an analog GPIO, when enabled. |

Objects: [config](#odrv0axis0motormotor_thermistorconfig)

### odrv0.axis0.motor.motor_thermistor.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_pin` | uint16 |  | rw | The analog GPIO the thermistor divider connects to; it must be in `GPIO_MODE_ANALOG_IN`. |
| `poly_coefficient_0` | float32 |  | rw | Temperature = c0 x^3 + c1 x^2 + c2 x + c3, where x is the GPIO voltage as a fraction of 3.3 V. This is c0. |
| `poly_coefficient_1` | float32 |  | rw | c1 of the polynomial above. |
| `poly_coefficient_2` | float32 |  | rw | c2 of the polynomial above. |
| `poly_coefficient_3` | float32 |  | rw | c3 of the polynomial above. |
| `temp_limit_lower` | float32 |  | rw | The lower limit when the controller starts limiting current. |
| `temp_limit_upper` | float32 |  | rw | The upper limit when current limit reaches 0 Amps and an over temperature error is triggered. |
| `enabled` | bool |  | rw | Whether this thermistor is enabled. |

### odrv0.axis0.motor.current_control

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `p_gain` | float32 | V/A | ro | Proportional gain of the current loop: `current_control_bandwidth` x phase inductance. |
| `i_gain` | float32 | V/(A·s) | ro | Integral gain of the current loop: `current_control_bandwidth` x phase resistance. |
| `I_measured_report_filter_k` | float32 |  | rw | Filter gain for the reported `Id_measured` and `Iq_measured` (1 = unfiltered). Affects only the reported values. |
| `Id_setpoint` | float32 | A | ro | d-axis current setpoint (non-zero with flux braking or the bus current soft limits). |
| `Iq_setpoint` | float32 | A | ro | q-axis (torque) current setpoint. |
| `Vd_setpoint` | float32 | V | ro | d-axis voltage feed-forward. |
| `Vq_setpoint` | float32 | V | ro | q-axis voltage feed-forward. |
| `phase` | float32 | rad | ro | Electrical angle the current loop commutates at. |
| `phase_vel` | float32 | rad/s | ro | Electrical angular velocity. |
| `Ialpha_measured` | float32 | A | ro | Measured current in the stator's alpha axis. |
| `Ibeta_measured` | float32 | A | ro | Measured current in the stator's beta axis. |
| `Id_measured` | float32 | A | ro | The phase current measured along the "d" axis in the FOC control loop. This should be close to 0 for typical surface permanent magnet motors. |
| `Iq_measured` | float32 | A | ro | The phase current measured along the "q" axis in the FOC control loop. This is the torque-generating current, so motor torque is approx. `torque_constant * Iq_measured` |
| `power` | float32 | W | ro | The electrical power being delivered to the motor |
| `v_current_control_integral_d` | float32 | V | rw | State of the d-axis current loop's integrator. |
| `v_current_control_integral_q` | float32 | V | rw | State of the q-axis current loop's integrator. |
| `final_v_alpha` | float32 | V | ro | Output voltage in the alpha axis |
| `final_v_beta` | float32 | V | ro | Output voltage in the beta axis |

### odrv0.axis0.motor.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `pre_calibrated` | bool |  | rw | Indicates to the ODrive that the parameters `config.phase_resistance` and `config.phase_inductance` are valid at system start. If these are valid and `pre_calibrated` is set to `True`, motor calibration can be skipped. |
| `pole_pairs` | int32 |  | rw | The number of pole pairs in the motor. Note this is equal to 1/2 of the number of magnets (not coils!) in a typical hobby motor. |
| `calibration_current` | float32 |  | rw | The current used to measure resistance during `AXIS_STATE_MOTOR_CALIBRATION`. |
| `resistance_calib_max_voltage` | float32 |  | rw | The maximum voltage allowed during `AXIS_STATE_MOTOR_CALIBRATION`. This should be set to less than `(0.5 * vbus_voltage)`, but high enough to satisfy V=IR during motor calibration, where I is `config.calibration_current` and R is `config.phase_resistance` |
| `phase_inductance` | float32 | henry | rw | Measured by `AXIS_STATE_MOTOR_CALIBRATION`; sets the current loop's gains. |
| `phase_resistance` | float32 | ohm | rw | Measured by `AXIS_STATE_MOTOR_CALIBRATION`; sets the current loop's gains. |
| `torque_constant` | float32 | N·m/A | rw | Torque per amp of q-axis current: 8.27 / KV (0.1074 for a 77 KV DJI 10018). The default, 0.04, makes every torque setting act 2.7 times stronger in amps on a 10018. |
| `motor_type` | [Motor.MotorType](#motormotortype) |  | rw | `HIGH_CURRENT` (the default) for brushless motors driven by current control. |
| `current_lim` | float32 | A | rw | Maximum commanded current allowed |
| `current_lim_margin` | float32 | A | rw | Measured current allowed above `current_lim`. Above `current_lim + current_lim_margin`, the motor disarms with `CURRENT_LIMIT_VIOLATION`. |
| `torque_lim` | float32 | N·m | rw | Maximum commanded torque allowed in the torque loop. |
| `inverter_temp_limit_lower` | float32 | °C | rw | Not implemented. |
| `inverter_temp_limit_upper` | float32 | °C | rw | Not implemented. |
| `requested_current_range` | float32 | A | rw | The minimum phase current range expected to be measured. This is used to set the current shunt amplifier gains. Set it above `current_lim + current_lim_margin`, but as low as possible for resolution. At 20 A the measurement saturates at about 33.8 A. Takes effect after a save and reboot. |
| `current_control_bandwidth` | float32 | rad/s | rw | Sets the PI gains of the Q and D axis FOC control according to `phase_resistance` and `phase_inductance` to create a critically-damped controller with a -3dB bandwidth at this frequency. |
| `acim_gain_min_flux` | float32 |  | rw | AC induction motors only (untested on the Mini). |
| `acim_autoflux_min_Id` | float32 | A | rw | AC induction motors only. |
| `acim_autoflux_enable` | bool |  | rw | AC induction motors only. |
| `acim_autoflux_attack_gain` | float32 |  | rw | AC induction motors only. |
| `acim_autoflux_decay_gain` | float32 |  | rw | AC induction motors only. |
| `R_wL_FF_enable` | bool |  | rw | Enables automatic feedforward of the R*wL term in the current controller. |
| `bEMF_FF_enable` | bool |  | rw | Enables automatic feedforward of the bEMF term in the current controller. |
| `I_bus_hard_min` | float32 | A | rw | If the controller fails to keep this motor's DC current (`ODrive.Motor:I_bus`) above this value the motor gets disarmed immediately. Most likely you want a negative value here. Set to -inf to disable. Take noise into account when choosing a value. |
| `I_bus_hard_max` | float32 | A | rw | If the controller fails to keep this motor's DC current (`ODrive.Motor:I_bus`) below this value the motor gets disarmed immediately. Usually this is set in conjunction with `I_bus_hard_min`. Set to inf to disable. Take noise into account when choosing a value. |
| `I_bus_soft_min` (added) | float32 | A | rw | Lowest bus current (most regen) the motor aims for. Each control period the torque current is clamped so that the predicted bus current, 1.5 * (R * (Id^2 + Iq^2) + back-EMF * Iq) / vbus, stays at or above this value. Values above 0 count as 0. Braking at speed is limited to what copper losses (including flux braking) and this regen allowance absorb. -inf (default) disables it. |
| `I_bus_soft_max` (added) | float32 | A | rw | Highest bus current the motor aims for, by the same prediction as `I_bus_soft_min`; caps this board's draw from a shared supply. Values below 0 count as 0. inf (default) disables it. |
| `flux_brake_start_voltage` (added) | float32 | V | rw | Flux braking: above this bus voltage the motor adds d-axis current Id = -flux_brake_gain * (vbus - start), up to the current limit, to burn bus energy in the windings (1.5 * R * Id^2). Set it a little above the supply voltage and below `dc_bus_overvoltage_trip_level`. inf (default) disables it. |
| `flux_brake_gain` (added) | float32 | A/V | rw | Flux-braking d-axis current per volt above `flux_brake_start_voltage`. |
| `I_leak_max` | float32 | A | rw | In almost all scenarios, the currents on phase A, B and C should add up to zero. A small amount of measurement noise is expected. However if the sum of A, B, C currents exceeds this configuration value, the motor gets disarmed immediately.<br>This check needs three current sensors; the Mini has two, so it has no effect there. |
| `dc_calib_tau` | float32 | s | rw | Time constant of the filter that tracks the current-measurement offsets. |

### odrv0.axis0.controller

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Controller.Error](#controllererror) |  | rw | The controller's errors (bits in `Controller.Error`). |
| `last_error_time` | float32 | s | rw | Time since boot of the controller's last error. |
| `input_pos` | float32 | turn | rw | The commanded position, in `CONTROL_MODE_POSITION_CONTROL` and `CONTROL_MODE_IMPEDANCE_CONTROL`. Writing it also updates the step count. In `INPUT_MODE_TUNING`, this acts as a DC offset for the position sine wave. |
| `input_vel` | float32 | turn/s | rw | In `CONTROL_MODE_VELOCITY_CONTROL`, sets the desired velocity of the axis. In `CONTROL_MODE_POSITION_CONTROL`, sets the feed-forward velocity of the velocity controller In `INPUT_MODE_TUNING`, this acts as a DC offset for the velocity sine wave. |
| `input_torque` | float32 | N·m | rw | In `CONTROL_MODE_TORQUE_CONTROL`, sets the desired output torque of the axis. In `CONTROL_MODE_VELOCITY_CONTROL`, `CONTROL_MODE_POSITION_CONTROL` and `CONTROL_MODE_IMPEDANCE_CONTROL`, sets the feed-forward torque of the torque controller, in every input mode: `INPUT_MODE_VEL_RAMP`, `INPUT_MODE_POS_FILTER` and `INPUT_MODE_TRAP_TRAJ` add it to their `config.inertia` term. In `INPUT_MODE_TUNING`, this acts as a DC offset for the torque sine wave. |
| `input_kp` (added) | float32 | N·m/turn | rw | Stiffness in `CONTROL_MODE_IMPEDANCE_CONTROL`. RAM only; also set by the CAN impedance command. |
| `input_kd` (added) | float32 | N·m/(turn/s) | rw | Damping in `CONTROL_MODE_IMPEDANCE_CONTROL`. RAM only; also set by the CAN impedance command. |
| `pos_setpoint` | float32 | turn | ro | The position reference actually being used by the position controller. This is the same as `input_pos` in `INPUT_MODE_PASSTHROUGH`, but may vary according to `InputMode`. |
| `vel_setpoint` | float32 | turn/s | ro | The velocity reference actually being used by the velocity controller. This is the same as `input_vel` in `INPUT_MODE_PASSTHROUGH`, but may vary according to `InputMode`. |
| `torque_setpoint` | float32 | N·m | ro | The torque reference actually being used by the torque controller. This is the same as `input_torque` in `INPUT_MODE_PASSTHROUGH`, but may vary according to `InputMode`. |
| `trajectory_done` | bool |  | ro | Indicates the last commanded Trapezoidal Trajectory movement is complete. |
| `timeout_active` (added) | bool |  | ro | The axis watchdog expired with `axis.config.watchdog_action = DECEL_HOLD`. The controller decelerates to a stop at `axis.config.watchdog_decel`, holds that position and ignores new inputs. Ends on `clear_errors()` (feed the watchdog first) or on a new entry into closed loop; the inputs are then set to the hold position. |
| `vel_integrator_torque` | float32 | N·m | rw | The accumulated value of the velocity loop integrator |
| `anticogging_valid` | bool |  | rw | True once an anticogging map is recorded or loaded (untested on the Mini). |
| `autotuning_phase` | float32 | rad | rw | The current phase angle of the `INPUT_MODE_TUNING` sine wave generator |
| `mechanical_power` | float32 | Watt | ro | Mechanical power estimate. Torque * velocity |
| `electrical_power` | float32 | Watt | ro | Electrical power estimate. Vdq·Idq |

| Function | Description |
|---|---|
| `move_incremental(displacement: float32, from_input_pos: bool)` | Moves the axes' goal point by a specified increment. |
| `start_anticogging_calibration()` | Starts recording the anticogging map (ODrive's procedure, untested on the Mini). |
| `remove_anticogging_bias()` -> float32 | Subtracts the map's mean from every entry and returns the mean. |
| `get_anticogging_value(index: uint32)` -> float32 | One entry of the anticogging map. |

Objects: [config](#odrv0axis0controllerconfig), [autotuning](#odrv0axis0controllerautotuning)

### odrv0.axis0.controller.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gain_scheduling_width` | float32 | turn | rw | Position error below which gain scheduling scales the gains down (`enable_gain_scheduling`). |
| `enable_vel_limit` | bool |  | rw | Clamp the velocity setpoint to `vel_limit` (default true). |
| `enable_torque_mode_vel_limit` | bool |  | rw | Enable velocity limit in torque control mode (requires a valid velocity estimator). |
| `enable_gain_scheduling` | bool |  | rw | Enable the experimental "gain scheduling" module, which reduces the `pos_gain`, `vel_gain`, and `vel_integrator_gain` according to the position error. Also known as "anti-hunt" |
| `enable_overspeed_error` | bool |  | rw | Enables the velocity controller's overspeed error |
| `control_mode` | [Controller.ControlMode](#controllercontrolmode) |  | rw | Which loops run: torque, velocity, position (the default) or impedance control. [Control](control.md) describes each. |
| `input_mode` | [Controller.InputMode](#controllerinputmode) |  | rw | How `input_pos`, `input_vel` and `input_torque` become setpoints. Default: `PASSTHROUGH`. |
| `pos_gain` | float32 | (turn/s) / turn | rw | units = (turn/s) / turn |
| `vel_gain` | float32 | N·m / (turn/s) | rw | units = N·m / (turn/s) |
| `vel_integrator_gain` | float32 | N·m / (turn/s * s) | rw | units = N·m / (turn/s * s) |
| `vel_integrator_limit` | float32 | N·m | rw | Limit the integrator output (independent of proportional gain output). Set to infinity to disable. Units = N·m |
| `vel_limit` | float32 | turn/s | rw | Infinity to disable. |
| `vel_limit_tolerance` | float32 |  | rw | Ratio to `vel_limit`. Infinity to disable. |
| `vel_ramp_rate` | float32 | turn/s^2 | rw | Rate at which `INPUT_MODE_VEL_RAMP` moves the velocity setpoint toward `input_vel`. |
| `torque_ramp_rate` | float32 | N·m / sec | rw | Rate at which `INPUT_MODE_TORQUE_RAMP` moves the torque setpoint toward `input_torque`. |
| `circular_setpoints` | bool |  | rw | Keep the position setpoint within [0, `circular_setpoint_range`) and control against `encoder.pos_circular`, for continuous rotation. Step/direction input needs it. |
| `circular_setpoint_range` | float32 |  | rw | circular range in [turns] for position setpoints when circular_setpoints is True |
| `steps_per_circular_range` | int32 |  | rw | Number of steps within the circular setpoint range. Set this and the circular setpoint range to powers of 2 for the best results. |
| `homing_speed` | float32 | turn/s | rw | The speed at which the axis moves towards the `min_endstop` during `AXIS_STATE_HOMING` |
| `inertia` | float32 | N·m/(turn/s^2) | rw | Torque feed-forward per unit of planned acceleration in `VEL_RAMP`, `POS_FILTER` and `TRAP_TRAJ`; `input_torque` adds to it. |
| `input_filter_bandwidth` | float32 | rad/s | rw | The desired bandwidth for `INPUT_MODE_POS_FILTER`.<br>Sets the position filter's P and I gains to emulate a critically-damped 2nd order mass-spring-damper motion. |
| `mechanical_power_bandwidth` | float32 | rad/s | rw | Bandwidth for mechanical power estimate. Used for spinout detection |
| `electrical_power_bandwidth` | float32 | rad/s | rw | Bandwidth for electrical power estimate. Used for spinout detection. Dot product of Vdq and Idq |
| `spinout_mechanical_power_threshold` | float32 | Watt | rw | Mechanical power threshold for spinout detection. This should be a negative value |
| `spinout_electrical_power_threshold` | float32 | Watt | rw | Electrical power threshold for spinout detection. This should be a positive value |
| `pos_min` (added) | float32 | turn | rw | Soft limit. Trap-trajectory targets and the position setpoint are clamped to [`pos_min`, `pos_max`]. -inf (the default) disables it. |
| `pos_max` (added) | float32 | turn | rw | Soft limit, see `pos_min`. inf (the default) disables it. |
| `pos_limit_margin` (added) | float32 | turn | rw | `POS_LIMIT_VIOLATION` when the position estimate is beyond a limit by more than this. Default 0.1. |
| `max_pos_error` (added) | float32 | turn | rw | `POS_FOLLOWING_ERROR` threshold. inf (the default) disables it. |
| `max_vel_error` (added) | float32 | turn/s | rw | `VEL_FOLLOWING_ERROR` threshold. inf (the default) disables it. |

Objects: [anticogging](#odrv0axis0controllerconfiganticogging)

### odrv0.axis0.controller.config.anticogging

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `index` | uint32 |  | ro | Map entry the anticogging calibration is at. |
| `pre_calibrated` | bool |  | rw | Keep the anticogging map across reboots (saved with the config). |
| `calib_anticogging` | bool |  | ro | True while the anticogging calibration runs. |
| `calib_pos_threshold` | float32 |  | rw | Position error under which the calibration moves to the next map entry. |
| `calib_vel_threshold` | float32 |  | rw | Velocity under which the calibration moves to the next map entry. |
| `cogging_ratio` | float32 |  | ro | Scale between the encoder's counts and the map's entries. |
| `anticogging_enabled` | bool |  | rw | Add the anticogging map's torque in closed loop (untested on the Mini). |

### odrv0.axis0.controller.autotuning

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `frequency` | float32 | Hz | rw | Frequency of the `INPUT_MODE_TUNING` sine wave. |
| `pos_amplitude` | float32 | turns | rw | Amplitude of the position sine. |
| `vel_amplitude` | float32 | turns/sec | rw | Amplitude of the velocity sine. |
| `torque_amplitude` | float32 | N·m | rw | Amplitude of the torque sine. |

### odrv0.axis0.encoder

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Encoder.Error](#encodererror) |  | rw | The encoder's errors (bits in `Encoder.Error`). |
| `is_ready` | bool |  | ro | True once the encoder's offset is known: after offset calibration, or at boot for a `pre_calibrated` absolute encoder on its first valid read. |
| `index_found` | bool |  | ro | True once the index search found the index pulse. |
| `shadow_count` | int32 | counts | ro | Raw linear count from the encoder. |
| `count_in_cpr` | int32 | counts | ro | Raw circular count from the encoder on [0, cpr) |
| `interpolation` | float32 |  | ro | Fraction of a count interpolated between encoder edges (`config.enable_phase_interpolation`). |
| `phase` | float32 | rad | ro | Electrical angle used for commutation. |
| `pos_estimate` | float32 | turns | ro | Linear position estimate of the encoder, in turns. Also known as "multi-turn" position. |
| `pos_estimate_counts` | float32 | counts | ro | Linear position estimate of the encoder, in counts. Equal to `pos_estimate * config.cpr` |
| `pos_circular` | float32 | turns | ro | Circular position estimate of the encoder, as a decimal from [0, 1). Also known as "single-turn" position. |
| `pos_cpr_counts` | float32 | counts | ro | Circular position estimate of the encoder, on the space [0, cpr). |
| `delta_pos_cpr_counts` | float32 | counts | ro | Circular position delta of the encoder in the most recent loop. Primarily for debug purposes, it indicates much the encoder changed since the last time it was checked. |
| `hall_state` | uint8 |  | ro | The three hall inputs as bits (hall encoder mode). |
| `vel_estimate` | float32 | turn/s | ro | Estimate of the linear velocity of an axis in turn/s |
| `vel_estimate_counts` | float32 | counts/sec | ro | Estimate of the linear velocity of an axis, in counts/s. |
| `calib_scan_response` | float32 | counts | ro | Encoder movement measured during the last offset calibration scan. |
| `pos_abs` | int32 |  | rw | The last (valid) position from an absolute encoder, if used. |
| `spi_error_rate` | float32 |  | ro | Filtered fraction of control periods without a valid absolute-encoder sample; above 0.05 raises `ABS_SPI_COM_FAIL`. |
| `spi_frame_count` (added) | uint32 |  | ro | Absolute-encoder SPI frames received. |
| `spi_error_flag_count` (added) | uint32 |  | ro | AMS frames with the error flag (bit 14) set. |
| `spi_warning_flag_count` (added) | uint32 |  | ro | AMS frames with bit 15 set (AS5047U warning flag; AS5047P parity). |
| `spi_jump_count` (added) | uint32 |  | ro | Samples dropped because they jumped further than `config.abs_spi_max_jump`. |
| `spi_last_frame` (added) | uint16 |  | ro | Last raw AMS SPI frame. |
| `spi_parity_error_count` (added) | uint32 |  | ro | AMS frames with odd parity (meaningful for an AS5047P). |
| `pos_abs_raw` (added) | int32 |  | ro | Last good raw absolute position, before the correction table. |
| `correction_rms` (added) | float32 | counts | ro | RMS encoder error measured by the last correction calibration. |
| `correction_peak` (added) | float32 | counts | ro | Largest \|error\| measured by the last correction calibration. |
| `correction_bins` (added) | uint32 |  | ro | Bins the last correction calibration covered in both directions (256 = all). |

| Function | Description |
|---|---|
| `set_linear_count(count: int32)` | Set the current linear position of the axis, in counts |
| `get_correction(index: uint32)` -> float32 (added) | Correction table entry `index` (0 to 255), in counts. |
| `set_correction(index: uint32, val: float32)` (added) | Sets correction table entry `index` (0 to 255), in counts. RAM only until saved. |

Objects: [config](#odrv0axis0encoderconfig)

### odrv0.axis0.encoder.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `mode` | [Encoder.Mode](#encodermode) |  | rw | Encoder type. The onboard AS5047 is `SPI_ABS_AMS` (257); the default is `INCREMENTAL`. |
| `use_index` | bool |  | rw | Set this to `True` when using an encoder with an index pin to allow pre-calibration of the encoder and encoder index search. |
| `index_offset` | float32 |  | rw | When the index is found, the linear position of the axis will be set to this value if `use_index_offset` is set to `True`. |
| `use_index_offset` | bool |  | rw | Set this to `True` to have the axis set the linear position of the axis to `index_offset` when the index is found during encoder index search |
| `find_idx_on_lockin_only` | bool |  | rw | Look for the index pulse only during lock-in spin. |
| `abs_spi_cs_gpio_pin` | uint16 |  | rw | Chip-select GPIO of an SPI absolute encoder: 7 for the Mini's onboard AS5047, 6 for one on J4. The GPIO must be in `GPIO_MODE_DIGITAL`. |
| `abs_spi_max_jump` (added) | uint16 | counts | rw | Drop an absolute-encoder sample further than this from the last good one (default 1024, 1/16 turn of the AS5047; 0 turns it off). Active after 16 good samples; a fourth sample in a row at the new position is accepted. |
| `correction_enabled` (added) | bool |  | rw | Add the correction table (`get_correction`, `set_correction`) to the raw absolute position. Default false; the correction calibration sets it. |
| `correction_scan_turns` (added) | float32 | turns | rw | Mechanical turns each way for `AXIS_STATE_ENCODER_CORRECTION_CALIBRATION`. Default 1. |
| `correction_max_harmonic` (added) | uint8 |  | rw | The correction calibration keeps harmonics 1 to N per turn of the measured error (default 12; 0 keeps the raw bins). Higher orders are cogging, not encoder error. |
| `abs_spi_check_parity` (added) | bool |  | rw | Drop AMS frames with odd parity (default false). For an AS5047P (bit 15 = even parity); an AS5047U has none. |
| `abs_spi_reject_error_flag` (added) | bool |  | rw | Drop AMS frames with the error flag set (default false). The flag stays set until the chip's ERRFL register is read. |
| `cpr` | int32 |  | rw | Counts per Revolution of the encoder. This is 4x the Pulses per Revolution. |
| `phase_offset` | int32 | counts | rw | Encoder count at the rotor's electrical zero, measured by offset calibration. |
| `phase_offset_float` | float32 | counts | rw | Fractional part of `phase_offset`. |
| `direction` | int32 |  | rw | +1 or -1: whether the encoder counts up with the electrical angle. Measured by offset calibration. |
| `pre_calibrated` | bool |  | rw | Keep the offset calibration across reboots. With an absolute encoder, the board is ready at boot without a calibration sweep. |
| `enable_phase_interpolation` | bool |  | rw | Interpolate the commutation angle between encoder counts. |
| `bandwidth` | float32 | rad/s | rw | Bandwidth of the PLL that estimates position and velocity. Commutation uses the raw count, so it affects only the position and velocity loops. Default 1000. |
| `calib_range` | float32 | turn | rw | Offset calibration fails with `CPR_POLEPAIRS_MISMATCH` when the measured movement differs from the expected by more than this fraction. Default 0.02. |
| `calib_scan_distance` | float32 | rad (electrical) | rw | The distance the motor is turned during encoder offset calibration. This is in the electrical frame, so if you want a 7pp motor to turn 1 mechanical revolution, you would put `(7 * 2*pi)` |
| `calib_scan_omega` | float32 | rad/s (electrical) | rw | The speed the motor turns during encoder offset calibration. This is in the electrical frame, so a 7pp motor rotating 1 mechanical revolution in 2 sec would be set to `(7 * 2*pi) / 2` |
| `ignore_illegal_hall_state` | bool |  | rw | Ignore the error "Illegal Hall State" |
| `hall_polarity` | uint8 |  | rw | Hall input polarity bits |
| `hall_polarity_calibrated` | bool |  | rw | True once the hall polarity calibration ran. |
| `sincos_gpio_pin_sin` | uint16 |  | rw | Analog sine signal of a sin/cos encoder. The corresponding GPIO must be in `GPIO_MODE_ANALOG_IN`. |
| `sincos_gpio_pin_cos` | uint16 |  | rw | Analog cosine signal of a sin/cos encoder. The corresponding GPIO must be in `GPIO_MODE_ANALOG_IN`. |

### odrv0.axis0.acim_estimator

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `rotor_flux` | float32 | A | ro | estimated magnitude of the rotor flux |
| `slip_vel` | float32 | rad/s | ro | Estimated slip between physical and electrical angular velocity. |
| `phase_offset` | float32 | rad | ro | Estimated offset between physical and electrical angular position. |
| `stator_phase_vel` | float32 | rad/s | ro | Calculated setpoint for the electrical velocity. |
| `stator_phase` | float32 | rad | ro | Calculated setpoint for the electrical phase. |

Objects: [config](#odrv0axis0acim_estimatorconfig)

### odrv0.axis0.acim_estimator.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `slip_velocity` | float32 |  | rw | AC induction motors only (untested on the Mini). |

### odrv0.axis0.sensorless_estimator

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [SensorlessEstimator.Error](#sensorlessestimatorerror) |  | rw | The sensorless estimator's errors (bits in `SensorlessEstimator.Error`). |
| `phase` | float32 | rad | ro | Estimated electrical angle. |
| `pll_pos` | float32 | rad | ro | Electrical angle tracked by the estimator's PLL. |
| `phase_vel` | float32 | rad/s | ro | Estimated electrical angular velocity. |
| `vel_estimate` | float32 | turn/s | ro | Estimated mechanical velocity. |

Objects: [config](#odrv0axis0sensorless_estimatorconfig)

### odrv0.axis0.sensorless_estimator.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `observer_gain` | float32 |  | rw | Gain of the flux observer (sensorless mode |
| `pll_bandwidth` | float32 | rad/s | rw | Bandwidth of the estimator's PLL. |
| `pm_flux_linkage` | float32 | Wb | rw | The motor's flux linkage: 5.51328895422 / (pole pairs x KV). |

### odrv0.axis0.trap_traj

Objects: [config](#odrv0axis0trap_trajconfig)

### odrv0.axis0.trap_traj.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `vel_limit` | float32 | turn/s | rw | Cruise speed of a trapezoidal move. Keep `controller.config.vel_limit` at least 10 % above it. |
| `accel_limit` | float32 | turn/s^2 | rw | Acceleration of a trapezoidal move. |
| `decel_limit` | float32 | turn/s^2 | rw | Deceleration of a trapezoidal move. |

### odrv0.axis0.min_endstop

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endstop_state` | bool |  | ro | True while the endstop is pressed (after debouncing). |

Objects: [config](#odrv0axis0min_endstopconfig)

### odrv0.axis0.min_endstop.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_num` | uint16 |  | rw | The endstop's GPIO; it must be in a `GPIO_MODE_DIGITAL` mode. |
| `enabled` | bool |  | rw | Enables the endstop. Outside homing |
| `offset` | float32 | turns | rw | Position the axis takes at the endstop after homing. |
| `is_active_high` | bool |  | rw | True when the input reads high while pressed. |
| `debounce_ms` | uint32 |  | rw | Time the input must stay at a level before it counts. |

### odrv0.axis0.max_endstop

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endstop_state` | bool |  | ro | True while the endstop is pressed (after debouncing). |

Objects: [config](#odrv0axis0max_endstopconfig)

### odrv0.axis0.max_endstop.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_num` | uint16 |  | rw | The endstop's GPIO; it must be in a `GPIO_MODE_DIGITAL` mode. |
| `enabled` | bool |  | rw | Enables the endstop. Outside homing |
| `offset` | float32 | turns | rw | Position the axis takes at the endstop after homing. |
| `is_active_high` | bool |  | rw | True when the input reads high while pressed. |
| `debounce_ms` | uint32 |  | rw | Time the input must stay at a level before it counts. |

### odrv0.axis0.mechanical_brake

| Function | Description |
|---|---|
| `engage()` | This function engages the mechanical brake if one is present and enabled. |
| `release()` | This function releases the mechanical brake if one is present and enabled. |

Objects: [config](#odrv0axis0mechanical_brakeconfig)

### odrv0.axis0.mechanical_brake.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_num` | uint16 |  | rw | GPIO that drives the brake; it must be in `GPIO_MODE_MECH_BRAKE`. |
| `is_active_low` | bool |  | rw | True when a low output engages the brake. |

### odrv0.axis0.task_times

Objects: [thermistor_update](#odrv0axis0task_timesthermistor_update), [encoder_update](#odrv0axis0task_timesencoder_update), [sensorless_estimator_update](#odrv0axis0task_timessensorless_estimator_update), [endstop_update](#odrv0axis0task_timesendstop_update), [can_heartbeat](#odrv0axis0task_timescan_heartbeat), [controller_update](#odrv0axis0task_timescontroller_update), [open_loop_controller_update](#odrv0axis0task_timesopen_loop_controller_update), [acim_estimator_update](#odrv0axis0task_timesacim_estimator_update), [motor_update](#odrv0axis0task_timesmotor_update), [current_controller_update](#odrv0axis0task_timescurrent_controller_update), [dc_calib](#odrv0axis0task_timesdc_calib), [current_sense](#odrv0axis0task_timescurrent_sense), [pwm_update](#odrv0axis0task_timespwm_update)

### odrv0.axis0.task_times.thermistor_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.encoder_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.sensorless_estimator_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.endstop_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.can_heartbeat

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.controller_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.open_loop_controller_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.acim_estimator_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.motor_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.current_controller_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.dc_calib

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.current_sense

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

### odrv0.axis0.task_times.pwm_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 | ticks | ro | Start of the task in the profiled control period, as a TIM13 timestamp in 168 MHz ticks. Recorded when `task_timers_armed` is set. |
| `end_time` | uint32 | ticks | ro | End of the task in the profiled control period. |
| `length` | uint32 | ticks | ro | The task's duration in the profiled control period (168 ticks = 1 µs). |
| `max_length` | uint32 | ticks | rw | The task's longest duration since boot; write 0 to reset it. |

## Enums and error bits

### Axis.AxisState

Enum.

| Name | Value | Description |
|---|---|---|
| `UNDEFINED` | 0 | No request. `requested_state` reads this once the state machine has taken a request. |
| `IDLE` | 1 | Disable motor PWM and do nothing. |
| `STARTUP_SEQUENCE` | 2 | Run the startup procedure.<br>The `config.startup_*` flags choose the steps. |
| `FULL_CALIBRATION_SEQUENCE` | 3 | Run motor calibration and then encoder offset calibration (or encoder index search if `<axis>.encoder.config.use_index` is `True`). |
| `MOTOR_CALIBRATION` | 4 | Measure phase resistance and phase inductance of the motor.<br>Writes `motor.config.phase_resistance` and `motor.config.phase_inductance`. Saved with `motor.config.pre_calibrated = True`, the results make this calibration unnecessary at the next boot. |
| `ENCODER_INDEX_SEARCH` | 6 | Turn the motor in one direction until the encoder index is traversed.<br>This state can only be entered if `encoder.config.use_index` is `True`. |
| `ENCODER_OFFSET_CALIBRATION` | 7 | Turn the motor in one direction for a few seconds and then back to measure the offset between the encoder position and the electrical phase.<br>Needs a calibrated motor (`motor.is_calibrated`). Success sets `encoder.is_ready`. |
| `CLOSED_LOOP_CONTROL` | 8 | Run closed loop control.<br>What runs depends on `controller.config.control_mode`. Needs a calibrated motor (`motor.is_calibrated`) and a ready encoder (`encoder.is_ready`). Entering it starts from rest: zero velocity and torque setpoints, no running trajectory. |
| `LOCKIN_SPIN` | 9 | Run lockin spin.<br>Can only be entered if the motor is calibrated (`motor.is_calibrated`) or the motor direction is unspecified (`encoder.config.direction` == 1) |
| `ENCODER_DIR_FIND` | 10 | Run encoder direction search.<br>Can only be entered if the motor is calibrated (`motor.is_calibrated`). |
| `HOMING` | 11 | Run axis homing function.<br>Endstops must be enabled to use this feature. |
| `ENCODER_HALL_POLARITY_CALIBRATION` | 12 | Rotate the motor in lockin and calibrate hall polarity<br>ODrive assumes 120 degree electrical hall spacing. This routine determines if that is the case and sets the polarity if the halls are on 60 degree electrical spacing |
| `ENCODER_HALL_PHASE_CALIBRATION` | 13 | Rotate the motor for 30s to calibrate hall sensor edge offsets<br>The phase offset is not calibrated at this time, so the map is only relative |
| `ENCODER_CORRECTION_CALIBRATION` (added) | 14 | Measure the absolute encoder's per-angle error and fill the encoder's correction table<br>Turns an open-loop current vector (`motor.config.calibration_current`, `encoder.config.calib_scan_omega`) forward and back over `encoder.config.correction_scan_turns` mechanical turns. Needs a calibrated motor and a ready encoder. Run `ENCODER_OFFSET_CALIBRATION` again afterwards, then save. |

### Axis.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `INVALID_STATE` | 0x00000001 | An invalid state was requested.<br>You tried to run a state before you are allowed to. Typically you tried to run encoder calibration or closed loop control before the motor was calibrated, or you tried to run closed loop control before the encoder was calibrated. |
| `MOTOR_FAILED` | 0x00000040 | Check `motor.error` for more information. |
| `SENSORLESS_ESTIMATOR_FAILED` | 0x00000080 | Check `sensorless_estimator.error` for more information. |
| `ENCODER_FAILED` | 0x00000100 | Check `encoder.error` for more information. |
| `CONTROLLER_FAILED` | 0x00000200 | Check `controller.error` for more information. Set together with a controller fault, such as a following error or a soft limit violation. |
| `WATCHDOG_TIMER_EXPIRED` | 0x00000800 | The axis watchdog timer expired.<br>An amount of time greater than `config.watchdog_timeout` passed without the watchdog being fed. |
| `MIN_ENDSTOP_PRESSED` | 0x00001000 | The min endstop was pressed |
| `MAX_ENDSTOP_PRESSED` | 0x00002000 | The max endstop was pressed |
| `ESTOP_REQUESTED` | 0x00004000 | The estop message was sent over CAN |
| `HOMING_WITHOUT_ENDSTOP` | 0x00020000 | the min endstop was not enabled during homing |
| `OVER_TEMP` | 0x00040000 | Check `motor.error` for more details. |
| `UNKNOWN_POSITION` | 0x00080000 | There isn't a valid position estimate available. |

### Axis.WatchdogAction

Enum (added).

| Name | Value | Description |
|---|---|---|
| `DISARM` (added) | 0 | Set `AXIS_ERROR_WATCHDOG_TIMER_EXPIRED` and disarm (the motor goes limp): ODrive's behavior. |
| `DECEL_HOLD` (added) | 1 | Decelerate to a stop at `config.watchdog_decel`, then hold that position with torque capped at `config.watchdog_torque_lim`. Reported by `controller.timeout_active`, not as an error. Outside armed closed loop the watchdog disarms with an error as in DISARM. |

### Can.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `DUPLICATE_CAN_IDS` | 0x00000001 | Not raised by this firmware. |

### Can.Protocol

Bit flags.

| Name | Value | Description |
|---|---|---|
| `SIMPLE` | 0x00000001 | CANSimple, ODrive's CAN protocol, with this firmware's impedance command (0x01E) and endpoint access (0x01F). |

### Capture.CaptureState

Enum (added).

| Name | Value | Description |
|---|---|---|
| `IDLE` (added) | 0 | No capture recorded (or the channels changed since). |
| `ARMED` (added) | 1 | Recording and waiting for the trigger. |
| `TRIGGERED` (added) | 2 | Recording the post_trigger samples. |
| `DONE` (added) | 3 | Recording finished; the buffer can be read. |

### Capture.CaptureTrigger

Enum (added).

| Name | Value | Description |
|---|---|---|
| `IMMEDIATE` (added) | 0 | Trigger on the first sample. |
| `RISING` (added) | 1 | Trigger when trigger_channel goes from below trigger_level to at or above it. |
| `FALLING` (added) | 2 | Trigger when trigger_channel goes from above trigger_level to at or below it. |
| `MANUAL` (added) | 3 | Wait for trigger(). |

### Controller.ControlMode

Enum.

| Name | Value | Description |
|---|---|---|
| `VOLTAGE_CONTROL` | 0 | Note: This mode is not used internally. For voltage-only FOC, use `MotorType.GIMBAL` |
| `TORQUE_CONTROL` | 1 | Uses only the inner torque control loop. Use `input_torque` to command desired torque. Note the setting `motor.config.torque_constant`. Note the setting `enable_torque_mode_vel_limit`. |
| `VELOCITY_CONTROL` | 2 | Uses both the inner torque control loop and the velocity control loop. Use `input_vel` to command desired velocity, and `input_torque`. |
| `POSITION_CONTROL` | 3 | Uses the inner torque loop, the velocity control loop, and the outer position control loop. Use `input_pos` to command desired position, `input_vel` to command velocity feed-forward, and `input_torque` for torque feed-forward. |
| `IMPEDANCE_CONTROL` (added) | 4 | A spring and damper toward the setpoint, computed every control period: torque = input_kp * (pos_setpoint - pos) + input_kd * (vel_setpoint - vel) + torque_setpoint. No velocity integrator, no position gain scheduling; a steady load deflects the axis by load / input_kp. input_kp = input_kd = 0 is torque control (without `enable_torque_mode_vel_limit`); input_kp = 0 damps only. Soft limits, following-error checks (the position check only while input_kp > 0, the velocity check only while input_kd > 0), the torque limits and the watchdog apply as in position control. A watchdog DECEL_HOLD holds with the position-control gains (`pos_gain`, `vel_gain`, `vel_integrator_gain`). |

### Controller.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `OVERSPEED` | 0x00000001 | Motor speed exceeded `config.vel_limit * config.vel_limit_tolerance` and `config.enable_overspeed_error` was enabled.<br>Raise `config.vel_limit` (default 2 turn/s, 120 rpm) if the motor is meant to run faster. A sudden change of load can overshoot the limit even when no command exceeds it. `config.vel_limit_tolerance` (default 1.2) sets how far past the limit the speed can go; `config.enable_overspeed_error = False` turns the error off. |
| `INVALID_INPUT_MODE` | 0x00000002 | The `config.input_mode` setting was set to an invalid value. See InputMode for available values<br>Input modes and control modes are separate concepts. A control mode sets the type of control to be used, like position, velocity, or torque control. Input modes modify the input given (`input_pos`, etc) to give desired behavior. For example, in position *control mode*, the position filter *input mode* will smooth out `input_pos` commands to give smoother motion. |
| `UNSTABLE_GAIN` | 0x00000004 | Not raised by this firmware. |
| `INVALID_ESTIMATE` | 0x00000020 | Indicates the encoder estimation module declined to output a linear position or velocity value and the exception was caught. |
| `INVALID_CIRCULAR_RANGE` | 0x00000040 | Indicates the encoder estimation module declined to output a circular position value and the exception was caught. |
| `SPINOUT_DETECTED` | 0x00000080 | The motor mechanical power and electrical power do not agree. This is usually caused by a slipping encoder or incorrect encoder offset calibration. Check that your encoder is not slipping on the motor. If using an Index pin, check that you are not getting false index pulses caused by noise. This can happen if you are using unshielded cable for the encoder signals. |
| `POS_LIMIT_VIOLATION` (added) | 0x00000100 | The position went beyond `config.pos_min`/`config.pos_max` by more than `config.pos_limit_margin`.<br>Checked only while armed in closed loop. Entering closed loop outside the limits also raises it. |
| `POS_FOLLOWING_ERROR` (added) | 0x00000200 | \|pos_setpoint - pos_estimate\| exceeded `config.max_pos_error` (position control).<br>Catches jams, collisions and encoder slip. Checked only while armed in closed loop. |
| `VEL_FOLLOWING_ERROR` (added) | 0x00000400 | \|vel_setpoint - vel_estimate\| exceeded `config.max_vel_error` (velocity or position control).<br>Checked only while armed in closed loop. |

### Controller.InputMode

Enum.

| Name | Value | Description |
|---|---|---|
| `INACTIVE` | 0 | Disable inputs. Setpoints retain their last value. |
| `PASSTHROUGH` | 1 | Pass `input_pos`, `input_vel` and `input_torque` through to the setpoints directly.<br>For every control mode; the usual mode for impedance control and for a host that streams a smooth trajectory. |
| `VEL_RAMP` | 2 | Ramps the velocity setpoint toward `input_vel` at `config.vel_ramp_rate`.<br>Velocity control. `config.inertia` times the ramp's acceleration, plus `input_torque`, is the torque feed-forward. |
| `POS_FILTER` | 3 | Smooths `input_pos` with a critically damped second-order filter.<br>Position control. `config.input_filter_bandwidth` sets the filter; `config.inertia` times the filter's acceleration, plus `input_torque`, is the torque feed-forward. Step response: [Control](control.md#position-filter-3). |
| `MIX_CHANNELS` | 4 | Not implemented. |
| `TRAP_TRAJ` | 5 | Plans a trapezoidal move to each new `input_pos`.<br>Position or impedance control. `axis0.trap_traj.config.vel_limit`, `accel_limit` and `decel_limit` shape the move; `config.inertia` times the planned acceleration, plus `input_torque`, is the torque feed-forward during the move, and `input_torque` alone after it. A move: [Control](control.md#trapezoidal-trajectory-5). |
| `TORQUE_RAMP` | 6 | Ramps the torque setpoint toward `input_torque` at `config.torque_ramp_rate`.<br>Torque control. |
| `TUNING` | 8 | Adds sine waves to the inputs, for frequency-response tuning.<br>Set `control_mode` for the loop to tune and the `controller.autotuning` frequency and amplitudes; `input_pos`, `input_vel` and `input_torque` act as the sine waves' DC offsets. |

### Encoder.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `UNSTABLE_GAIN` | 0x00000001 | `config.bandwidth` is too high for the 8 kHz loop (4000 rad/s or more). |
| `CPR_POLEPAIRS_MISMATCH` | 0x00000002 | During offset calibration the encoder moved a different distance than `config.cpr` and the motor's `pole_pairs` predict, by more than `config.calib_range`. Check both values (the onboard AS5047: cpr 16384; pole pairs: magnets / 2). A rotor that stalls or slips during the scan (too little `calibration_current`, cogging, or a load) causes it too: raise `config.calib_scan_distance` (up to 4 times the default) or the calibration current. For an incremental encoder, CPR is 4 times its pulses per revolution. |
| `NO_RESPONSE` | 0x00000004 | Check the encoder's wiring and `config.mode`. |
| `UNSUPPORTED_ENCODER_MODE` | 0x00000008 | `config.mode` has a value the firmware doesn't support. |
| `ILLEGAL_HALL_STATE` | 0x00000010 | Hall effect encoder only have 6 valid states out of 8 (2^3) possible states. An invalid state can be caused by noise or a hardware fault. If you get this error and you are sure that your electrical connections are correct, add 22nF capacitors between the encoder A,B,Z pins and ground to filter out noise. |
| `INDEX_NOT_FOUND_YET` | 0x00000020 | Check that the encoder has an index pulse wired to Z (J5 pin 2 on the Mini). |
| `ABS_SPI_TIMEOUT` | 0x00000040 | Not raised by this firmware. |
| `ABS_SPI_COM_FAIL` | 0x00000080 | Too many absolute-encoder samples were missing or dropped: `spi_error_rate`, a filtered rate, rose above 5 %. Frame checks (`config.abs_spi_check_parity`, `abs_spi_reject_error_flag`, `abs_spi_max_jump`) count dropped frames as missing, so a wrong parity setting for the chip causes it too. |
| `ABS_SPI_NOT_READY` | 0x00000100 | Not raised by this firmware. |
| `HALL_NOT_CALIBRATED_YET` | 0x00000200 | Hall encoder mode needs `AXIS_STATE_ENCODER_HALL_PHASE_CALIBRATION` first. |

### Encoder.Mode

Enum.

| Name | Value | Description |
|---|---|---|
| `INCREMENTAL` | 0 | Quadrature encoder on J5 (A, B and an optional index Z). |
| `HALL` | 1 | Hall sensors on J5. |
| `SINCOS` | 2 | Analog sine and cosine signals on two GPIOs (`config.sincos_gpio_pin_sin`, `sincos_gpio_pin_cos`). |
| `SPI_ABS_CUI` | 256 | Compatible with CUI AMT23xx |
| `SPI_ABS_AMS` | 257 | AMS AS5047P/U (the Mini's onboard encoder), AS5048A/AS5048B (no daisy chain support). |
| `SPI_ABS_AEAT` | 258 | Supports AEAT-8800 |
| `SPI_ABS_RLS` | 259 | Supports RLS Orbis Encoders |
| `SPI_ABS_MA732` | 260 | MagAlpha MA732 magnetic encoder |

### Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `CONTROL_ITERATION_MISSED` | 0x00000001 | At least one control iteration was missed.<br>The main control loop is supposed to runs at a fixed frequency. If the device is computationally overloaded (e.g. too many active components) it's possible that one or more control iterations are skipped. |
| `DC_BUS_UNDER_VOLTAGE` | 0x00000002 | The DC voltage fell below the limit configured in `config.dc_bus_undervoltage_trip_level`.<br>Check that the power leads are connected securely and that the supply can deliver the motor's peak current: a supply that sags under load trips this error during fast moves at a high current limit. The default trip level is 8 V. `tools/sample.py` logs `vbus_voltage`, and `tools/capture.py` records it at 8 kHz. Lowering `axis0.motor.config.current_lim` or `axis0.controller.config.vel_limit` lowers the peak draw. |
| `DC_BUS_OVER_VOLTAGE` | 0x00000004 | The DC voltage exceeded the limit configured in `config.dc_bus_overvoltage_trip_level`.<br>Usually regen: a braking motor pushed current back into a supply that can't sink it. Enable a brake resistor (`config.enable_brake_resistor`, with `config.brake_resistance` set to its value, wiring included), or set flux braking or the bus current soft limits (`axis0.motor.config.flux_brake_start_voltage`, `I_bus_soft_min`). Keep the trip level a few volts above the supply voltage. |
| `DC_BUS_OVER_REGEN_CURRENT` | 0x00000008 | Current flowing back into the power supply exceeded `config.dc_max_negative_current`. This happens when the brake resistor is disabled or can't absorb the braking current.<br>Check that `config.enable_brake_resistor` is `True` and that supply voltage / `config.brake_resistance` exceeds `axis0.motor.config.current_lim` + `current_lim_margin`. |
| `DC_BUS_OVER_CURRENT` | 0x00000010 | Too much current was pulled from the power supply. `ibus` exceeded `config.dc_max_positive_current`. |
| `BRAKE_DEADTIME_VIOLATION` | 0x00000020 | The brake resistor's PWM timings left less than the required dead time between its two FETs. Every motor disarms. |
| `BRAKE_DUTY_CYCLE_NAN` | 0x00000040 | The computed brake duty cycle was not a number (for example from an invalid `vbus_voltage`). Every motor and the brake resistor disarm. |
| `INVALID_BRAKE_RESISTANCE` | 0x00000080 | `config.brake_resistance` is non-positive or NaN. Make sure that `config.brake_resistance` is a positive number. |

### GpioMode

Enum.

| Name | Value | Description |
|---|---|---|
| `DIGITAL` | 0 | The pin can be used for one or more of these functions: Step, dir, enable, encoder index, hall effect encoder, SPI encoder nCS (this one is exclusive). |
| `DIGITAL_PULL_UP` | 1 | Same as `DIGITAL` but with the internal pull-up resistor enabled. |
| `DIGITAL_PULL_DOWN` | 2 | Same as `DIGITAL` but with the internal pull-down resistor enabled. |
| `ANALOG_IN` | 3 | The pin can be used for one or more of these functions: Sin/cos encoders, analog input, `get_adc_voltage()`. |
| `UART_A` | 4 | See `config.enable_uart_a`. |
| `UART_B` | 5 | See `config.enable_uart_b` (GPIO3 TX, GPIO4 RX). |
| `UART_C` | 6 | This mode is not supported on ODrive v3.x. |
| `CAN_A` | 7 | See `config.enable_can_a`. |
| `I2C_A` | 8 | See `config.enable_i2c_a`. |
| `SPI_A` | 9 | The SPI pins are fixed in hardware on ODrive v3.x boards and the Mini |
| `PWM` | 10 | See `config.gpio1_pwm_mapping`. |
| `ENC0` | 11 | The pin is used by quadrature encoder 0. |
| `ENC2` | 13 | This mode is not supported on ODrive v3.x. |
| `MECH_BRAKE` | 14 | Drives an external mechanical brake (`axis0.mechanical_brake`). |
| `STATUS` | 15 | The pin is used for status output (see `config.error_gpio_pin`) |

### Motor.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `PHASE_RESISTANCE_OUT_OF_RANGE` | 0x00000001 | The measured motor phase resistance is outside of the plausible range.<br>During calibration the motor resistance and [inductance](https://en.wikipedia.org/wiki/Inductance) is measured. If the measured motor resistance or inductance falls outside a set range this error will be returned. Check that all motor leads are connected securely.<br>The measured values are in `config.phase_resistance` and `config.phase_inductance`. Small or gimbal motors can measure far outside the expected range: raise `config.resistance_calib_max_voltage` (default 2 V) or lower `config.calibration_current` (default 10 A), then calibrate again.<br>In general, the calibration needs `resistance_calib_max_voltage` above `calibration_current` x `phase_resistance` and below half of `vbus_voltage`. |
| `PHASE_INDUCTANCE_OUT_OF_RANGE` | 0x00000002 | The measured motor phase inductance is outside of the plausible range.<br>See `PHASE_RESISTANCE_OUT_OF_RANGE` for details. |
| `DRV_FAULT` | 0x00000008 | The gate driver chip reported an error.<br>The DRV8301 reported a fault (for example gate-drive undervoltage or overcurrent), and the motor disarmed. `axis0.last_drv_fault` holds the fault word from that moment. |
| `CONTROL_DEADLINE_MISSED` | 0x00000010 | The control loop didn't finish within its 125 µs period. A debugger halt causes it too. |
| `MODULATION_MAGNITUDE` | 0x00000080 | The bus voltage was insufficent to push the requested current through the motor. If you are getting this during motor calibration, make sure that `config.resistance_calib_max_voltage` is no more than half your bus voltage.<br>For gimbal motors, set `config.calibration_current` and `config.current_lim` (volts for a gimbal motor) to half the bus voltage or less. |
| `CURRENT_SENSE_SATURATION` | 0x00000400 | The current sense circuit saturated the current sense amplifier. This can be caused by setting `config.current_lim` higher than `config.requested_current_range`. If this happens, increase the requested current range, save the configuration, and reboot the controller. |
| `CURRENT_LIMIT_VIOLATION` | 0x00001000 | The motor current exceeded `motor.config.current_lim + motor.config.current_lim_margin`. The current controller is a PI controller, so it can experience overshoot. The PI gains are automatically calculated based on `config.current_control_bandwidth` and the motor resistance and inductance (pole placement). Some overshoot is normal, so a sensible solution is to increase the current limit margin if your current limit is large. |
| `MODULATION_IS_NAN` | 0x00010000 | The current controller computed a PWM duty cycle that was not a number. |
| `MOTOR_THERMISTOR_OVER_TEMP` | 0x00020000 | The motor thermistor measured a temperature above motor.motor_thermistor.config.temp_limit_upper |
| `FET_THERMISTOR_OVER_TEMP` | 0x00040000 | The inverter thermistor measured a temperature above motor.fet_thermistor.config.temp_limit_upper |
| `TIMER_UPDATE_MISSED` | 0x00080000 | A timer update event was missed. Perhaps the previous timer update took too much time. This is not expected in official release firmware. |
| `CURRENT_MEASUREMENT_UNAVAILABLE` | 0x00100000 | The phase current measurement is not available. The ADC failed to sample the current sensor in time. This is not expected in official release firmware. |
| `CONTROLLER_FAILED` | 0x00200000 | The motor was disarmed because the underlying controller failed. Usually this is the FOC controller. |
| `I_BUS_OUT_OF_RANGE` | 0x00400000 | The DC current sourced/sunk by this motor exceeded the configured hard limits. More specifically `I_bus` fell outside of the range `config.I_bus_hard_min` ... `config.I_bus_hard_max`. |
| `BRAKE_RESISTOR_DISARMED` | 0x00800000 | An attempt was made to run the motor PWM while the brake resistor was configured as enabled (`config.enable_brake_resistor`) but disarmed.<br>The most common cause: `config.enable_brake_resistor` was set to `True` without a save and reboot.<br>Otherwise a system-wide error disarmed the brake resistor; the board's `error` shows it (`tools/dump_board.py` decodes it). A reboot or `clear_errors()` re-arms the brake resistor. |
| `SYSTEM_LEVEL` | 0x01000000 | The motor had to be disarmed because of a system level error. See `ODrive:error` for more details. |
| `BAD_TIMING` | 0x02000000 | The main control loop got out of sync with the motor control loop. This could indicate that the main control loop got stuck. |
| `UNKNOWN_PHASE_ESTIMATE` | 0x04000000 | The current controller did not get a valid angle input. Maybe you didn't calibrate the encoder. |
| `UNKNOWN_PHASE_VEL` | 0x08000000 | The motor controller did not get a valid phase velocity input. |
| `UNKNOWN_TORQUE` | 0x10000000 | The motor controller did not get a valid torque input. |
| `UNKNOWN_CURRENT_COMMAND` | 0x20000000 | The current controller did not get a valid current setpoint. Maybe you didn't configure the controller correctly. |
| `UNKNOWN_CURRENT_MEASUREMENT` | 0x40000000 | The current controller did not get a valid current measurement. |
| `UNKNOWN_VBUS_VOLTAGE` | 0x80000000 | The current controller did not get a valid `ODrive:vbus_voltage` measurement. |
| `UNKNOWN_VOLTAGE_COMMAND` | 0x100000000 | The current controller did not get a valid feedforward voltage setpoint. |
| `UNKNOWN_GAINS` | 0x200000000 | The current controller gains were not configured. Run motor calibration or set `config.phase_resistance` and `config.phase_inductance` manually. |
| `CONTROLLER_INITIALIZING` | 0x400000000 | Internal value used while the controller is not yet ready to generate PWM timings. |
| `UNBALANCED_PHASES` | 0x800000000 | The motor phases are not balanced. |

### Motor.MotorType

Enum.

| Name | Value | Description |
|---|---|---|
| `HIGH_CURRENT` | 0 | Used for all standard "hobby-style" motors Permanant Magnet AC (PMAC) or Brushless DC (BLDC) motors. This is the default. Note: Assumes sinusoidal back-EMF, "wye" connected motors. Trapezoidal bEMF may have reduced controllability. |
| `GIMBAL` | 2 | Enables voltage-only FOC where V=IR can be assumed to be correct. Used for high-phase-resistance motors (> 1 ohm), which are typically sold as "Gimbal" motors. |
| `ACIM` | 3 | Used for FOC control of AC Induction Motors (ACIM), aka Asynchronous motors, |

### SensorlessEstimator.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `UNSTABLE_GAIN` | 0x00000001 | `config.pll_bandwidth` is too high for the 8 kHz loop. |
| `UNKNOWN_CURRENT_MEASUREMENT` | 0x00000002 | The estimator got no valid current measurement. |

### StreamProtocolType

Enum.

| Name | Value | Description |
|---|---|---|
| `Fibre` | 0 | Machine-to-machine protocol which gives access to all features of the board. The host tools and the `xdrive` library speak it over USB. |
| `Ascii` | 1 | Human-readable protocol for hosts that don't speak Fibre. Refer to [ODrive's ASCII protocol page](https://docs.odriverobotics.com/v/0.5.6/ascii-protocol.html) for details. |
| `Stdout` | 2 | Output of printf(). Only intended for developers who modify ODrive firmware. |
| `AsciiAndStdout` | 3 | Combination of `Ascii` and `Stdout`. |
