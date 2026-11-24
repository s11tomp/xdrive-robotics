# Property reference

Every object, property, function, enum and error bit the firmware exposes over USB, as `odrivetool` and the host tools see them (`odrv0.axis0.controller.config.pos_gain`). Items marked *(added)* are not in ODrive v0.5.6. Access: `rw` can be written, `ro` is read-only. Settings under a `config` object persist after `save_configuration()`; everything else resets at boot.

This file is generated from `src/odrive-interface.yaml` by `tools/gen_reference.py`; edit the interface file and run `make generate` instead of editing this file.

## Objects

### odrv0

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Error](#error) |  | rw |  |
| `vbus_voltage` | float32 | V | ro | Voltage on the DC bus as measured by the ODrive. |
| `ibus` | float32 | A | ro | Current on the DC bus as calculated by the ODrive.<br>A positive value means that the ODrive is consuming power from the power supply, a negative value means that the ODrive is sourcing power to the power supply.<br>This value is equal to the sum of the motor currents and the brake resistor currents. The motor currents are measured, the brake resistor current is calculated based on `config.brake_resistance`. |
| `ibus_report_filter_k` | float32 |  | rw | Filter gain for the reported `ibus`. Set to a value below 1.0 to get a smoother line when plotting `ibus`. Set to 1.0 to disable. This filter is only applied to the reported value and not for internal calculations. |
| `serial_number` | uint64 |  | ro |  |
| `hw_version_major` | uint8 |  | ro |  |
| `hw_version_minor` | uint8 |  | ro |  |
| `hw_version_variant` | uint8 |  | ro |  |
| `fw_version_major` | uint8 |  | ro |  |
| `fw_version_minor` | uint8 |  | ro |  |
| `fw_version_revision` | uint8 |  | ro |  |
| `fw_version_unreleased` | uint8 |  | ro | 0 for official releases, 1 otherwise |
| `brake_resistor_armed` | bool |  | ro |  |
| `brake_resistor_saturated` | bool |  | ro |  |
| `brake_resistor_current` | float32 |  | ro | Commanded brake resistor current |
| `n_evt_sampling` | uint32 |  | ro | Number of input sampling events since startup (modulo 2^32) |
| `n_evt_control_loop` | uint32 |  | ro | Number of control loop iterations since startup (modulo 2^32) |
| `task_timers_armed` | bool |  | rw | Set by a profiling application to trigger sampling of a single control iteration. Cleared by the device as soon as the sampling is complete. |
| `user_config_loaded` | uint32 |  | ro |  |
| `config_save_failed` (added) | bool |  | ro | True when the `save_configuration()` call that caused this boot failed to store the config. The board reboots after every save, so after a failed one it runs on the config saved before. Any other boot clears it. |
| `misconfigured` | bool |  | ro | If this property is true, something is bad in the configuration. The ODrive can still be used in this state but the user should investigate which setting is problematic. This variable does not cover all misconfigurations.<br>Possible causes: - A GPIO was set to a mode that it doesn't support - A GPIO was set to a mode for which the corresponding feature was not enabled. Example: `GPIO_MODE_UART_A` was used without enabling `config.enable_uart_a`. - A feature was enabled which is not supported on this hardware. Example: `config.enable_uart_c` set to true on ODrive v3.x. - A GPIO was used as an interrupt input for two internal components or two GPIOs that are mutually exclusive in their interrupt capability were both used as interrupt input. Example: `Axis:config.step_gpio_pin` of both axes were set to the same GPIO. |
| `test_property` | uint32 |  | rw |  |
| `otp_valid` | bool |  | ro |  |
| `adc1_scan_enabled` (added) | bool |  | ro | XDRIVE diagnostics: whether ADC1's free-running 16-channel scan (thermistors, GPIO analog inputs) runs. See set_adc1_scan. |

| Function | Description |
|---|---|
| `set_adc1_scan(enable: bool)` (added) | XDRIVE diagnostics (RAM only): stop or restart ADC1's free-running regular scan. The bus-voltage sample (ADC1 injected, timer-triggered) keeps running. While stopped, thermistor and analog-input readings are frozen at their last value. |
| `test_function(delta: int32)` -> int32 |  |
| `get_adc_voltage(gpio: uint32)` -> float32 | Reads the ADC voltage of the specified GPIO. The GPIO should be in `GPIO_MODE_ANALOG_IN`.} |
| `save_configuration()` -> bool | Saves the current configuration to non-volatile memory and reboots the board, whether or not the store succeeded: check `config_save_failed` once it is back up. Returns false without saving or rebooting while the motor is armed. |
| `erase_configuration()` | Resets all `config` variables to their default values and reboots the controller |
| `reboot()` | Reboots the controller without saving the current configuraiton |
| `enter_dfu_mode()` | Enters the Device Firmware Update mode |
| `get_interrupt_status(irqn: int32)` -> uint32 | Returns information about the specified interrupt number. |
| `get_dma_status(stream_num: uint8)` -> uint32 | Returns information about the specified DMA stream. |
| `get_gpio_states()` -> uint32 | Returns the logic states of all GPIOs. Bit i represents the state of GPIOi. |
| `get_drv_fault()` -> uint32 |  |
| `clear_errors()` | Clear all the errors of this device including all contained submodules. |

Objects: [task_times](#odrv0task_times), [system_stats](#odrv0system_stats), [capture](#odrv0capture), [can](#odrv0can), [config](#odrv0config), [axis0](#odrv0axis0)

### odrv0.task_times

Objects: [sampling](#odrv0task_timessampling), [control_loop_misc](#odrv0task_timescontrol_loop_misc), [control_loop_checks](#odrv0task_timescontrol_loop_checks), [dc_calib_wait](#odrv0task_timesdc_calib_wait), [capture_update](#odrv0task_timescapture_update)

### odrv0.task_times.sampling

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.task_times.control_loop_misc

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.task_times.control_loop_checks

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.task_times.dc_calib_wait

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.task_times.capture_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` (added) | uint32 |  | ro |  |
| `end_time` (added) | uint32 |  | ro |  |
| `length` (added) | uint32 |  | ro |  |
| `max_length` (added) | uint32 |  | rw |  |

### odrv0.system_stats

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `uptime` | uint32 |  | ro |  |
| `min_heap_space` | uint32 |  | ro |  |
| `max_stack_usage_axis` | uint32 |  | ro |  |
| `max_stack_usage_usb` | uint32 |  | ro |  |
| `max_stack_usage_uart` | uint32 |  | ro |  |
| `max_stack_usage_can` | uint32 |  | ro |  |
| `max_stack_usage_startup` | uint32 |  | ro |  |
| `max_stack_usage_analog` | uint32 |  | ro |  |
| `stack_size_axis` | uint32 |  | ro |  |
| `stack_size_usb` | uint32 |  | ro |  |
| `stack_size_uart` | uint32 |  | ro |  |
| `stack_size_startup` | uint32 |  | ro |  |
| `stack_size_can` | uint32 |  | ro |  |
| `stack_size_analog` | uint32 |  | ro |  |
| `prio_axis` | int32 |  | ro |  |
| `prio_usb` | int32 |  | ro |  |
| `prio_uart` | int32 |  | ro |  |
| `prio_startup` | int32 |  | ro |  |
| `prio_can` | int32 |  | ro |  |
| `prio_analog` | int32 |  | ro |  |

Objects: [usb](#odrv0system_statsusb), [i2c](#odrv0system_statsi2c)

### odrv0.system_stats.usb

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `rx_cnt` | uint32 |  | ro |  |
| `tx_cnt` | uint32 |  | ro |  |
| `tx_overrun_cnt` | uint32 |  | ro |  |

### odrv0.system_stats.i2c

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `addr` | uint8 |  | ro |  |
| `addr_match_cnt` | uint32 |  | ro |  |
| `rx_cnt` | uint32 |  | ro |  |
| `error_cnt` | uint32 |  | ro |  |

### odrv0.capture

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `decimation` (added) | uint32 |  | rw | Record one sample every `decimation` control periods. |
| `trigger_mode` (added) | [Capture.CaptureTrigger](#capturecapturetrigger) |  | rw |  |
| `trigger_channel` (added) | uint32 |  | rw | Channel (in add_channel order) watched by the RISING and FALLING triggers. |
| `trigger_level` (added) | float32 |  | rw | Level for the RISING and FALLING triggers, in the channel's own unit. |
| `post_trigger` (added) | uint32 |  | rw | Samples recorded after the trigger sample; start() clamps it to capacity - 1. |
| `state` (added) | [Capture.CaptureState](#capturecapturestate) |  | ro |  |
| `n_channels` (added) | uint32 |  | ro |  |
| `capacity` (added) | uint32 |  | ro | Frames the buffer holds: 8192 / n_channels. |
| `n_samples` (added) | uint32 |  | ro | Frames recorded (at most capacity). |
| `trigger_index` (added) | uint32 |  | ro | Frame of the trigger sample, in readout order. Valid when DONE. |
| `readout_endpoint` (added) | uint16 |  | ro |  |

| Function | Description |
|---|---|
| `add_channel(endpoint_id: uint32)` -> bool (added) | Append a property (float32, bool, uint8, uint16, uint32 or int32) by endpoint ID. Fails while recording, for an unknown ID, a function or another type, and beyond 8 channels. Discards the recorded data. |
| `clear_channels()` (added) | Remove all channels, stop any recording and discard the data. |
| `start()` -> bool (added) | Discard the data and record until the trigger plus post_trigger samples. Fails with no channels, an unknown trigger_mode, or a level trigger on a missing channel. |
| `trigger()` (added) | Trigger the armed capture now (any trigger_mode). |

### odrv0.can

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Can.Error](#canerror) |  | rw |  |

Objects: [config](#odrv0canconfig)

### odrv0.can.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `baud_rate` | uint32 |  | rw |  |
| `protocol` | [Can.Protocol](#canprotocol) |  | rw |  |

### odrv0.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `enable_uart_a` | bool |  | rw | Enables/disables UART_A.<br>You also need to set the corresponding GPIOs to GPIO_MODE_UART_A. Refer to [Hardware](hardware.md#gpios) to see which pins support UART_A. Changing this requires a reboot. |
| `enable_uart_b` | bool |  | rw | Enables/disables UART_B.<br>You also need to set the corresponding GPIOs to GPIO_MODE_UART_B. Refer to [Hardware](hardware.md#gpios) to see which pins support UART_B. Changing this requires a reboot. |
| `enable_uart_c` | bool |  | rw | Not supported on ODrive v3.x. |
| `uart_a_baudrate` | uint32 | baud/s | rw | Defines the baudrate used on the UART interface.<br>Some baudrates will have a small timing error due to hardware limitations.<br>Here's an (incomplete) list of baudrates for ODrive v3.x:<br>+-------------+---------------+-----------+ \| Configured \| Actual \| Error [%] \| +=============+===============+===========+ \| 1.2 KBps \| 1.2 KBps \| 0 \| +-------------+---------------+-----------+ \| 2.4 KBps \| 2.4 KBps \| 0 \| +-------------+---------------+-----------+ \| 9.6 KBps \| 9.6 KBps \| 0 \| +-------------+---------------+-----------+ \| 19.2 KBps \| 19.195 KBps \| 0.02 \| +-------------+---------------+-----------+ \| 38.4 KBps \| 38.391 KBps \| 0.02 \| +-------------+---------------+-----------+ \| 57.6 KBps \| 57.613 KBps \| 0.02 \| +-------------+---------------+-----------+ \| 115.2 KBps \| 115.068 KBps \| 0.11 \| +-------------+---------------+-----------+ \| 230.4 KBps \| 230.769 KBps \| 0.16 \| +-------------+---------------+-----------+ \| 460.8 KBps \| 461.538 KBps \| 0.16 \| +-------------+---------------+-----------+ \| 921.6 KBps \| 913.043 KBps \| 0.93 \| +-------------+---------------+-----------+ \| 1.792 MBps \| 1.826 MBps \| 1.9 \| +-------------+---------------+-----------+ \| 1.8432 MBps \| 1.826 MBps \| 0.93 \| +-------------+---------------+-----------+<br>For more information refer to Section 30.3.4 and Table 142 (the column with f_PCLK = 42 MHz) in the `STM datasheet <https://www.st.com/content/ccc/resource/technical/document/reference_manual/3d/6d/5a/66/b4/99/40/d4/DM00031020.pdf/files/DM00031020.pdf/jcr:content/translations/en.DM00031020.pdf>`__. |
| `uart_b_baudrate` | uint32 | baud/s | rw | Defines the baudrate used on the UART interface.<br>See `uart_a_baudrate` for details. |
| `uart_c_baudrate` | uint32 |  | rw | Not supported on ODrive v3.x. |
| `enable_can_a` | bool |  | rw | Enables CAN. Changing this setting requires a reboot. |
| `enable_i2c_a` | bool |  | rw | Enables I2C. The I2C pins on ODrive v3.x are in conflict with CAN. This setting has no effect if `enable_can_a` is also true. This setting has no effect on ODrive v3.2 or earlier. Changing this setting requires a reboot. |
| `usb_cdc_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw | The protocol that's being run on the device's virtual COM port on USB. Note that the ODrive has two independent interfaces on USB: One is the virtual COM port (affected by this option) and the other one is a vendor specific interface which always runs Fibre. So changing this option does not affect the working of odrivetool. |
| `uart0_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw |  |
| `uart1_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw |  |
| `uart2_protocol` | [StreamProtocolType](#streamprotocoltype) |  | rw |  |
| `max_regen_current` | float32 | Amps | rw | The bus current allowed to flow back to the power supply before the brake resistor module will start shunting current. |
| `brake_resistance` | float32 | ohm | rw | Value of the brake resistor connected to the ODrive.<br>If you set this to a lower value than the true brake resistance then the ODrive will not meed the `max_regen_current` constraint during braking, that is it will sink more than `max_regen_current` into the power supply. Some power supplies don't like this.<br>If you set this to a higher value than the true brake resistance then the ODrive will unnecessarily burn more power than required during braking. |
| `enable_brake_resistor` | bool |  | rw | Enable/disable the use of a brake resistor.<br>Setting this to False even though a brake resistor is connected is harmless. Setting this to True even though no brake resistor is connected can break the power supply. Changes to this value require a reboot to take effect. |
| `dc_bus_undervoltage_trip_level` | float32 | V | rw | Minimum voltage below which the motor stops operating. |
| `dc_bus_overvoltage_trip_level` | float32 | V | rw | Maximum voltage above which the motor stops operating.<br>This protects against cases in which the power supply fails to dissipate the brake power if the brake resistor is disabled. The default is 26V for the 24V board version and 52V for the 48V board version. |
| `enable_dc_bus_overvoltage_ramp` | bool |  | rw | Enables the DC bus overvoltage ramp feature.<br>If enabled, if the measured DC voltage exceeds `dc_bus_overvoltage_ramp_start`, the ODrive will sink more power than usual into the the brake resistor in an attempt to bring the voltage down again.<br>The brake duty cycle is increased by the following amount:<br>* `ODrive:vbus_voltage` == `dc_bus_overvoltage_ramp_start` => brake_duty_cycle += 0% * `ODrive:vbus_voltage` == `dc_bus_overvoltage_ramp_end` => brake_duty_cycle += 100%<br>Remarks: - This feature is active even when all motors are disarmed. - This feature is disabled if `brake_resistance` is non-positive. |
| `dc_bus_overvoltage_ramp_start` | float32 |  | rw | See `enable_dc_bus_overvoltage_ramp`.<br>Do not set this lower than your usual `ODrive:vbus_voltage`, unless you like fried brake resistors. |
| `dc_bus_overvoltage_ramp_end` | float32 |  | rw | See `enable_dc_bus_overvoltage_ramp`.<br>Must be larger than `dc_bus_overvoltage_ramp_start`, otherwise the ramp feature is disabled. |
| `dc_max_positive_current` | float32 | A | rw | Max current the power supply can source. |
| `dc_max_negative_current` | float32 | A | rw | Max current the power supply can sink.<br>You most likely want a non-positive value here. Set to -INFINITY to disable. Note: This should be greater in magnitude than `max_regen_current` |
| `error_gpio_pin` | uint32 |  | rw |  |
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
| `endpoint` | endpoint_ref |  | rw |  |
| `min` | float32 |  | rw |  |
| `max` | float32 |  | rw |  |

### odrv0.config.gpio4_analog_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw |  |
| `min` | float32 |  | rw |  |
| `max` | float32 |  | rw |  |

### odrv0.config.gpio1_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw |  |
| `min` | float32 |  | rw |  |
| `max` | float32 |  | rw |  |

### odrv0.config.gpio2_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw |  |
| `min` | float32 |  | rw |  |
| `max` | float32 |  | rw |  |

### odrv0.config.gpio3_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw |  |
| `min` | float32 |  | rw |  |
| `max` | float32 |  | rw |  |

### odrv0.config.gpio4_pwm_mapping

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endpoint` | endpoint_ref |  | rw |  |
| `min` | float32 |  | rw |  |
| `max` | float32 |  | rw |  |

### odrv0.axis0

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Axis.Error](#axiserror) |  | rw |  |
| `step_dir_active` | bool |  | ro |  |
| `last_drv_fault` | uint32 |  | ro |  |
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
| `enable_sensorless_mode` | bool |  | rw |  |
| `watchdog_timeout` | float32 | s | rw |  |
| `enable_watchdog` | bool |  | rw |  |
| `watchdog_action` (added) | [Axis.WatchdogAction](#axiswatchdogaction) |  | rw | XDRIVE: what the axis does in closed loop when the watchdog expires. |
| `watchdog_decel` (added) | float32 | turn/s^2 | rw | XDRIVE: deceleration for watchdog_action = DECEL_HOLD. |
| `watchdog_torque_lim` (added) | float32 | N·m | rw | XDRIVE: torque cap while decelerating and holding after a watchdog timeout. Infinity = the normal limit. |
| `step_gpio_pin` | uint16 |  | rw |  |
| `dir_gpio_pin` | uint16 |  | rw |  |

Objects: [calibration_lockin](#odrv0axis0configcalibration_lockin), [sensorless_ramp](#odrv0axis0configsensorless_ramp), [general_lockin](#odrv0axis0configgeneral_lockin), [can](#odrv0axis0configcan)

### odrv0.axis0.config.calibration_lockin

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `current` | float32 |  | rw |  |
| `ramp_time` | float32 |  | rw |  |
| `ramp_distance` | float32 |  | rw |  |
| `accel` | float32 |  | rw |  |
| `vel` | float32 |  | rw |  |

### odrv0.axis0.config.sensorless_ramp

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `current` | float32 | A | rw |  |
| `ramp_time` | float32 | s | rw |  |
| `ramp_distance` | float32 | rad | rw |  |
| `accel` | float32 | rad/s^2 | rw |  |
| `vel` | float32 | rad/s | rw |  |
| `finish_distance` | float32 | rad | rw |  |
| `finish_on_vel` | bool |  | rw |  |
| `finish_on_distance` | bool |  | rw |  |
| `finish_on_enc_idx` | bool |  | rw |  |

### odrv0.axis0.config.general_lockin

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `current` | float32 | A | rw |  |
| `ramp_time` | float32 | s | rw |  |
| `ramp_distance` | float32 | rad | rw |  |
| `accel` | float32 | rad/s^2 | rw |  |
| `vel` | float32 | rad/s | rw |  |
| `finish_distance` | float32 | rad | rw |  |
| `finish_on_vel` | bool |  | rw |  |
| `finish_on_distance` | bool |  | rw |  |
| `finish_on_enc_idx` | bool |  | rw |  |

### odrv0.axis0.config.can

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `node_id` | uint32 |  | rw |  |
| `is_extended` | bool |  | rw |  |
| `heartbeat_rate_ms` | uint32 |  | rw |  |
| `encoder_rate_ms` | uint32 |  | rw |  |
| `motor_error_rate_ms` | uint32 |  | rw |  |
| `encoder_error_rate_ms` | uint32 |  | rw |  |
| `controller_error_rate_ms` | uint32 |  | rw |  |
| `sensorless_error_rate_ms` | uint32 |  | rw |  |
| `encoder_count_rate_ms` | uint32 |  | rw |  |
| `iq_rate_ms` | uint32 |  | rw |  |
| `sensorless_rate_ms` | uint32 |  | rw |  |
| `bus_vi_rate_ms` | uint32 |  | rw |  |
| `impedance_pos_range` (added) | float32 | turn | rw | XDRIVE: full scale (+/-) of the position fields of the impedance command and reply (MSG_IMPEDANCE, 16 bit). Positions beyond it saturate. |
| `impedance_vel_range` (added) | float32 | turn/s | rw | XDRIVE: full scale (+/-) of the velocity fields of the impedance command and reply (12 bit). |
| `impedance_kp_max` (added) | float32 | N·m/turn | rw | XDRIVE: full scale of the impedance command's kp field (12 bit, 0..max). |
| `impedance_kd_max` (added) | float32 | N·m/(turn/s) | rw | XDRIVE: full scale of the impedance command's kd field (12 bit, 0..max). |
| `impedance_torque_range` (added) | float32 | N·m | rw | XDRIVE: full scale (+/-) of the torque fields of the impedance command and reply (12 bit). |

### odrv0.axis0.motor

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `last_error_time` | float32 |  | rw |  |
| `error` | [Motor.Error](#motorerror) |  | rw |  |
| `is_armed` | bool |  | ro |  |
| `is_calibrated` | bool |  | ro |  |
| `current_meas_phA` | float32 |  | ro |  |
| `current_meas_phB` | float32 |  | ro |  |
| `current_meas_phC` | float32 |  | ro |  |
| `DC_calib_phA` | float32 |  | rw |  |
| `DC_calib_phB` | float32 |  | rw |  |
| `DC_calib_phC` | float32 |  | rw |  |
| `I_bus` | float32 | A | ro | The current in the ODrive DC bus. This is also the current seen by the power supply in most systems. |
| `phase_current_rev_gain` | float32 |  | rw |  |
| `effective_current_lim` | float32 | A | ro | This value is the internally-limited value of phase current allowed according to the set current limit and the FET and Motor thermistor limits. |
| `max_allowed_current` | float32 | A | ro | Indicates the maximum current that can be measured by the current sensors in the current hardware configuration. This value depends on `config.requested_current_range`. |
| `max_dc_calib` | float32 | A | ro |  |
| `n_evt_current_measurement` | uint32 |  | ro | Number of current measurement events since startup (modulo 2^32) |
| `n_evt_pwm_update` | uint32 |  | ro | Number of PWM update events since startup (modulo 2^32) |
| `spike_count` (added) | uint32 |  | ro | XDRIVE diagnostics: control periods (while armed) in which the measured current vector jumped by more than spike_threshold from the previous period. A one-period glitch counts twice (out and back). |
| `spike_threshold` (added) | float32 | A | rw | XDRIVE diagnostics (RAM only): jump threshold for spike_count. |

| Function | Description |
|---|---|
| `get_spike_n(index: uint32)` -> uint32 (added) | XDRIVE diagnostics: odrv.n_evt_control_loop at spike event `index` (0..31, ring buffer; event k is at k % 32). |
| `get_spike_db(index: uint32)` -> float32 (added) | XDRIVE diagnostics: phase-B current change [A] at spike event `index`. |
| `get_spike_dc(index: uint32)` -> float32 (added) | XDRIVE diagnostics: phase-C current change [A] at spike event `index`. |

Objects: [fet_thermistor](#odrv0axis0motorfet_thermistor), [motor_thermistor](#odrv0axis0motormotor_thermistor), [current_control](#odrv0axis0motorcurrent_control), [config](#odrv0axis0motorconfig)

### odrv0.axis0.motor.fet_thermistor

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `temperature` | float32 | °C | ro |  |

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
| `temperature` | float32 | °C | ro |  |

Objects: [config](#odrv0axis0motormotor_thermistorconfig)

### odrv0.axis0.motor.motor_thermistor.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_pin` | uint16 |  | rw |  |
| `poly_coefficient_0` | float32 |  | rw |  |
| `poly_coefficient_1` | float32 |  | rw |  |
| `poly_coefficient_2` | float32 |  | rw |  |
| `poly_coefficient_3` | float32 |  | rw |  |
| `temp_limit_lower` | float32 |  | rw | The lower limit when the controller starts limiting current. |
| `temp_limit_upper` | float32 |  | rw | The upper limit when current limit reaches 0 Amps and an over temperature error is triggered. |
| `enabled` | bool |  | rw | Whether this thermistor is enabled. |

### odrv0.axis0.motor.current_control

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `p_gain` | float32 |  | ro |  |
| `i_gain` | float32 |  | ro |  |
| `I_measured_report_filter_k` | float32 |  | rw |  |
| `Id_setpoint` | float32 |  | ro |  |
| `Iq_setpoint` | float32 |  | ro |  |
| `Vd_setpoint` | float32 |  | ro |  |
| `Vq_setpoint` | float32 |  | ro |  |
| `phase` | float32 |  | ro |  |
| `phase_vel` | float32 |  | ro |  |
| `Ialpha_measured` | float32 |  | ro |  |
| `Ibeta_measured` | float32 |  | ro |  |
| `Id_measured` | float32 | A | ro | The phase current measured along the "d" axis in the FOC control loop. This should be close to 0 for typical surface permanent magnet motors. |
| `Iq_measured` | float32 | A | ro | The phase current measured along the "q" axis in the FOC control loop. This is the torque-generating current, so motor torque is approx. `torque_constant * Iq_measured` |
| `power` | float32 | W | ro | The electrical power being delivered to the motor |
| `v_current_control_integral_d` | float32 |  | rw |  |
| `v_current_control_integral_q` | float32 |  | rw |  |
| `final_v_alpha` | float32 |  | ro |  |
| `final_v_beta` | float32 |  | ro |  |

### odrv0.axis0.motor.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `pre_calibrated` | bool |  | rw | Indicates to the ODrive that the parameters `config.phase_resistance` and `config.phase_inductance` are valid at system start. If these are valid and `pre_calibrated` is set to `True`, motor calibration can be skipped. |
| `pole_pairs` | int32 |  | rw | The number of pole pairs in the motor. Note this is equal to 1/2 of the number of magnets (not coils!) in a typical hobby motor. |
| `calibration_current` | float32 |  | rw | The current used to measure resistance during `AXIS_STATE_MOTOR_CALIBRATION`. |
| `resistance_calib_max_voltage` | float32 |  | rw | The maximum voltage allowed during `AXIS_STATE_MOTOR_CALIBRATION`. This should be set to less than `(0.5 * vbus_voltage)`, but high enough to satisfy V=IR during motor calibration, where I is `config.calibration_current` and R is `config.phase_resistance` |
| `phase_inductance` | float32 | henry | rw |  |
| `phase_resistance` | float32 | ohm | rw |  |
| `torque_constant` | float32 | N·m/A | rw |  |
| `motor_type` | [Motor.MotorType](#motormotortype) |  | rw |  |
| `current_lim` | float32 | A | rw | Maximum commanded current allowed |
| `current_lim_margin` | float32 | A | rw | Maximum measured current allowed above `current_lim`. Any value above `current_lim + curren_lim_margin` will throw a `CURRENT_LIMIT_VIOLATION` error. |
| `torque_lim` | float32 | N·m | rw | Maximum commanded torque allowed in the torque loop. |
| `inverter_temp_limit_lower` | float32 | °C | rw | Not implemented. |
| `inverter_temp_limit_upper` | float32 | °C | rw | Not implemented. |
| `requested_current_range` | float32 | A | rw | The minimum phase current range expected to be measured. This is used to set the current shunt amplifier gains. This should be set > `current_lim + curren_lim_margin`, but as low as possible to maximize precision and accuracy of the controller. |
| `current_control_bandwidth` | float32 | rad/s | rw | Sets the PI gains of the Q and D axis FOC control according to `phase_resistance` and `phase_inductance` to create a critically-damped controller with a -3dB bandwidth at this frequency. |
| `acim_gain_min_flux` | float32 |  | rw |  |
| `acim_autoflux_min_Id` | float32 |  | rw |  |
| `acim_autoflux_enable` | bool |  | rw |  |
| `acim_autoflux_attack_gain` | float32 |  | rw |  |
| `acim_autoflux_decay_gain` | float32 |  | rw |  |
| `R_wL_FF_enable` | bool |  | rw | Enables automatic feedforward of the R*wL term in the current controller. |
| `bEMF_FF_enable` | bool |  | rw | Enables automatic feedforward of the bEMF term in the current controller. |
| `I_bus_hard_min` | float32 | A | rw | If the controller fails to keep this motor's DC current (`ODrive.Motor:I_bus`) above this value the motor gets disarmed immediately. Most likely you want a negative value here. Set to -inf to disable. Take noise into account when chosing a value. |
| `I_bus_hard_max` | float32 | A | rw | If the controller fails to keep this motor's DC current (`ODrive.Motor:I_bus`) below this value the motor gets disarmed immediately. Usually this is set in conjunction with `I_bus_hard_min`. Set to inf to disable. Take noise into account when chosing a value. |
| `I_bus_soft_min` (added) | float32 | A | rw | XDRIVE: lowest bus current (most regen) the motor aims for. Each control period the torque current is clamped so that the predicted bus current, 1.5 * (R * (Id^2 + Iq^2) + back-EMF * Iq) / vbus, stays at or above this value. Values above 0 count as 0. Braking at speed is limited to what copper losses (including flux braking) and this regen allowance absorb. -inf (default) disables it. |
| `I_bus_soft_max` (added) | float32 | A | rw | XDRIVE: highest bus current the motor aims for, by the same prediction as `I_bus_soft_min`; caps this board's draw from a shared supply. Values below 0 count as 0. inf (default) disables it. |
| `flux_brake_start_voltage` (added) | float32 | V | rw | XDRIVE: flux braking. Above this bus voltage the motor adds d-axis current Id = -flux_brake_gain * (vbus - start), up to the current limit, to burn bus energy in the windings (1.5 * R * Id^2). Set it a little above the supply voltage and below `dc_bus_overvoltage_trip_level`. inf (default) disables it. |
| `flux_brake_gain` (added) | float32 | A/V | rw | XDRIVE: flux-braking d-axis current per volt above `flux_brake_start_voltage`. |
| `I_leak_max` | float32 | A | rw | In almost all scenarios, the currents on phase A, B and C should add up to zero. A small amount of measurement noise is expected. However if the sum of A, B, C currents exceeds this configuration value, the motor gets disarmed immediately.<br>Note that this feature is only works on devices with three current sensors (e.g. ODrive v4). |
| `dc_calib_tau` | float32 |  | rw |  |

### odrv0.axis0.controller

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Controller.Error](#controllererror) |  | rw |  |
| `last_error_time` | float32 |  | rw |  |
| `input_pos` | float32 | turn | rw | Set the desired position of the axis. Only valid in `CONTROL_MODE_POSITION_CONTROL`.startup. Also updates the step count. In `INPUT_MODE_TUNING`, this acts as a DC offset for the position sine wave. |
| `input_vel` | float32 | turn/s | rw | In `CONTROL_MODE_VELOCITY_CONTROL`, sets the desired velocity of the axis. In `CONTROL_MODE_POSITION_CONTROL`, sets the feed-forward velocity of the velocity controller In `INPUT_MODE_TUNING`, this acts as a DC offset for the velocity sine wave. |
| `input_torque` | float32 | N·m | rw | In `CONTROL_MODE_TORQUE_CONTROL`, sets the desired output torque of the axis. In `CONTROL_MODE_VELOCITY_CONTROL`, `CONTROL_MODE_POSITION_CONTROL` and `CONTROL_MODE_IMPEDANCE_CONTROL`, sets the feed-forward torque of the torque controller, in every input mode: `INPUT_MODE_VEL_RAMP`, `INPUT_MODE_POS_FILTER` and `INPUT_MODE_TRAP_TRAJ` add it to their `config.inertia` term. In `INPUT_MODE_TUNING`, this acts as a DC offset for the torque sine wave. |
| `input_kp` (added) | float32 | N·m/turn | rw | XDRIVE: stiffness in `CONTROL_MODE_IMPEDANCE_CONTROL`. RAM only; also set by the CAN impedance command. |
| `input_kd` (added) | float32 | N·m/(turn/s) | rw | XDRIVE: damping in `CONTROL_MODE_IMPEDANCE_CONTROL`. RAM only; also set by the CAN impedance command. |
| `pos_setpoint` | float32 | turn | ro | The position reference actually being used by the position controller. This is the same as `input_pos` in `INPUT_MODE_PASSTHROUGH`, but may vary according to `InputMode`. |
| `vel_setpoint` | float32 | turn/s | ro | The velocity reference actually being used by the velocity controller. This is the same as `input_vel` in `INPUT_MODE_PASSTHROUGH`, but may vary according to `InputMode`. |
| `torque_setpoint` | float32 | N·m | ro | The torque reference actually being used by the torque controller. This is the same as `input_vel` in `INPUT_MODE_PASSTHROUGH`, but may vary according to `InputMode`. |
| `trajectory_done` | bool |  | ro | Indicates the last commanded Trapezoidal Trajectory movement is complete. |
| `timeout_active` (added) | bool |  | ro | XDRIVE: the axis watchdog expired with `axis.config.watchdog_action = DECEL_HOLD`. The controller decelerates to a stop at `axis.config.watchdog_decel`, holds that position and ignores new inputs. Ends on `clear_errors()` (feed the watchdog first) or on a new entry into closed loop; the inputs are then set to the hold position. |
| `vel_integrator_torque` | float32 | N·m | rw | The accumulated value of the velocity loop integrator |
| `anticogging_valid` | bool |  | rw |  |
| `autotuning_phase` | float32 | rad | rw | The current phase angle of the `INPUT_MODE_TUNING` sine wave generator |
| `mechanical_power` | float32 | Watt | ro | Mechanical power estimate. Torque * velocity |
| `electrical_power` | float32 | Watt | ro | Electrical power estimate. Vdq·Idq |

| Function | Description |
|---|---|
| `move_incremental(displacement: float32, from_input_pos: bool)` | Moves the axes' goal point by a specified increment. |
| `start_anticogging_calibration()` |  |
| `remove_anticogging_bias()` -> float32 |  |
| `get_anticogging_value(index: uint32)` -> float32 |  |

Objects: [config](#odrv0axis0controllerconfig), [autotuning](#odrv0axis0controllerautotuning)

### odrv0.axis0.controller.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gain_scheduling_width` | float32 |  | rw |  |
| `enable_vel_limit` | bool |  | rw |  |
| `enable_torque_mode_vel_limit` | bool |  | rw | Enable velocity limit in torque control mode (requires a valid velocity estimator). |
| `enable_gain_scheduling` | bool |  | rw | Enable the experimental "gain scheduling" module, which reduces the `pos_gain`, `vel_gain`, and `vel_integrator_gain` according to the position error. Also known as "anti-hunt" |
| `enable_overspeed_error` | bool |  | rw | Enables the velocity controller's overspeed error |
| `control_mode` | [Controller.ControlMode](#controllercontrolmode) |  | rw |  |
| `input_mode` | [Controller.InputMode](#controllerinputmode) |  | rw |  |
| `pos_gain` | float32 | (turn/s) / turn | rw | units = (turn/s) / turn |
| `vel_gain` | float32 | N·m / (turn/s) | rw | units = N·m / (turn/s) |
| `vel_integrator_gain` | float32 | N·m / (turn/s * s) | rw | units = N·m / (turn/s * s) |
| `vel_integrator_limit` | float32 | N·m | rw | Limit the integrator output (independent of proportional gain output). Set to infinity to disable. Units = N·m |
| `vel_limit` | float32 | turn/s | rw | Infinity to disable. |
| `vel_limit_tolerance` | float32 |  | rw | Ratio to `vel_limit`. Infinity to disable. |
| `vel_ramp_rate` | float32 | turn/s^2 | rw |  |
| `torque_ramp_rate` | float32 | N·m / sec | rw |  |
| `circular_setpoints` | bool |  | rw |  |
| `circular_setpoint_range` | float32 |  | rw | circular range in [turns] for position setpoints when circular_setpoints is True |
| `steps_per_circular_range` | int32 |  | rw | Number of steps within the circular setpoint range. Set this and the circular setpoint range to powers of 2 for the best results. |
| `homing_speed` | float32 | turn/s | rw | The speed at which the axis moves towards the `min_endstop` during `AXIS_STATE_HOMING` |
| `inertia` | float32 | N·m/(turn/s^2) | rw |  |
| `input_filter_bandwidth` | float32 | rad/s | rw | The desired bandwidth for `INPUT_MODE_POS_FILTER`.<br>Sets the position filter's P and I gains to emulate a critically-damped 2nd order mass-spring-damper motion. |
| `mechanical_power_bandwidth` | float32 | rad/s | rw | Bandwidth for mechanical power estimate. Used for spinout detection |
| `electrical_power_bandwidth` | float32 | rad/s | rw | Bandwidth for electrical power estimate. Used for spinout detection. Dot product of Vdq and Idq |
| `spinout_mechanical_power_threshold` | float32 | Watt | rw | Mechanical power threshold for spinout detection. This should be a negative value |
| `spinout_electrical_power_threshold` | float32 | Watt | rw | Electrical power threshold for spinout detection. This should be a positive value |
| `pos_min` (added) | float32 | turn | rw | XDRIVE: soft limit. Trap-trajectory targets and the position setpoint are clamped to [pos_min, pos_max]. -Infinity to disable. |
| `pos_max` (added) | float32 | turn | rw | XDRIVE: soft limit, see pos_min. Infinity to disable. |
| `pos_limit_margin` (added) | float32 | turn | rw | XDRIVE: POS_LIMIT_VIOLATION when the position estimate is beyond a limit by more than this. |
| `max_pos_error` (added) | float32 | turn | rw | XDRIVE: POS_FOLLOWING_ERROR threshold. Infinity to disable. |
| `max_vel_error` (added) | float32 | turn/s | rw | XDRIVE: VEL_FOLLOWING_ERROR threshold. Infinity to disable. |

Objects: [anticogging](#odrv0axis0controllerconfiganticogging)

### odrv0.axis0.controller.config.anticogging

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `index` | uint32 |  | ro |  |
| `pre_calibrated` | bool |  | rw |  |
| `calib_anticogging` | bool |  | ro |  |
| `calib_pos_threshold` | float32 |  | rw |  |
| `calib_vel_threshold` | float32 |  | rw |  |
| `cogging_ratio` | float32 |  | ro |  |
| `anticogging_enabled` | bool |  | rw |  |

### odrv0.axis0.controller.autotuning

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `frequency` | float32 | Hz | rw |  |
| `pos_amplitude` | float32 | turns | rw |  |
| `vel_amplitude` | float32 | turns/sec | rw |  |
| `torque_amplitude` | float32 | N·m | rw |  |

### odrv0.axis0.encoder

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [Encoder.Error](#encodererror) |  | rw |  |
| `is_ready` | bool |  | ro |  |
| `index_found` | bool |  | ro |  |
| `shadow_count` | int32 | counts | ro | Raw linear count from the encoder. |
| `count_in_cpr` | int32 | counts | ro | Raw circular count from the encoder on [0, cpr) |
| `interpolation` | float32 |  | ro |  |
| `phase` | float32 |  | ro |  |
| `pos_estimate` | float32 | turns | ro | Linear position estimate of the encoder, in turns. Also known as "multi-turn" position. |
| `pos_estimate_counts` | float32 | counts | ro | Linear position estimate of the encoder, in counts. Equal to `pos_estimate * config.cpr` |
| `pos_circular` | float32 | turns | ro | Circular position estimate of the encoder, as a decimal from [0, 1). Also known as "single-turn" position. |
| `pos_cpr_counts` | float32 | counts | ro | Circular position estimate of the encoder, on the space [0, cpr). |
| `delta_pos_cpr_counts` | float32 | counts | ro | Circular position delta of the encoder in the most recent loop. Primarily for debug purposes, it indicates much the encoder changed since the last time it was checked. |
| `hall_state` | uint8 |  | ro |  |
| `vel_estimate` | float32 | turn/s | ro | Estimate of the linear velocity of an axis in turn/s |
| `vel_estimate_counts` | float32 | counts/sec | ro | Estimate of the linear velocity of an axis, in counts/s. |
| `calib_scan_response` | float32 |  | ro |  |
| `pos_abs` | int32 |  | rw | The last (valid) position from an absolute encoder, if used. |
| `spi_error_rate` | float32 |  | ro |  |
| `spi_frame_count` (added) | uint32 |  | ro | XDRIVE: absolute-encoder SPI frames received. |
| `spi_error_flag_count` (added) | uint32 |  | ro | XDRIVE: AMS frames with the error flag (bit 14) set. |
| `spi_warning_flag_count` (added) | uint32 |  | ro | XDRIVE: AMS frames with bit 15 set (AS5047U warning flag; AS5047P parity). |
| `spi_jump_count` (added) | uint32 |  | ro | XDRIVE: samples dropped because they jumped further than config.abs_spi_max_jump. |
| `spi_last_frame` (added) | uint16 |  | ro | XDRIVE: last raw AMS SPI frame. |
| `spi_parity_error_count` (added) | uint32 |  | ro | XDRIVE: AMS frames with odd parity (meaningful for an AS5047P). |
| `pos_abs_raw` (added) | int32 |  | ro | XDRIVE: last good raw absolute position, before the correction table. |
| `correction_rms` (added) | float32 | counts | ro | XDRIVE: rms encoder error measured by the last correction calibration. |
| `correction_peak` (added) | float32 | counts | ro | XDRIVE: largest \|error\| measured by the last correction calibration. |
| `correction_bins` (added) | uint32 |  | ro | XDRIVE: bins the last correction calibration covered in both directions (256 = all). |

| Function | Description |
|---|---|
| `set_linear_count(count: int32)` | Set the current linear position of the axis, in counts |
| `get_correction(index: uint32)` -> float32 (added) | XDRIVE: correction table entry (0..255), counts. |
| `set_correction(index: uint32, val: float32)` (added) | XDRIVE: set a correction table entry (0..255), counts. |

Objects: [config](#odrv0axis0encoderconfig)

### odrv0.axis0.encoder.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `mode` | [Encoder.Mode](#encodermode) |  | rw |  |
| `use_index` | bool |  | rw | Set this to `True` when using an encoder with an index pin to allow pre-calibration of the encoder and encoder index search. |
| `index_offset` | float32 |  | rw | When the index is found, the linear position of the axis will be set to this value if `use_index_offset` is set to `True`. |
| `use_index_offset` | bool |  | rw | Set this to `True` to have the axis set the linear position of the axis to `index_offset` when the index is found during encoder index search |
| `find_idx_on_lockin_only` | bool |  | rw |  |
| `abs_spi_cs_gpio_pin` | uint16 |  | rw | Make sure that the GPIO is in `GPIO_MODE_DIGITAL`. |
| `abs_spi_max_jump` (added) | uint16 | counts | rw | XDRIVE: drop an absolute-encoder sample that is further than this from the last good one (0 = off). Accepted after 3 in a row. |
| `correction_enabled` (added) | bool |  | rw | XDRIVE: add the correction table (get_correction/set_correction) to the raw absolute position. |
| `correction_scan_turns` (added) | float32 | turns | rw | XDRIVE: mechanical turns each way for AXIS_STATE_ENCODER_CORRECTION_CALIBRATION. |
| `correction_max_harmonic` (added) | uint8 |  | rw | XDRIVE: the correction calibration keeps harmonics 1..N per turn of the measured error (0 = raw bins). Higher orders are cogging, not encoder error. |
| `abs_spi_check_parity` (added) | bool |  | rw | XDRIVE: drop AMS frames with odd parity. For an AS5047P (bit 15 = even parity); an AS5047U has none. |
| `abs_spi_reject_error_flag` (added) | bool |  | rw | XDRIVE: drop AMS frames with the error flag set. Off by default; the flag is sticky until the chip's ERRFL register is read. |
| `cpr` | int32 |  | rw | Counts per Revolution of the encoder. This is 4x the Pulses per Revolution. |
| `phase_offset` | int32 |  | rw |  |
| `phase_offset_float` | float32 |  | rw |  |
| `direction` | int32 |  | rw |  |
| `pre_calibrated` | bool |  | rw |  |
| `enable_phase_interpolation` | bool |  | rw |  |
| `bandwidth` | float32 | rad/s | rw |  |
| `calib_range` | float32 | turn | rw | The error threshold for encoder offset calibration, in turns. If the |
| `calib_scan_distance` | float32 | rad (electrical) | rw | The distance the motor is turned during encoder offset calibration. This is in the electrical frame, so if you want a 7pp motor to turn 1 mechanical revolution, you would put `(7 * 2*pi)` |
| `calib_scan_omega` | float32 | rad/s (electrical) | rw | The speed the motor turns during encoder offset calibration. This is in the electrical frame, so a 7pp motor rotating 1 mechanical revolution in 2 sec would be set to `(7 * 2*pi) / 2` |
| `ignore_illegal_hall_state` | bool |  | rw | Ignore the error "Illegal Hall State" |
| `hall_polarity` | uint8 |  | rw |  |
| `hall_polarity_calibrated` | bool |  | rw |  |
| `sincos_gpio_pin_sin` | uint16 |  | rw | Analog sine signal of a sin/cos encoder. The corresponding GPIO must be in `GPIO_MODE_ANALOG_IN`. |
| `sincos_gpio_pin_cos` | uint16 |  | rw | Analog cosine signal of a sin/cos encoder. The corresponding GPIO must be in `GPIO_MODE_ANALOG_IN`. |

### odrv0.axis0.acim_estimator

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `rotor_flux` | float32 | A | ro | estimated magnitude of the rotor flux |
| `slip_vel` | float32 | rad/s | ro | estimated slip between physical and electrical angular velocity} |
| `phase_offset` | float32 | rad | ro | estimate offset between physical and electrical angular position} |
| `stator_phase_vel` | float32 | rad/s | ro | calculated setpoint for the electrical velocity} |
| `stator_phase` | float32 | rad | ro | calculated setpoint for the electrical phase} |

Objects: [config](#odrv0axis0acim_estimatorconfig)

### odrv0.axis0.acim_estimator.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `slip_velocity` | float32 |  | rw |  |

### odrv0.axis0.sensorless_estimator

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `error` | [SensorlessEstimator.Error](#sensorlessestimatorerror) |  | rw |  |
| `phase` | float32 | rad | ro |  |
| `pll_pos` | float32 | rad | ro |  |
| `phase_vel` | float32 | rad/s | ro |  |
| `vel_estimate` | float32 | turn/s | ro |  |

Objects: [config](#odrv0axis0sensorless_estimatorconfig)

### odrv0.axis0.sensorless_estimator.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `observer_gain` | float32 |  | rw |  |
| `pll_bandwidth` | float32 |  | rw |  |
| `pm_flux_linkage` | float32 |  | rw |  |

### odrv0.axis0.trap_traj

Objects: [config](#odrv0axis0trap_trajconfig)

### odrv0.axis0.trap_traj.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `vel_limit` | float32 | turn/s | rw |  |
| `accel_limit` | float32 | turn/s^2 | rw |  |
| `decel_limit` | float32 | turn/s^2 | rw |  |

### odrv0.axis0.min_endstop

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endstop_state` | bool |  | ro |  |

Objects: [config](#odrv0axis0min_endstopconfig)

### odrv0.axis0.min_endstop.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_num` | uint16 |  | rw | Make sure the corresponding GPIO is in `GPIO_MODE_DIGITAL`. |
| `enabled` | bool |  | rw |  |
| `offset` | float32 | turns | rw |  |
| `is_active_high` | bool |  | rw |  |
| `debounce_ms` | uint32 |  | rw |  |

### odrv0.axis0.max_endstop

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `endstop_state` | bool |  | ro |  |

Objects: [config](#odrv0axis0max_endstopconfig)

### odrv0.axis0.max_endstop.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_num` | uint16 |  | rw | Make sure the corresponding GPIO is in `GPIO_MODE_DIGITAL`. |
| `enabled` | bool |  | rw |  |
| `offset` | float32 | turns | rw |  |
| `is_active_high` | bool |  | rw |  |
| `debounce_ms` | uint32 |  | rw |  |

### odrv0.axis0.mechanical_brake

| Function | Description |
|---|---|
| `engage()` | This function engages the mechanical brake if one is present and enabled. |
| `release()` | This function releases the mecahncal brake if one is present and enabled. |

Objects: [config](#odrv0axis0mechanical_brakeconfig)

### odrv0.axis0.mechanical_brake.config

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `gpio_num` | uint16 |  | rw |  |
| `is_active_low` | bool |  | rw |  |

### odrv0.axis0.task_times

Objects: [thermistor_update](#odrv0axis0task_timesthermistor_update), [encoder_update](#odrv0axis0task_timesencoder_update), [sensorless_estimator_update](#odrv0axis0task_timessensorless_estimator_update), [endstop_update](#odrv0axis0task_timesendstop_update), [can_heartbeat](#odrv0axis0task_timescan_heartbeat), [controller_update](#odrv0axis0task_timescontroller_update), [open_loop_controller_update](#odrv0axis0task_timesopen_loop_controller_update), [acim_estimator_update](#odrv0axis0task_timesacim_estimator_update), [motor_update](#odrv0axis0task_timesmotor_update), [current_controller_update](#odrv0axis0task_timescurrent_controller_update), [dc_calib](#odrv0axis0task_timesdc_calib), [current_sense](#odrv0axis0task_timescurrent_sense), [pwm_update](#odrv0axis0task_timespwm_update)

### odrv0.axis0.task_times.thermistor_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.encoder_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.sensorless_estimator_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.endstop_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.can_heartbeat

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.controller_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.open_loop_controller_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.acim_estimator_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.motor_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.current_controller_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.dc_calib

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.current_sense

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

### odrv0.axis0.task_times.pwm_update

| Property | Type | Unit | Access | Description |
|---|---|---|---|---|
| `start_time` | uint32 |  | ro |  |
| `end_time` | uint32 |  | ro |  |
| `length` | uint32 |  | ro |  |
| `max_length` | uint32 |  | rw |  |

## Enums and error bits

### Axis.AxisState

Enum.

| Name | Value | Description |
|---|---|---|
| `UNDEFINED` | 0 | will fall through to idle |
| `IDLE` | 1 | Disable motor PWM and do nothing. |
| `STARTUP_SEQUENCE` | 2 | Run the startup procedure.<br>the actual sequence is defined by the `config`.startup... flags |
| `FULL_CALIBRATION_SEQUENCE` | 3 | Run motor calibration and then encoder offset calibration (or encoder index search if `<axis>.encoder.config.use_index` is `True`). |
| `MOTOR_CALIBRATION` | 4 | Measure phase resistance and phase inductance of the motor.<br>* To store the results set `motor.config.pre_calibrated` to `True` and save the configuration (`save_configuration()`). After that you don't have to run the motor calibration on the next start up. * This modifies the variables `motor.config.phase_resistance` and `motor.config.phase_inductance`. |
| `ENCODER_INDEX_SEARCH` | 6 | Turn the motor in one direction until the encoder index is traversed.<br>This state can only be entered if `encoder.config.use_index` is `True`. |
| `ENCODER_OFFSET_CALIBRATION` | 7 | Turn the motor in one direction for a few seconds and then back to measure the offset between the encoder position and the electrical phase.<br>* Can only be entered if the motor is calibrated (`motor.is_calibrated`). * A successful encoder calibration will make the `encoder.is_ready` go to true. |
| `CLOSED_LOOP_CONTROL` | 8 | Run closed loop control.<br>* The action depends on the `controller.config.control_mode`. * Can only be entered if the motor is calibrated (`motor.is_calibrated`) and the encoder is ready (`encoder.is_ready`). |
| `LOCKIN_SPIN` | 9 | Run lockin spin.<br>Can only be entered if the motor is calibrated (`motor.is_calibrated`) or the motor direction is unspecified (`encoder.config.direction` == 1) |
| `ENCODER_DIR_FIND` | 10 | Run encoder direction search.<br>Can only be entered if the motor is calibrated (`motor.is_calibrated`). |
| `HOMING` | 11 | Run axis homing function.<br>Endstops must be enabled to use this feature. |
| `ENCODER_HALL_POLARITY_CALIBRATION` | 12 | Rotate the motor in lockin and calibrate hall polarity<br>ODrive assumes 120 degree electrical hall spacing. This routine determines if that is the case and sets the polarity if the halls are on 60 degree electrical spacing |
| `ENCODER_HALL_PHASE_CALIBRATION` | 13 | Rotate the motor for 30s to calibrate hall sensor edge offsets<br>The phase offset is not calibrated at this time, so the map is only relative |
| `ENCODER_CORRECTION_CALIBRATION` (added) | 14 | XDRIVE: measure the absolute encoder's per-angle error and fill encoder.config.correction_table<br>Turns an open-loop current vector (calibration_current, calib_scan_omega) forward and back over encoder.config.correction_scan_turns mechanical turns. Needs a calibrated motor and a ready encoder. Re-run ENCODER_OFFSET_CALIBRATION afterwards, then save. |

### Axis.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `INVALID_STATE` | 0x00000001 | An invalid state was requested.<br>You tried to run a state before you are allowed to. Typically you tried to run encoder calibration or closed loop control before the motor was calibrated, or you tried to run closed loop control before the encoder was calibrated. |
| `MOTOR_FAILED` | 0x00000040 | Check `motor.error` for more information. |
| `SENSORLESS_ESTIMATOR_FAILED` | 0x00000080 |  |
| `ENCODER_FAILED` | 0x00000100 | Check `encoder.error` for more information. |
| `CONTROLLER_FAILED` | 0x00000200 |  |
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
| `DISARM` (added) | 0 | Set AXIS_ERROR_WATCHDOG_TIMER_EXPIRED and disarm (the motor goes limp). Stock ODrive behavior. |
| `DECEL_HOLD` (added) | 1 | XDRIVE: decelerate to a stop at `config.watchdog_decel`, then hold that position with torque capped at `config.watchdog_torque_lim`. Reported by `controller.timeout_active`, not as an error. Outside armed closed loop the watchdog disarms with an error as in DISARM. |

### Can.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `DUPLICATE_CAN_IDS` | 0x00000001 |  |

### Can.Protocol

Bit flags.

| Name | Value | Description |
|---|---|---|
| `SIMPLE` | 0x00000001 | CANSimple, an ODrive-specific protocol for basic functionality |

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
| `IMPEDANCE_CONTROL` (added) | 4 | XDRIVE: a spring and damper toward the setpoint, computed every control period: torque = input_kp * (pos_setpoint - pos) + input_kd * (vel_setpoint - vel) + torque_setpoint. No velocity integrator, no position gain scheduling; a steady load deflects the axis by load / input_kp. input_kp = input_kd = 0 is torque control (without `enable_torque_mode_vel_limit`); input_kp = 0 damps only. Soft limits, following-error checks (the position check only while input_kp > 0, the velocity check only while input_kd > 0), the torque limits and the watchdog apply as in position control. A watchdog DECEL_HOLD holds with the position-control gains (`pos_gain`, `vel_gain`, `vel_integrator_gain`). |

### Controller.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `OVERSPEED` | 0x00000001 | Motor speed exceeded `config.vel_limit * config.vel_limit_tolerance` and `config.enable_overspeed_error` was enabled.<br>Try increasing `config.vel_limit`. The default of 2 turns per second gives a motor speed of only 120 RPM. Note: Even if you do not command your motor to exceed `config.vel_limit`, sudden changes in the load placed on a motor may cause this speed to be temporarily exceeded, resulting in this error.<br>You can also try increasing `config.vel_limit_tolerance`. The default value of 1.2 means it will only allow a 20% violation of the speed limit. You can set `config.enable_overspeed_error` to False to disable this error. |
| `INVALID_INPUT_MODE` | 0x00000002 | The `config.input_mode` setting was set to an invalid value. See InputMode for available values<br>Input modes and control modes are separate concepts. A control mode sets the type of control to be used, like position, velocity, or torque control. Input modes modify the input given (`input_pos`, etc) to give desired behavior. For example, in position *control mode*, the position filter *input mode* will smooth out `input_pos` commands to give smoother motion. |
| `UNSTABLE_GAIN` | 0x00000004 | `motor.config.bandwidth` was set too high to create a stable controller. |
| `INVALID_ESTIMATE` | 0x00000020 | Indicates the encoder estimation module declined to output a linear position or velocity value and the exception was caught. |
| `INVALID_CIRCULAR_RANGE` | 0x00000040 | Indicates the encoder estimation module declined to output a circular position value and the exception was caught. |
| `SPINOUT_DETECTED` | 0x00000080 | The motor mechanical power and electrical power do not agree. This is usually caused by a slipping encoder or incorrect encoder offset calibration. Check that your encoder is not slipping on the motor. If using an Index pin, check that you are not getting false index pulses caused by noise. This can happen if you are using unshielded cable for the encoder signals. |
| `POS_LIMIT_VIOLATION` (added) | 0x00000100 | XDRIVE: the position went beyond `config.pos_min`/`config.pos_max` by more than `config.pos_limit_margin`.<br>Checked only while armed in closed loop. Entering closed loop outside the limits also raises it. |
| `POS_FOLLOWING_ERROR` (added) | 0x00000200 | XDRIVE: \|pos_setpoint - pos_estimate\| exceeded `config.max_pos_error` (position control).<br>Catches jams, collisions and encoder slip. Checked only while armed in closed loop. |
| `VEL_FOLLOWING_ERROR` (added) | 0x00000400 | XDRIVE: \|vel_setpoint - vel_estimate\| exceeded `config.max_vel_error` (velocity or position control).<br>Checked only while armed in closed loop. |

### Controller.InputMode

Enum.

| Name | Value | Description |
|---|---|---|
| `INACTIVE` | 0 | Disable inputs. Setpoints retain their last value. |
| `PASSTHROUGH` | 1 | Pass `input_xxx` through to `xxx_setpoint` directly.<br>### Valid Inputs: * `input_pos` * `input_vel` * `input_torque`<br>### Valid Control modes: * `CONTROL_MODE_VOLTAGE_CONTROL` * `CONTROL_MODE_TORQUE_CONTROL` * `CONTROL_MODE_VELOCITY_CONTROL` * `CONTROL_MODE_POSITION_CONTROL` |
| `VEL_RAMP` | 2 | Ramps a velocity command from the current value to the target value.<br>### Configuration Values: * `config.vel_ramp_rate` [turn/s] * `config.inertia` [N·m/(turn/s^2))]<br>### Valid inputs: * `input_vel` * `input_torque` (feed-forward, added to the `config.inertia` term)<br>### Valid Control Modes: * `CONTROL_MODE_VELOCITY_CONTROL` |
| `POS_FILTER` | 3 | Implements a 2nd order position tracking filter.<br>Intended for use with step/dir interface, but can also be used with position-only commands.<br>Step response: [Control](control.md#position-filter-3). Result of a step command from 1000 to 0<br>### Configuration Values: * `config.input_filter_bandwidth` * `config.inertia`<br>### Valid inputs: * `input_pos` * `input_torque` (feed-forward, added to the `config.inertia` term)<br>### Valid Control modes: * `CONTROL_MODE_POSITION_CONTROL` |
| `MIX_CHANNELS` | 4 | Not Implemented. |
| `TRAP_TRAJ` | 5 | Implementes an online trapezoidal trajectory planner.<br>A move: [Control](control.md#trapezoidal-trajectory-5).<br>### Configuration Values: * `Axis:trap_traj.config.vel_limit` * `Axis:trap_traj.config.accel_limit` * `Axis:trap_traj.config.decel_limit` * `config.inertia`<br>### Valid Inputs: * `input_pos` * `input_torque` (feed-forward, added to the `config.inertia` term during a move, and applied alone after it)<br>### Valid Control Modes: * `CONTROL_MODE_POSITION_CONTROL` * `CONTROL_MODE_IMPEDANCE_CONTROL` |
| `TORQUE_RAMP` | 6 | Ramp a torque command from the current value to the target value.<br>### Configuration Values: * `config.torque_ramp_rate`<br>### Valid Inputs: * `input_torque`<br>### Valid Control Modes: * `CONTROL_MODE_TORQUE_CONTROL` |
| `TUNING` | 8 | Implements a tuning mode<br>Used for tuning your odrive, this mode allows the user to set different frequencies. Set control_mode for the loop you want to tune, then set the frequency desired. The ODrive will send a 1 turn amplitude sine wave to the controller with the given frequency and phase. |

### Encoder.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `UNSTABLE_GAIN` | 0x00000001 |  |
| `CPR_POLEPAIRS_MISMATCH` | 0x00000002 | Confirm you have entered the correct count per rotation (CPR) for [your encoder](https://docs.odriverobotics.com/encoders). The ODrive uses your supplied value for the motor pole pairs to measure the CPR. So you should also double check this value.<br>If you are still having issues, you can try to increase `config.calib_scan_distance` up to a factor of 4 above the default.<br>If your encoder cpr and motor pole pair settings are correct, this error can be caused because motor cogging makes the motor move less or more than commanded. You can fix this by increasing `config.calib_scan_distance`.<br>Note that the AMT encoders are configurable using the micro- switches on the encoder PCB and so you may need to check that these are in the right positions. If your encoder lists its pulse per rotation (PPR) multiply that number by four to get CPR. |
| `NO_RESPONSE` | 0x00000004 | Confirm that your encoder is plugged into the right pins on the ODrive board. |
| `UNSUPPORTED_ENCODER_MODE` | 0x00000008 |  |
| `ILLEGAL_HALL_STATE` | 0x00000010 | Hall effect encoder only have 6 valid states out of 8 (2^3) possible states. An invalid state can be caused by noise or a hardware fault. If you get this error and you are sure that your electrical connections are correct, add 22nF capacitors between the encoder A,B,Z pins and ground to filter out noise. |
| `INDEX_NOT_FOUND_YET` | 0x00000020 | Check that your encoder is a model that has an index pulse. If your encoder does not have a wire connected to pin Z on your ODrive then it does not output an index pulse. |
| `ABS_SPI_TIMEOUT` | 0x00000040 |  |
| `ABS_SPI_COM_FAIL` | 0x00000080 |  |
| `ABS_SPI_NOT_READY` | 0x00000100 |  |
| `HALL_NOT_CALIBRATED_YET` | 0x00000200 |  |

### Encoder.Mode

Enum.

| Name | Value | Description |
|---|---|---|
| `INCREMENTAL` | 0 |  |
| `HALL` | 1 |  |
| `SINCOS` | 2 |  |
| `SPI_ABS_CUI` | 256 | Compatible with CUI AMT23xx |
| `SPI_ABS_AMS` | 257 | Compatible with AMS AS5047P, AS5048A/AS5048B (no daisy chain support) |
| `SPI_ABS_AEAT` | 258 | Supports AEAT-8800 |
| `SPI_ABS_RLS` | 259 | Supports RLS Orbis Encoders |
| `SPI_ABS_MA732` | 260 | MagAlpha MA732 magnetic encoder |

### Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `CONTROL_ITERATION_MISSED` | 0x00000001 | At least one control iteration was missed.<br>The main control loop is supposed to runs at a fixed frequency. If the device is computationally overloaded (e.g. too many active components) it's possible that one or more control iterations are skipped. |
| `DC_BUS_UNDER_VOLTAGE` | 0x00000002 | The DC voltage fell below the limit configured in `config.dc_bus_undervoltage_trip_level`.<br>Confirm that your power leads are connected securely. For initial testing a 12V PSU which can supply a couple of amps should be sufficient while the use of low current ‘wall wart’ plug packs may lead to inconsistent behaviour and is not recommended.<br>You can monitor your PSU voltage using liveplotter in odrivetool by entering `start_liveplotter(lambda: [odrv0.vbus_voltage])`. If you see your votlage drop below `config.dc_bus_undervoltage_trip_level` (default: ~ 8V) then you will trip this error. Even a relatively small motor can draw multiple kW momentary and so unless you have a very large PSU or are running of a battery you may encounter this error when executing high speed movements with a high current limit. To limit your PSU power draw you can limit your motor current and/or velocity limit `Axis:controller.config.vel_limit` and `Axis:motor.config.current_lim`. |
| `DC_BUS_OVER_VOLTAGE` | 0x00000004 | The DC voltage exceeded the limit configured in `config.dc_bus_overvoltage_trip_level`.<br>Confirm that you have a brake resistor of the correct value connected securely and that `config.brake_resistance` is set to the value of your brake resistor.<br>You can monitor your PSU voltage using liveplotter in odrivetool by entering `start_liveplotter(lambda: [odrv0.vbus_voltage])`. If during a move you see the voltage rise above your PSU’s nominal set voltage then you have your brake resistance set too low. This may happen if you are using long wires or small gauge wires to connect your brake resistor to your odrive which will added extra resistance. This extra resistance needs to be accounted for to prevent this voltage spike. If you have checked all your connections you can also try increasing your brake resistance by ~ 0.01 ohm at a time to a maximum of 0.05 greater than your brake resistor value. |
| `DC_BUS_OVER_REGEN_CURRENT` | 0x00000008 | Current flowing back into the power supply exceeded `config.dc_max_negative_current`. This can happen if your brake resistor is disabled or unable to handle the braking current.<br>Check that `config.enable_brake_resistor` is `True` and that `(V_power_supply / Brake_resistance) > (total motor.config.current_lim + total motor.config.current_lim_margin)`. |
| `DC_BUS_OVER_CURRENT` | 0x00000010 | Too much current was pulled from the power supply. `ibus` exceeded `config.dc_max_positive_current`. |
| `BRAKE_DEADTIME_VIOLATION` | 0x00000020 |  |
| `BRAKE_DUTY_CYCLE_NAN` | 0x00000040 |  |
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
| `UART_B` | 5 | This mode is not supported on ODrive v3.x. |
| `UART_C` | 6 | This mode is not supported on ODrive v3.x. |
| `CAN_A` | 7 | See `config.enable_can_a`. |
| `I2C_A` | 8 | See `config.enable_i2c_a`. |
| `SPI_A` | 9 | Note that the SPI pins on ODrive v3.x are hardwired so they cannot be configured through software. Consequently |
| `PWM` | 10 | See `config.gpio1_pwm_mapping`. |
| `ENC0` | 11 | The pin is used by quadrature encoder 0. |
| `ENC2` | 13 | This mode is not supported on ODrive v3.x. |
| `MECH_BRAKE` | 14 | This is to support external mechanical brakes. |
| `STATUS` | 15 | The pin is used for status output (see `config.error_gpio_pin`) |

### Motor.Error

Bit flags.

| Name | Value | Description |
|---|---|---|
| `PHASE_RESISTANCE_OUT_OF_RANGE` | 0x00000001 | The measured motor phase resistance is outside of the plausible range.<br>During calibration the motor resistance and [inductance](https://en.wikipedia.org/wiki/Inductance) is measured. If the measured motor resistance or inductance falls outside a set range this error will be returned. Check that all motor leads are connected securely.<br>The measured values can be viewed using odrivetool as is shown below: ``` In [2]: odrv0.axis0.motor.config.phase_inductance Out[2]: 1.408751450071577e-05<br>In [3]: odrv0.axis0.motor.config.phase_resistance Out[3]: 0.029788672924041748 ``` Some motors will have a considerably different phase resistance and inductance than this. For example, gimbal motors, some small motors (e.g. < 10A peak current). If you think this applies to you try increasing `config.resistance_calib_max_voltage` from its default value of 1 using odrivetool and repeat the motor calibration process. If your motor has a small peak current draw (e.g. < 20A) you can also try decreasing `config.calibration_current` from its default value of 10A.<br>In general, you need ```text resistance_calib_max_voltage > calibration_current * phase_resistance resistance_calib_max_voltage < 0.5 * vbus_voltage ``` |
| `PHASE_INDUCTANCE_OUT_OF_RANGE` | 0x00000002 | The measured motor phase inductance is outside of the plausible range.<br>See `PHASE_RESISTANCE_OUT_OF_RANGE` for details. |
| `DRV_FAULT` | 0x00000008 | The gate driver chip reported an error.<br>The ODrive v3.4 is known to have a hardware issue whereby the motors would stop operating when applying high currents to M0. The reported error of both motors in this case is `ERROR_DRV_FAULT`.<br>The conjecture is that the high switching current creates large ripples in the power supply of the DRV8301 gate driver chips, thus tripping its under-voltage fault detection.<br>To resolve this issue you can limit the M0 current to 40A. The lowest current at which the DRV fault was observed is 45A on one test motor and 50A on another test motor. Refer to [this post](https://discourse.odriverobotics.com/t/drv-fault-on-odrive-v3-4/558) for instructions for a hardware fix. |
| `CONTROL_DEADLINE_MISSED` | 0x00000010 |  |
| `MODULATION_MAGNITUDE` | 0x00000080 | The bus voltage was insufficent to push the requested current through the motor. If you are getting this during motor calibration, make sure that `config.resistance_calib_max_voltage` is no more than half your bus voltage.<br>For gimbal motors, it is recommended to set the `config.calibration_current` and `config.current_lim` to half your bus voltage, or less. |
| `CURRENT_SENSE_SATURATION` | 0x00000400 | The current sense circuit saturated the current sense amplifier. This can be caused by setting `config.current_lim` higher than `config.requested_current_range`. If this happens, increase the requested current range, save the configuration, and reboot the controller. |
| `CURRENT_LIMIT_VIOLATION` | 0x00001000 | The motor current exceeded `motor.config.current_lim + motor.config.current_lim_margin`. The current controller is a PI controller, so it can experience overshoot. The PI gains are automatically calculated based on `config.current_control_bandwidth` and the motor resistance and inductance (pole placement). Some overshoot is normal, so a sensible solution is to increase the current limit margin if your current limit is large. |
| `MODULATION_IS_NAN` | 0x00010000 |  |
| `MOTOR_THERMISTOR_OVER_TEMP` | 0x00020000 | The motor thermistor measured a temperature above motor.motor_thermistor.config.temp_limit_upper |
| `FET_THERMISTOR_OVER_TEMP` | 0x00040000 | The inverter thermistor measured a temperature above motor.fet_thermistor.config.temp_limit_upper |
| `TIMER_UPDATE_MISSED` | 0x00080000 | A timer update event was missed. Perhaps the previous timer update took too much time. This is not expected in official release firmware. |
| `CURRENT_MEASUREMENT_UNAVAILABLE` | 0x00100000 | The phase current measurement is not available. The ADC failed to sample the current sensor in time. This is not expected in official release firmware. |
| `CONTROLLER_FAILED` | 0x00200000 | The motor was disarmed because the underlying controller failed. Usually this is the FOC controller. |
| `I_BUS_OUT_OF_RANGE` | 0x00400000 | The DC current sourced/sunk by this motor exceeded the configured hard limits. More specifically `I_bus` fell outside of the range `config.I_bus_hard_min` ... `config.I_bus_hard_max`. |
| `BRAKE_RESISTOR_DISARMED` | 0x00800000 | An attempt was made to run the motor PWM while the brake resistor was configured as enabled (`config.enable_brake_resistor`) but disarmed.<br>The most common cause is that you just set `config.enable_brake_resistor` to `True` but didn't arm the brake resistor yet (by either rebooting or running `odrvX.clear_errors()`).<br>Otherwise, the brake resistor can be disarmed due to various system-wide errors. The root cause will usually show up under `system` when you run `dump_errors(odrvX)`.<br>To re-arm the brake resistor reboot the ODrive or run `odrvX.clear_errors()`. |
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
| `UNSTABLE_GAIN` | 0x00000001 |  |
| `UNKNOWN_CURRENT_MEASUREMENT` | 0x00000002 |  |

### StreamProtocolType

Enum.

| Name | Value | Description |
|---|---|---|
| `Fibre` | 0 | Machine-to-machine protocol which gives access to all features of the ODrive. This protocol is used by the official odrivetool and GUI. Developers who wish to interact with this protocol are advised to do so through libfibre. |
| `Ascii` | 1 | Human readable protocol designed for easy implementation for cases where the use of libfibre is not desired or feasible. Refer to [ODrive's ASCII protocol page](https://docs.odriverobotics.com/v/0.5.6/ascii-protocol.html) for details. |
| `Stdout` | 2 | Output of printf(). Only intended for developers who modify ODrive firmware. |
| `AsciiAndStdout` | 3 | Combination of `Ascii` and `Stdout`. |
