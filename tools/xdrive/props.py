# Generated from src/odrive-interface.yaml by `make generate` (tools/gen_props.py); edit the interface file, not this file.

"""Typed names for every object, property and function of the firmware's interface.

`odrv` is the board's root object: `board.get(odrv.axis0.encoder.pos_estimate)` returns a float.
"""
from __future__ import annotations

from xdrive import enums as E
from xdrive.model import Arg, Call, EndpointRef, Func, Prop, RwProp

__all__ = ["odrv"]


class ODrive3_set_adc1_scan(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('enable', bool),), ())

    def __call__(self, enable: bool) -> Call[None]:
        return Call(self, (enable,))


class ODrive3_test_function(Func[int]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('delta', int),), (Arg('cnt', int),))

    def __call__(self, delta: int) -> Call[int]:
        return Call(self, (delta,))


class ODrive3_get_adc_voltage(Func[float]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('gpio', int),), (Arg('voltage', float),))

    def __call__(self, gpio: int) -> Call[float]:
        return Call(self, (gpio,))


class ODrive3_save_configuration(Func[bool]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), (Arg('success', bool),))

    def __call__(self) -> Call[bool]:
        return Call(self, ())


class ODrive3_erase_configuration(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class ODrive3_reboot(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class ODrive3_enter_dfu_mode(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class ODrive3_get_interrupt_status(Func[int]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('irqn', int),), (Arg('status', int),))

    def __call__(self, irqn: int) -> Call[int]:
        return Call(self, (irqn,))


class ODrive3_get_dma_status(Func[int]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('stream_num', int),), (Arg('status', int),))

    def __call__(self, stream_num: int) -> Call[int]:
        return Call(self, (stream_num,))


class ODrive3_get_gpio_states(Func[int]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), (Arg('status', int),))

    def __call__(self) -> Call[int]:
        return Call(self, ())


class ODrive3_get_drv_fault(Func[int]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), (Arg('drv_fault', int),))

    def __call__(self) -> Call[int]:
        return Call(self, ())


class ODrive3_clear_errors(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class ODrive3:
    def __init__(self, p: str) -> None:
        self.error: RwProp[E.ODriveError] = RwProp(p + "error", E.ODriveError)
        self.vbus_voltage: Prop[float] = Prop(p + "vbus_voltage", float)
        self.ibus: Prop[float] = Prop(p + "ibus", float)
        self.ibus_report_filter_k: RwProp[float] = RwProp(p + "ibus_report_filter_k", float)
        self.serial_number: Prop[int] = Prop(p + "serial_number", int)
        self.hw_version_major: Prop[int] = Prop(p + "hw_version_major", int)
        self.hw_version_minor: Prop[int] = Prop(p + "hw_version_minor", int)
        self.hw_version_variant: Prop[int] = Prop(p + "hw_version_variant", int)
        self.fw_version_major: Prop[int] = Prop(p + "fw_version_major", int)
        self.fw_version_minor: Prop[int] = Prop(p + "fw_version_minor", int)
        self.fw_version_revision: Prop[int] = Prop(p + "fw_version_revision", int)
        self.fw_version_unreleased: Prop[int] = Prop(p + "fw_version_unreleased", int)
        self.brake_resistor_armed: Prop[bool] = Prop(p + "brake_resistor_armed", bool)
        self.brake_resistor_saturated: Prop[bool] = Prop(p + "brake_resistor_saturated", bool)
        self.brake_resistor_current: Prop[float] = Prop(p + "brake_resistor_current", float)
        self.n_evt_sampling: Prop[int] = Prop(p + "n_evt_sampling", int)
        self.n_evt_control_loop: Prop[int] = Prop(p + "n_evt_control_loop", int)
        self.task_timers_armed: RwProp[bool] = RwProp(p + "task_timers_armed", bool)
        self.task_times = TaskTimes(p + "task_times.")
        self.system_stats = SystemStats(p + "system_stats.")
        self.user_config_loaded: Prop[int] = Prop(p + "user_config_loaded", int)
        self.misconfigured: Prop[bool] = Prop(p + "misconfigured", bool)
        self.capture = Capture(p + "capture.")
        self.can = Can(p + "can.")
        self.test_property: RwProp[int] = RwProp(p + "test_property", int)
        self.otp_valid: Prop[bool] = Prop(p + "otp_valid", bool)
        self.adc1_scan_enabled: Prop[bool] = Prop(p + "adc1_scan_enabled", bool)
        self.config = ODrive3Config(p + "config.")
        self.axis0 = Axis(p + "axis0.")
        self.set_adc1_scan = ODrive3_set_adc1_scan(p + "set_adc1_scan")
        self.test_function = ODrive3_test_function(p + "test_function")
        self.get_adc_voltage = ODrive3_get_adc_voltage(p + "get_adc_voltage")
        self.save_configuration = ODrive3_save_configuration(p + "save_configuration")
        self.erase_configuration = ODrive3_erase_configuration(p + "erase_configuration")
        self.reboot = ODrive3_reboot(p + "reboot")
        self.enter_dfu_mode = ODrive3_enter_dfu_mode(p + "enter_dfu_mode")
        self.get_interrupt_status = ODrive3_get_interrupt_status(p + "get_interrupt_status")
        self.get_dma_status = ODrive3_get_dma_status(p + "get_dma_status")
        self.get_gpio_states = ODrive3_get_gpio_states(p + "get_gpio_states")
        self.get_drv_fault = ODrive3_get_drv_fault(p + "get_drv_fault")
        self.clear_errors = ODrive3_clear_errors(p + "clear_errors")


class TaskTimes:
    def __init__(self, p: str) -> None:
        self.sampling = TaskTimer(p + "sampling.")
        self.control_loop_misc = TaskTimer(p + "control_loop_misc.")
        self.control_loop_checks = TaskTimer(p + "control_loop_checks.")
        self.dc_calib_wait = TaskTimer(p + "dc_calib_wait.")
        self.capture_update = TaskTimer(p + "capture_update.")


class TaskTimer:
    def __init__(self, p: str) -> None:
        self.start_time: Prop[int] = Prop(p + "start_time", int)
        self.end_time: Prop[int] = Prop(p + "end_time", int)
        self.length: Prop[int] = Prop(p + "length", int)
        self.max_length: RwProp[int] = RwProp(p + "max_length", int)


class SystemStats:
    def __init__(self, p: str) -> None:
        self.uptime: Prop[int] = Prop(p + "uptime", int)
        self.min_heap_space: Prop[int] = Prop(p + "min_heap_space", int)
        self.max_stack_usage_axis: Prop[int] = Prop(p + "max_stack_usage_axis", int)
        self.max_stack_usage_usb: Prop[int] = Prop(p + "max_stack_usage_usb", int)
        self.max_stack_usage_uart: Prop[int] = Prop(p + "max_stack_usage_uart", int)
        self.max_stack_usage_can: Prop[int] = Prop(p + "max_stack_usage_can", int)
        self.max_stack_usage_startup: Prop[int] = Prop(p + "max_stack_usage_startup", int)
        self.max_stack_usage_analog: Prop[int] = Prop(p + "max_stack_usage_analog", int)
        self.stack_size_axis: Prop[int] = Prop(p + "stack_size_axis", int)
        self.stack_size_usb: Prop[int] = Prop(p + "stack_size_usb", int)
        self.stack_size_uart: Prop[int] = Prop(p + "stack_size_uart", int)
        self.stack_size_startup: Prop[int] = Prop(p + "stack_size_startup", int)
        self.stack_size_can: Prop[int] = Prop(p + "stack_size_can", int)
        self.stack_size_analog: Prop[int] = Prop(p + "stack_size_analog", int)
        self.prio_axis: Prop[int] = Prop(p + "prio_axis", int)
        self.prio_usb: Prop[int] = Prop(p + "prio_usb", int)
        self.prio_uart: Prop[int] = Prop(p + "prio_uart", int)
        self.prio_startup: Prop[int] = Prop(p + "prio_startup", int)
        self.prio_can: Prop[int] = Prop(p + "prio_can", int)
        self.prio_analog: Prop[int] = Prop(p + "prio_analog", int)
        self.usb = SystemStatsUsb(p + "usb.")
        self.i2c = SystemStatsI2C(p + "i2c.")


class SystemStatsUsb:
    def __init__(self, p: str) -> None:
        self.rx_cnt: Prop[int] = Prop(p + "rx_cnt", int)
        self.tx_cnt: Prop[int] = Prop(p + "tx_cnt", int)
        self.tx_overrun_cnt: Prop[int] = Prop(p + "tx_overrun_cnt", int)


class SystemStatsI2C:
    def __init__(self, p: str) -> None:
        self.addr: Prop[int] = Prop(p + "addr", int)
        self.addr_match_cnt: Prop[int] = Prop(p + "addr_match_cnt", int)
        self.rx_cnt: Prop[int] = Prop(p + "rx_cnt", int)
        self.error_cnt: Prop[int] = Prop(p + "error_cnt", int)


class Capture_add_channel(Func[bool]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('endpoint_id', int),), (Arg('ok', bool),))

    def __call__(self, endpoint_id: int) -> Call[bool]:
        return Call(self, (endpoint_id,))


class Capture_clear_channels(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class Capture_start(Func[bool]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), (Arg('ok', bool),))

    def __call__(self) -> Call[bool]:
        return Call(self, ())


class Capture_trigger(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class Capture:
    def __init__(self, p: str) -> None:
        self.decimation: RwProp[int] = RwProp(p + "decimation", int)
        self.trigger_mode: RwProp[E.CaptureTrigger] = RwProp(p + "trigger_mode", E.CaptureTrigger)
        self.trigger_channel: RwProp[int] = RwProp(p + "trigger_channel", int)
        self.trigger_level: RwProp[float] = RwProp(p + "trigger_level", float)
        self.post_trigger: RwProp[int] = RwProp(p + "post_trigger", int)
        self.state: Prop[E.CaptureState] = Prop(p + "state", E.CaptureState)
        self.n_channels: Prop[int] = Prop(p + "n_channels", int)
        self.capacity: Prop[int] = Prop(p + "capacity", int)
        self.n_samples: Prop[int] = Prop(p + "n_samples", int)
        self.trigger_index: Prop[int] = Prop(p + "trigger_index", int)
        self.readout_endpoint: Prop[int] = Prop(p + "readout_endpoint", int)
        self.add_channel = Capture_add_channel(p + "add_channel")
        self.clear_channels = Capture_clear_channels(p + "clear_channels")
        self.start = Capture_start(p + "start")
        self.trigger = Capture_trigger(p + "trigger")


class Can:
    def __init__(self, p: str) -> None:
        self.error: RwProp[E.CanError] = RwProp(p + "error", E.CanError)
        self.config = CanConfig(p + "config.")


class CanConfig:
    def __init__(self, p: str) -> None:
        self.baud_rate: RwProp[int] = RwProp(p + "baud_rate", int)
        self.protocol: RwProp[E.CanProtocol] = RwProp(p + "protocol", E.CanProtocol)


class ODrive3Config:
    def __init__(self, p: str) -> None:
        self.enable_uart_a: RwProp[bool] = RwProp(p + "enable_uart_a", bool)
        self.enable_uart_b: RwProp[bool] = RwProp(p + "enable_uart_b", bool)
        self.enable_uart_c: RwProp[bool] = RwProp(p + "enable_uart_c", bool)
        self.uart_a_baudrate: RwProp[int] = RwProp(p + "uart_a_baudrate", int)
        self.uart_b_baudrate: RwProp[int] = RwProp(p + "uart_b_baudrate", int)
        self.uart_c_baudrate: RwProp[int] = RwProp(p + "uart_c_baudrate", int)
        self.enable_can_a: RwProp[bool] = RwProp(p + "enable_can_a", bool)
        self.enable_i2c_a: RwProp[bool] = RwProp(p + "enable_i2c_a", bool)
        self.usb_cdc_protocol: RwProp[E.StreamProtocolType] = RwProp(p + "usb_cdc_protocol", E.StreamProtocolType)
        self.uart0_protocol: RwProp[E.StreamProtocolType] = RwProp(p + "uart0_protocol", E.StreamProtocolType)
        self.uart1_protocol: RwProp[E.StreamProtocolType] = RwProp(p + "uart1_protocol", E.StreamProtocolType)
        self.uart2_protocol: RwProp[E.StreamProtocolType] = RwProp(p + "uart2_protocol", E.StreamProtocolType)
        self.max_regen_current: RwProp[float] = RwProp(p + "max_regen_current", float)
        self.brake_resistance: RwProp[float] = RwProp(p + "brake_resistance", float)
        self.enable_brake_resistor: RwProp[bool] = RwProp(p + "enable_brake_resistor", bool)
        self.dc_bus_undervoltage_trip_level: RwProp[float] = RwProp(p + "dc_bus_undervoltage_trip_level", float)
        self.dc_bus_overvoltage_trip_level: RwProp[float] = RwProp(p + "dc_bus_overvoltage_trip_level", float)
        self.enable_dc_bus_overvoltage_ramp: RwProp[bool] = RwProp(p + "enable_dc_bus_overvoltage_ramp", bool)
        self.dc_bus_overvoltage_ramp_start: RwProp[float] = RwProp(p + "dc_bus_overvoltage_ramp_start", float)
        self.dc_bus_overvoltage_ramp_end: RwProp[float] = RwProp(p + "dc_bus_overvoltage_ramp_end", float)
        self.dc_max_positive_current: RwProp[float] = RwProp(p + "dc_max_positive_current", float)
        self.dc_max_negative_current: RwProp[float] = RwProp(p + "dc_max_negative_current", float)
        self.error_gpio_pin: RwProp[int] = RwProp(p + "error_gpio_pin", int)
        self.gpio3_analog_mapping = Endpoint(p + "gpio3_analog_mapping.")
        self.gpio4_analog_mapping = Endpoint(p + "gpio4_analog_mapping.")
        self.gpio1_mode: RwProp[E.GpioMode] = RwProp(p + "gpio1_mode", E.GpioMode)
        self.gpio2_mode: RwProp[E.GpioMode] = RwProp(p + "gpio2_mode", E.GpioMode)
        self.gpio3_mode: RwProp[E.GpioMode] = RwProp(p + "gpio3_mode", E.GpioMode)
        self.gpio4_mode: RwProp[E.GpioMode] = RwProp(p + "gpio4_mode", E.GpioMode)
        self.gpio5_mode: RwProp[E.GpioMode] = RwProp(p + "gpio5_mode", E.GpioMode)
        self.gpio6_mode: RwProp[E.GpioMode] = RwProp(p + "gpio6_mode", E.GpioMode)
        self.gpio7_mode: RwProp[E.GpioMode] = RwProp(p + "gpio7_mode", E.GpioMode)
        self.gpio8_mode: RwProp[E.GpioMode] = RwProp(p + "gpio8_mode", E.GpioMode)
        self.gpio9_mode: RwProp[E.GpioMode] = RwProp(p + "gpio9_mode", E.GpioMode)
        self.gpio10_mode: RwProp[E.GpioMode] = RwProp(p + "gpio10_mode", E.GpioMode)
        self.gpio11_mode: RwProp[E.GpioMode] = RwProp(p + "gpio11_mode", E.GpioMode)
        self.gpio12_mode: RwProp[E.GpioMode] = RwProp(p + "gpio12_mode", E.GpioMode)
        self.gpio13_mode: RwProp[E.GpioMode] = RwProp(p + "gpio13_mode", E.GpioMode)
        self.gpio14_mode: RwProp[E.GpioMode] = RwProp(p + "gpio14_mode", E.GpioMode)
        self.gpio15_mode: RwProp[E.GpioMode] = RwProp(p + "gpio15_mode", E.GpioMode)
        self.gpio16_mode: RwProp[E.GpioMode] = RwProp(p + "gpio16_mode", E.GpioMode)
        self.gpio1_pwm_mapping = Endpoint(p + "gpio1_pwm_mapping.")
        self.gpio2_pwm_mapping = Endpoint(p + "gpio2_pwm_mapping.")
        self.gpio3_pwm_mapping = Endpoint(p + "gpio3_pwm_mapping.")
        self.gpio4_pwm_mapping = Endpoint(p + "gpio4_pwm_mapping.")


class Endpoint:
    def __init__(self, p: str) -> None:
        self.endpoint: RwProp[EndpointRef] = RwProp(p + "endpoint", EndpointRef)
        self.min: RwProp[float] = RwProp(p + "min", float)
        self.max: RwProp[float] = RwProp(p + "max", float)


class Axis_watchdog_feed(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class Axis:
    def __init__(self, p: str) -> None:
        self.error: RwProp[E.AxisError] = RwProp(p + "error", E.AxisError)
        self.step_dir_active: Prop[bool] = Prop(p + "step_dir_active", bool)
        self.last_drv_fault: Prop[int] = Prop(p + "last_drv_fault", int)
        self.steps: Prop[int] = Prop(p + "steps", int)
        self.current_state: Prop[E.AxisState] = Prop(p + "current_state", E.AxisState)
        self.requested_state: RwProp[E.AxisState] = RwProp(p + "requested_state", E.AxisState)
        self.is_homed: RwProp[bool] = RwProp(p + "is_homed", bool)
        self.config = AxisConfig(p + "config.")
        self.motor = Motor(p + "motor.")
        self.controller = Controller(p + "controller.")
        self.encoder = Encoder(p + "encoder.")
        self.acim_estimator = AcimEstimator(p + "acim_estimator.")
        self.sensorless_estimator = SensorlessEstimator(p + "sensorless_estimator.")
        self.trap_traj = TrapezoidalTrajectory(p + "trap_traj.")
        self.min_endstop = Endstop(p + "min_endstop.")
        self.max_endstop = Endstop(p + "max_endstop.")
        self.mechanical_brake = MechanicalBrake(p + "mechanical_brake.")
        self.task_times = AxisTaskTimes(p + "task_times.")
        self.watchdog_feed = Axis_watchdog_feed(p + "watchdog_feed")


class AxisConfig:
    def __init__(self, p: str) -> None:
        self.startup_motor_calibration: RwProp[bool] = RwProp(p + "startup_motor_calibration", bool)
        self.startup_encoder_index_search: RwProp[bool] = RwProp(p + "startup_encoder_index_search", bool)
        self.startup_encoder_offset_calibration: RwProp[bool] = RwProp(p + "startup_encoder_offset_calibration", bool)
        self.startup_closed_loop_control: RwProp[bool] = RwProp(p + "startup_closed_loop_control", bool)
        self.startup_homing: RwProp[bool] = RwProp(p + "startup_homing", bool)
        self.enable_step_dir: RwProp[bool] = RwProp(p + "enable_step_dir", bool)
        self.step_dir_always_on: RwProp[bool] = RwProp(p + "step_dir_always_on", bool)
        self.enable_sensorless_mode: RwProp[bool] = RwProp(p + "enable_sensorless_mode", bool)
        self.watchdog_timeout: RwProp[float] = RwProp(p + "watchdog_timeout", float)
        self.enable_watchdog: RwProp[bool] = RwProp(p + "enable_watchdog", bool)
        self.watchdog_action: RwProp[E.WatchdogAction] = RwProp(p + "watchdog_action", E.WatchdogAction)
        self.watchdog_decel: RwProp[float] = RwProp(p + "watchdog_decel", float)
        self.watchdog_torque_lim: RwProp[float] = RwProp(p + "watchdog_torque_lim", float)
        self.step_gpio_pin: RwProp[int] = RwProp(p + "step_gpio_pin", int)
        self.dir_gpio_pin: RwProp[int] = RwProp(p + "dir_gpio_pin", int)
        self.calibration_lockin = AxisConfigCalibrationLockin(p + "calibration_lockin.")
        self.sensorless_ramp = AxisLockinConfig(p + "sensorless_ramp.")
        self.general_lockin = AxisLockinConfig(p + "general_lockin.")
        self.can = AxisCanConfig(p + "can.")


class AxisConfigCalibrationLockin:
    def __init__(self, p: str) -> None:
        self.current: RwProp[float] = RwProp(p + "current", float)
        self.ramp_time: RwProp[float] = RwProp(p + "ramp_time", float)
        self.ramp_distance: RwProp[float] = RwProp(p + "ramp_distance", float)
        self.accel: RwProp[float] = RwProp(p + "accel", float)
        self.vel: RwProp[float] = RwProp(p + "vel", float)


class AxisLockinConfig:
    def __init__(self, p: str) -> None:
        self.current: RwProp[float] = RwProp(p + "current", float)
        self.ramp_time: RwProp[float] = RwProp(p + "ramp_time", float)
        self.ramp_distance: RwProp[float] = RwProp(p + "ramp_distance", float)
        self.accel: RwProp[float] = RwProp(p + "accel", float)
        self.vel: RwProp[float] = RwProp(p + "vel", float)
        self.finish_distance: RwProp[float] = RwProp(p + "finish_distance", float)
        self.finish_on_vel: RwProp[bool] = RwProp(p + "finish_on_vel", bool)
        self.finish_on_distance: RwProp[bool] = RwProp(p + "finish_on_distance", bool)
        self.finish_on_enc_idx: RwProp[bool] = RwProp(p + "finish_on_enc_idx", bool)


class AxisCanConfig:
    def __init__(self, p: str) -> None:
        self.node_id: RwProp[int] = RwProp(p + "node_id", int)
        self.is_extended: RwProp[bool] = RwProp(p + "is_extended", bool)
        self.heartbeat_rate_ms: RwProp[int] = RwProp(p + "heartbeat_rate_ms", int)
        self.encoder_rate_ms: RwProp[int] = RwProp(p + "encoder_rate_ms", int)
        self.motor_error_rate_ms: RwProp[int] = RwProp(p + "motor_error_rate_ms", int)
        self.encoder_error_rate_ms: RwProp[int] = RwProp(p + "encoder_error_rate_ms", int)
        self.controller_error_rate_ms: RwProp[int] = RwProp(p + "controller_error_rate_ms", int)
        self.sensorless_error_rate_ms: RwProp[int] = RwProp(p + "sensorless_error_rate_ms", int)
        self.encoder_count_rate_ms: RwProp[int] = RwProp(p + "encoder_count_rate_ms", int)
        self.iq_rate_ms: RwProp[int] = RwProp(p + "iq_rate_ms", int)
        self.sensorless_rate_ms: RwProp[int] = RwProp(p + "sensorless_rate_ms", int)
        self.bus_vi_rate_ms: RwProp[int] = RwProp(p + "bus_vi_rate_ms", int)
        self.impedance_pos_range: RwProp[float] = RwProp(p + "impedance_pos_range", float)
        self.impedance_vel_range: RwProp[float] = RwProp(p + "impedance_vel_range", float)
        self.impedance_kp_max: RwProp[float] = RwProp(p + "impedance_kp_max", float)
        self.impedance_kd_max: RwProp[float] = RwProp(p + "impedance_kd_max", float)
        self.impedance_torque_range: RwProp[float] = RwProp(p + "impedance_torque_range", float)


class Motor_get_spike_n(Func[int]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('index', int),), (Arg('n', int),))

    def __call__(self, index: int) -> Call[int]:
        return Call(self, (index,))


class Motor_get_spike_db(Func[float]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('index', int),), (Arg('val', float),))

    def __call__(self, index: int) -> Call[float]:
        return Call(self, (index,))


class Motor_get_spike_dc(Func[float]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('index', int),), (Arg('val', float),))

    def __call__(self, index: int) -> Call[float]:
        return Call(self, (index,))


class Motor:
    def __init__(self, p: str) -> None:
        self.last_error_time: RwProp[float] = RwProp(p + "last_error_time", float)
        self.error: RwProp[E.MotorError] = RwProp(p + "error", E.MotorError)
        self.is_armed: Prop[bool] = Prop(p + "is_armed", bool)
        self.is_calibrated: Prop[bool] = Prop(p + "is_calibrated", bool)
        self.current_meas_phA: Prop[float] = Prop(p + "current_meas_phA", float)
        self.current_meas_phB: Prop[float] = Prop(p + "current_meas_phB", float)
        self.current_meas_phC: Prop[float] = Prop(p + "current_meas_phC", float)
        self.DC_calib_phA: RwProp[float] = RwProp(p + "DC_calib_phA", float)
        self.DC_calib_phB: RwProp[float] = RwProp(p + "DC_calib_phB", float)
        self.DC_calib_phC: RwProp[float] = RwProp(p + "DC_calib_phC", float)
        self.I_bus: Prop[float] = Prop(p + "I_bus", float)
        self.phase_current_rev_gain: RwProp[float] = RwProp(p + "phase_current_rev_gain", float)
        self.effective_current_lim: Prop[float] = Prop(p + "effective_current_lim", float)
        self.max_allowed_current: Prop[float] = Prop(p + "max_allowed_current", float)
        self.max_dc_calib: Prop[float] = Prop(p + "max_dc_calib", float)
        self.fet_thermistor = OnboardThermistorCurrentLimiter(p + "fet_thermistor.")
        self.motor_thermistor = OffboardThermistorCurrentLimiter(p + "motor_thermistor.")
        self.current_control = MotorCurrentControl(p + "current_control.")
        self.n_evt_current_measurement: Prop[int] = Prop(p + "n_evt_current_measurement", int)
        self.n_evt_pwm_update: Prop[int] = Prop(p + "n_evt_pwm_update", int)
        self.spike_count: Prop[int] = Prop(p + "spike_count", int)
        self.spike_threshold: RwProp[float] = RwProp(p + "spike_threshold", float)
        self.config = MotorConfig(p + "config.")
        self.get_spike_n = Motor_get_spike_n(p + "get_spike_n")
        self.get_spike_db = Motor_get_spike_db(p + "get_spike_db")
        self.get_spike_dc = Motor_get_spike_dc(p + "get_spike_dc")


class OnboardThermistorCurrentLimiter:
    def __init__(self, p: str) -> None:
        self.temperature: Prop[float] = Prop(p + "temperature", float)
        self.config = OnboardThermistorCurrentLimiterConfig(p + "config.")


class OnboardThermistorCurrentLimiterConfig:
    def __init__(self, p: str) -> None:
        self.temp_limit_lower: RwProp[float] = RwProp(p + "temp_limit_lower", float)
        self.temp_limit_upper: RwProp[float] = RwProp(p + "temp_limit_upper", float)
        self.enabled: RwProp[bool] = RwProp(p + "enabled", bool)


class OffboardThermistorCurrentLimiter:
    def __init__(self, p: str) -> None:
        self.temperature: Prop[float] = Prop(p + "temperature", float)
        self.config = OffboardThermistorCurrentLimiterConfig(p + "config.")


class OffboardThermistorCurrentLimiterConfig:
    def __init__(self, p: str) -> None:
        self.gpio_pin: RwProp[int] = RwProp(p + "gpio_pin", int)
        self.poly_coefficient_0: RwProp[float] = RwProp(p + "poly_coefficient_0", float)
        self.poly_coefficient_1: RwProp[float] = RwProp(p + "poly_coefficient_1", float)
        self.poly_coefficient_2: RwProp[float] = RwProp(p + "poly_coefficient_2", float)
        self.poly_coefficient_3: RwProp[float] = RwProp(p + "poly_coefficient_3", float)
        self.temp_limit_lower: RwProp[float] = RwProp(p + "temp_limit_lower", float)
        self.temp_limit_upper: RwProp[float] = RwProp(p + "temp_limit_upper", float)
        self.enabled: RwProp[bool] = RwProp(p + "enabled", bool)


class MotorCurrentControl:
    def __init__(self, p: str) -> None:
        self.p_gain: Prop[float] = Prop(p + "p_gain", float)
        self.i_gain: Prop[float] = Prop(p + "i_gain", float)
        self.I_measured_report_filter_k: RwProp[float] = RwProp(p + "I_measured_report_filter_k", float)
        self.Id_setpoint: Prop[float] = Prop(p + "Id_setpoint", float)
        self.Iq_setpoint: Prop[float] = Prop(p + "Iq_setpoint", float)
        self.Vd_setpoint: Prop[float] = Prop(p + "Vd_setpoint", float)
        self.Vq_setpoint: Prop[float] = Prop(p + "Vq_setpoint", float)
        self.phase: Prop[float] = Prop(p + "phase", float)
        self.phase_vel: Prop[float] = Prop(p + "phase_vel", float)
        self.Ialpha_measured: Prop[float] = Prop(p + "Ialpha_measured", float)
        self.Ibeta_measured: Prop[float] = Prop(p + "Ibeta_measured", float)
        self.Id_measured: Prop[float] = Prop(p + "Id_measured", float)
        self.Iq_measured: Prop[float] = Prop(p + "Iq_measured", float)
        self.power: Prop[float] = Prop(p + "power", float)
        self.v_current_control_integral_d: RwProp[float] = RwProp(p + "v_current_control_integral_d", float)
        self.v_current_control_integral_q: RwProp[float] = RwProp(p + "v_current_control_integral_q", float)
        self.final_v_alpha: Prop[float] = Prop(p + "final_v_alpha", float)
        self.final_v_beta: Prop[float] = Prop(p + "final_v_beta", float)


class MotorConfig:
    def __init__(self, p: str) -> None:
        self.pre_calibrated: RwProp[bool] = RwProp(p + "pre_calibrated", bool)
        self.pole_pairs: RwProp[int] = RwProp(p + "pole_pairs", int)
        self.calibration_current: RwProp[float] = RwProp(p + "calibration_current", float)
        self.resistance_calib_max_voltage: RwProp[float] = RwProp(p + "resistance_calib_max_voltage", float)
        self.phase_inductance: RwProp[float] = RwProp(p + "phase_inductance", float)
        self.phase_resistance: RwProp[float] = RwProp(p + "phase_resistance", float)
        self.torque_constant: RwProp[float] = RwProp(p + "torque_constant", float)
        self.motor_type: RwProp[E.MotorType] = RwProp(p + "motor_type", E.MotorType)
        self.current_lim: RwProp[float] = RwProp(p + "current_lim", float)
        self.current_lim_margin: RwProp[float] = RwProp(p + "current_lim_margin", float)
        self.torque_lim: RwProp[float] = RwProp(p + "torque_lim", float)
        self.inverter_temp_limit_lower: RwProp[float] = RwProp(p + "inverter_temp_limit_lower", float)
        self.inverter_temp_limit_upper: RwProp[float] = RwProp(p + "inverter_temp_limit_upper", float)
        self.requested_current_range: RwProp[float] = RwProp(p + "requested_current_range", float)
        self.current_control_bandwidth: RwProp[float] = RwProp(p + "current_control_bandwidth", float)
        self.acim_gain_min_flux: RwProp[float] = RwProp(p + "acim_gain_min_flux", float)
        self.acim_autoflux_min_Id: RwProp[float] = RwProp(p + "acim_autoflux_min_Id", float)
        self.acim_autoflux_enable: RwProp[bool] = RwProp(p + "acim_autoflux_enable", bool)
        self.acim_autoflux_attack_gain: RwProp[float] = RwProp(p + "acim_autoflux_attack_gain", float)
        self.acim_autoflux_decay_gain: RwProp[float] = RwProp(p + "acim_autoflux_decay_gain", float)
        self.R_wL_FF_enable: RwProp[bool] = RwProp(p + "R_wL_FF_enable", bool)
        self.bEMF_FF_enable: RwProp[bool] = RwProp(p + "bEMF_FF_enable", bool)
        self.I_bus_hard_min: RwProp[float] = RwProp(p + "I_bus_hard_min", float)
        self.I_bus_hard_max: RwProp[float] = RwProp(p + "I_bus_hard_max", float)
        self.I_bus_soft_min: RwProp[float] = RwProp(p + "I_bus_soft_min", float)
        self.I_bus_soft_max: RwProp[float] = RwProp(p + "I_bus_soft_max", float)
        self.flux_brake_start_voltage: RwProp[float] = RwProp(p + "flux_brake_start_voltage", float)
        self.flux_brake_gain: RwProp[float] = RwProp(p + "flux_brake_gain", float)
        self.I_leak_max: RwProp[float] = RwProp(p + "I_leak_max", float)
        self.dc_calib_tau: RwProp[float] = RwProp(p + "dc_calib_tau", float)


class Controller_move_incremental(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('displacement', float), Arg('from_input_pos', bool)), ())

    def __call__(self, displacement: float, from_input_pos: bool) -> Call[None]:
        return Call(self, (displacement, from_input_pos))


class Controller_start_anticogging_calibration(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class Controller_remove_anticogging_bias(Func[float]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), (Arg('val', float),))

    def __call__(self) -> Call[float]:
        return Call(self, ())


class Controller_get_anticogging_value(Func[float]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('index', int),), (Arg('val', float),))

    def __call__(self, index: int) -> Call[float]:
        return Call(self, (index,))


class Controller:
    def __init__(self, p: str) -> None:
        self.error: RwProp[E.ControllerError] = RwProp(p + "error", E.ControllerError)
        self.last_error_time: RwProp[float] = RwProp(p + "last_error_time", float)
        self.input_pos: RwProp[float] = RwProp(p + "input_pos", float)
        self.input_vel: RwProp[float] = RwProp(p + "input_vel", float)
        self.input_torque: RwProp[float] = RwProp(p + "input_torque", float)
        self.input_kp: RwProp[float] = RwProp(p + "input_kp", float)
        self.input_kd: RwProp[float] = RwProp(p + "input_kd", float)
        self.pos_setpoint: Prop[float] = Prop(p + "pos_setpoint", float)
        self.vel_setpoint: Prop[float] = Prop(p + "vel_setpoint", float)
        self.torque_setpoint: Prop[float] = Prop(p + "torque_setpoint", float)
        self.trajectory_done: Prop[bool] = Prop(p + "trajectory_done", bool)
        self.timeout_active: Prop[bool] = Prop(p + "timeout_active", bool)
        self.vel_integrator_torque: RwProp[float] = RwProp(p + "vel_integrator_torque", float)
        self.anticogging_valid: RwProp[bool] = RwProp(p + "anticogging_valid", bool)
        self.autotuning_phase: RwProp[float] = RwProp(p + "autotuning_phase", float)
        self.config = ControllerConfig(p + "config.")
        self.autotuning = ControllerAutotuning(p + "autotuning.")
        self.mechanical_power: Prop[float] = Prop(p + "mechanical_power", float)
        self.electrical_power: Prop[float] = Prop(p + "electrical_power", float)
        self.move_incremental = Controller_move_incremental(p + "move_incremental")
        self.start_anticogging_calibration = Controller_start_anticogging_calibration(p + "start_anticogging_calibration")
        self.remove_anticogging_bias = Controller_remove_anticogging_bias(p + "remove_anticogging_bias")
        self.get_anticogging_value = Controller_get_anticogging_value(p + "get_anticogging_value")


class ControllerConfig:
    def __init__(self, p: str) -> None:
        self.gain_scheduling_width: RwProp[float] = RwProp(p + "gain_scheduling_width", float)
        self.enable_vel_limit: RwProp[bool] = RwProp(p + "enable_vel_limit", bool)
        self.enable_torque_mode_vel_limit: RwProp[bool] = RwProp(p + "enable_torque_mode_vel_limit", bool)
        self.enable_gain_scheduling: RwProp[bool] = RwProp(p + "enable_gain_scheduling", bool)
        self.enable_overspeed_error: RwProp[bool] = RwProp(p + "enable_overspeed_error", bool)
        self.control_mode: RwProp[E.ControlMode] = RwProp(p + "control_mode", E.ControlMode)
        self.input_mode: RwProp[E.InputMode] = RwProp(p + "input_mode", E.InputMode)
        self.pos_gain: RwProp[float] = RwProp(p + "pos_gain", float)
        self.vel_gain: RwProp[float] = RwProp(p + "vel_gain", float)
        self.vel_integrator_gain: RwProp[float] = RwProp(p + "vel_integrator_gain", float)
        self.vel_integrator_limit: RwProp[float] = RwProp(p + "vel_integrator_limit", float)
        self.vel_limit: RwProp[float] = RwProp(p + "vel_limit", float)
        self.vel_limit_tolerance: RwProp[float] = RwProp(p + "vel_limit_tolerance", float)
        self.vel_ramp_rate: RwProp[float] = RwProp(p + "vel_ramp_rate", float)
        self.torque_ramp_rate: RwProp[float] = RwProp(p + "torque_ramp_rate", float)
        self.circular_setpoints: RwProp[bool] = RwProp(p + "circular_setpoints", bool)
        self.circular_setpoint_range: RwProp[float] = RwProp(p + "circular_setpoint_range", float)
        self.steps_per_circular_range: RwProp[int] = RwProp(p + "steps_per_circular_range", int)
        self.homing_speed: RwProp[float] = RwProp(p + "homing_speed", float)
        self.inertia: RwProp[float] = RwProp(p + "inertia", float)
        self.input_filter_bandwidth: RwProp[float] = RwProp(p + "input_filter_bandwidth", float)
        self.anticogging = ControllerConfigAnticogging(p + "anticogging.")
        self.mechanical_power_bandwidth: RwProp[float] = RwProp(p + "mechanical_power_bandwidth", float)
        self.electrical_power_bandwidth: RwProp[float] = RwProp(p + "electrical_power_bandwidth", float)
        self.spinout_mechanical_power_threshold: RwProp[float] = RwProp(p + "spinout_mechanical_power_threshold", float)
        self.spinout_electrical_power_threshold: RwProp[float] = RwProp(p + "spinout_electrical_power_threshold", float)
        self.pos_min: RwProp[float] = RwProp(p + "pos_min", float)
        self.pos_max: RwProp[float] = RwProp(p + "pos_max", float)
        self.pos_limit_margin: RwProp[float] = RwProp(p + "pos_limit_margin", float)
        self.max_pos_error: RwProp[float] = RwProp(p + "max_pos_error", float)
        self.max_vel_error: RwProp[float] = RwProp(p + "max_vel_error", float)


class ControllerConfigAnticogging:
    def __init__(self, p: str) -> None:
        self.index: Prop[int] = Prop(p + "index", int)
        self.pre_calibrated: RwProp[bool] = RwProp(p + "pre_calibrated", bool)
        self.calib_anticogging: Prop[bool] = Prop(p + "calib_anticogging", bool)
        self.calib_pos_threshold: RwProp[float] = RwProp(p + "calib_pos_threshold", float)
        self.calib_vel_threshold: RwProp[float] = RwProp(p + "calib_vel_threshold", float)
        self.cogging_ratio: Prop[float] = Prop(p + "cogging_ratio", float)
        self.anticogging_enabled: RwProp[bool] = RwProp(p + "anticogging_enabled", bool)


class ControllerAutotuning:
    def __init__(self, p: str) -> None:
        self.frequency: RwProp[float] = RwProp(p + "frequency", float)
        self.pos_amplitude: RwProp[float] = RwProp(p + "pos_amplitude", float)
        self.vel_amplitude: RwProp[float] = RwProp(p + "vel_amplitude", float)
        self.torque_amplitude: RwProp[float] = RwProp(p + "torque_amplitude", float)


class Encoder_set_linear_count(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('count', int),), ())

    def __call__(self, count: int) -> Call[None]:
        return Call(self, (count,))


class Encoder_get_correction(Func[float]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('index', int),), (Arg('val', float),))

    def __call__(self, index: int) -> Call[float]:
        return Call(self, (index,))


class Encoder_set_correction(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (Arg('index', int), Arg('val', float)), ())

    def __call__(self, index: int, val: float) -> Call[None]:
        return Call(self, (index, val))


class Encoder:
    def __init__(self, p: str) -> None:
        self.error: RwProp[E.EncoderError] = RwProp(p + "error", E.EncoderError)
        self.is_ready: Prop[bool] = Prop(p + "is_ready", bool)
        self.index_found: Prop[bool] = Prop(p + "index_found", bool)
        self.shadow_count: Prop[int] = Prop(p + "shadow_count", int)
        self.count_in_cpr: Prop[int] = Prop(p + "count_in_cpr", int)
        self.interpolation: Prop[float] = Prop(p + "interpolation", float)
        self.phase: Prop[float] = Prop(p + "phase", float)
        self.pos_estimate: Prop[float] = Prop(p + "pos_estimate", float)
        self.pos_estimate_counts: Prop[float] = Prop(p + "pos_estimate_counts", float)
        self.pos_circular: Prop[float] = Prop(p + "pos_circular", float)
        self.pos_cpr_counts: Prop[float] = Prop(p + "pos_cpr_counts", float)
        self.delta_pos_cpr_counts: Prop[float] = Prop(p + "delta_pos_cpr_counts", float)
        self.hall_state: Prop[int] = Prop(p + "hall_state", int)
        self.vel_estimate: Prop[float] = Prop(p + "vel_estimate", float)
        self.vel_estimate_counts: Prop[float] = Prop(p + "vel_estimate_counts", float)
        self.calib_scan_response: Prop[float] = Prop(p + "calib_scan_response", float)
        self.pos_abs: RwProp[int] = RwProp(p + "pos_abs", int)
        self.spi_error_rate: Prop[float] = Prop(p + "spi_error_rate", float)
        self.spi_frame_count: Prop[int] = Prop(p + "spi_frame_count", int)
        self.spi_error_flag_count: Prop[int] = Prop(p + "spi_error_flag_count", int)
        self.spi_warning_flag_count: Prop[int] = Prop(p + "spi_warning_flag_count", int)
        self.spi_jump_count: Prop[int] = Prop(p + "spi_jump_count", int)
        self.spi_last_frame: Prop[int] = Prop(p + "spi_last_frame", int)
        self.spi_parity_error_count: Prop[int] = Prop(p + "spi_parity_error_count", int)
        self.pos_abs_raw: Prop[int] = Prop(p + "pos_abs_raw", int)
        self.correction_rms: Prop[float] = Prop(p + "correction_rms", float)
        self.correction_peak: Prop[float] = Prop(p + "correction_peak", float)
        self.correction_bins: Prop[int] = Prop(p + "correction_bins", int)
        self.config = EncoderConfig(p + "config.")
        self.set_linear_count = Encoder_set_linear_count(p + "set_linear_count")
        self.get_correction = Encoder_get_correction(p + "get_correction")
        self.set_correction = Encoder_set_correction(p + "set_correction")


class EncoderConfig:
    def __init__(self, p: str) -> None:
        self.mode: RwProp[E.EncoderMode] = RwProp(p + "mode", E.EncoderMode)
        self.use_index: RwProp[bool] = RwProp(p + "use_index", bool)
        self.index_offset: RwProp[float] = RwProp(p + "index_offset", float)
        self.use_index_offset: RwProp[bool] = RwProp(p + "use_index_offset", bool)
        self.find_idx_on_lockin_only: RwProp[bool] = RwProp(p + "find_idx_on_lockin_only", bool)
        self.abs_spi_cs_gpio_pin: RwProp[int] = RwProp(p + "abs_spi_cs_gpio_pin", int)
        self.abs_spi_max_jump: RwProp[int] = RwProp(p + "abs_spi_max_jump", int)
        self.correction_enabled: RwProp[bool] = RwProp(p + "correction_enabled", bool)
        self.correction_scan_turns: RwProp[float] = RwProp(p + "correction_scan_turns", float)
        self.correction_max_harmonic: RwProp[int] = RwProp(p + "correction_max_harmonic", int)
        self.abs_spi_check_parity: RwProp[bool] = RwProp(p + "abs_spi_check_parity", bool)
        self.abs_spi_reject_error_flag: RwProp[bool] = RwProp(p + "abs_spi_reject_error_flag", bool)
        self.cpr: RwProp[int] = RwProp(p + "cpr", int)
        self.phase_offset: RwProp[int] = RwProp(p + "phase_offset", int)
        self.phase_offset_float: RwProp[float] = RwProp(p + "phase_offset_float", float)
        self.direction: RwProp[int] = RwProp(p + "direction", int)
        self.pre_calibrated: RwProp[bool] = RwProp(p + "pre_calibrated", bool)
        self.enable_phase_interpolation: RwProp[bool] = RwProp(p + "enable_phase_interpolation", bool)
        self.bandwidth: RwProp[float] = RwProp(p + "bandwidth", float)
        self.calib_range: RwProp[float] = RwProp(p + "calib_range", float)
        self.calib_scan_distance: RwProp[float] = RwProp(p + "calib_scan_distance", float)
        self.calib_scan_omega: RwProp[float] = RwProp(p + "calib_scan_omega", float)
        self.ignore_illegal_hall_state: RwProp[bool] = RwProp(p + "ignore_illegal_hall_state", bool)
        self.hall_polarity: RwProp[int] = RwProp(p + "hall_polarity", int)
        self.hall_polarity_calibrated: RwProp[bool] = RwProp(p + "hall_polarity_calibrated", bool)
        self.sincos_gpio_pin_sin: RwProp[int] = RwProp(p + "sincos_gpio_pin_sin", int)
        self.sincos_gpio_pin_cos: RwProp[int] = RwProp(p + "sincos_gpio_pin_cos", int)


class AcimEstimator:
    def __init__(self, p: str) -> None:
        self.rotor_flux: Prop[float] = Prop(p + "rotor_flux", float)
        self.slip_vel: Prop[float] = Prop(p + "slip_vel", float)
        self.phase_offset: Prop[float] = Prop(p + "phase_offset", float)
        self.stator_phase_vel: Prop[float] = Prop(p + "stator_phase_vel", float)
        self.stator_phase: Prop[float] = Prop(p + "stator_phase", float)
        self.config = AcimEstimatorConfig(p + "config.")


class AcimEstimatorConfig:
    def __init__(self, p: str) -> None:
        self.slip_velocity: RwProp[float] = RwProp(p + "slip_velocity", float)


class SensorlessEstimator:
    def __init__(self, p: str) -> None:
        self.error: RwProp[E.SensorlessEstimatorError] = RwProp(p + "error", E.SensorlessEstimatorError)
        self.phase: Prop[float] = Prop(p + "phase", float)
        self.pll_pos: Prop[float] = Prop(p + "pll_pos", float)
        self.phase_vel: Prop[float] = Prop(p + "phase_vel", float)
        self.vel_estimate: Prop[float] = Prop(p + "vel_estimate", float)
        self.config = SensorlessEstimatorConfig(p + "config.")


class SensorlessEstimatorConfig:
    def __init__(self, p: str) -> None:
        self.observer_gain: RwProp[float] = RwProp(p + "observer_gain", float)
        self.pll_bandwidth: RwProp[float] = RwProp(p + "pll_bandwidth", float)
        self.pm_flux_linkage: RwProp[float] = RwProp(p + "pm_flux_linkage", float)


class TrapezoidalTrajectory:
    def __init__(self, p: str) -> None:
        self.config = TrapezoidalTrajectoryConfig(p + "config.")


class TrapezoidalTrajectoryConfig:
    def __init__(self, p: str) -> None:
        self.vel_limit: RwProp[float] = RwProp(p + "vel_limit", float)
        self.accel_limit: RwProp[float] = RwProp(p + "accel_limit", float)
        self.decel_limit: RwProp[float] = RwProp(p + "decel_limit", float)


class Endstop:
    def __init__(self, p: str) -> None:
        self.endstop_state: Prop[bool] = Prop(p + "endstop_state", bool)
        self.config = EndstopConfig(p + "config.")


class EndstopConfig:
    def __init__(self, p: str) -> None:
        self.gpio_num: RwProp[int] = RwProp(p + "gpio_num", int)
        self.enabled: RwProp[bool] = RwProp(p + "enabled", bool)
        self.offset: RwProp[float] = RwProp(p + "offset", float)
        self.is_active_high: RwProp[bool] = RwProp(p + "is_active_high", bool)
        self.debounce_ms: RwProp[int] = RwProp(p + "debounce_ms", int)


class MechanicalBrake_engage(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class MechanicalBrake_release(Func[None]):
    def __init__(self, path: str) -> None:
        super().__init__(path, (), ())

    def __call__(self) -> Call[None]:
        return Call(self, ())


class MechanicalBrake:
    def __init__(self, p: str) -> None:
        self.config = MechanicalBrakeConfig(p + "config.")
        self.engage = MechanicalBrake_engage(p + "engage")
        self.release = MechanicalBrake_release(p + "release")


class MechanicalBrakeConfig:
    def __init__(self, p: str) -> None:
        self.gpio_num: RwProp[int] = RwProp(p + "gpio_num", int)
        self.is_active_low: RwProp[bool] = RwProp(p + "is_active_low", bool)


class AxisTaskTimes:
    def __init__(self, p: str) -> None:
        self.thermistor_update = TaskTimer(p + "thermistor_update.")
        self.encoder_update = TaskTimer(p + "encoder_update.")
        self.sensorless_estimator_update = TaskTimer(p + "sensorless_estimator_update.")
        self.endstop_update = TaskTimer(p + "endstop_update.")
        self.can_heartbeat = TaskTimer(p + "can_heartbeat.")
        self.controller_update = TaskTimer(p + "controller_update.")
        self.open_loop_controller_update = TaskTimer(p + "open_loop_controller_update.")
        self.acim_estimator_update = TaskTimer(p + "acim_estimator_update.")
        self.motor_update = TaskTimer(p + "motor_update.")
        self.current_controller_update = TaskTimer(p + "current_controller_update.")
        self.dc_calib = TaskTimer(p + "dc_calib.")
        self.current_sense = TaskTimer(p + "current_sense.")
        self.pwm_update = TaskTimer(p + "pwm_update.")


odrv = ODrive3("")
