# Source files and include dirs for board v3.6-56V (XDRIVE Mini), transcribed from ODrive v0.5.6's
# Firmware/Tupfile.lua and fibre-cpp/package.lua (packages in the order Tupfile.lua adds them; see
# the tag upstream/fw-v0.5.6). Paths are relative to src/.

# board_v3 (+ its stm32f4xx_hal package)
BOARD_SRCS := \
	Board/v3/startup_stm32f405xx.s \
	ThirdParty/FreeRTOS/Source/portable/GCC/ARM_CM4F/port.c \
	Drivers/DRV8301/drv8301.cpp \
	Board/v3/board.cpp \
	Board/v3/Src/stm32f4xx_hal_timebase_TIM.c \
	Board/v3/Src/tim.c \
	Board/v3/Src/dma.c \
	Board/v3/Src/freertos.c \
	Board/v3/Src/main.c \
	Board/v3/Src/usbd_conf.c \
	Board/v3/Src/spi.c \
	Board/v3/Src/usart.c \
	Board/v3/Src/usbd_cdc_if.c \
	Board/v3/Src/adc.c \
	Board/v3/Src/stm32f4xx_hal_msp.c \
	Board/v3/Src/usbd_desc.c \
	Board/v3/Src/stm32f4xx_it.c \
	Board/v3/Src/usb_device.c \
	Board/v3/Src/can.c \
	Board/v3/Src/system_stm32f4xx.c \
	Board/v3/Src/gpio.c \
	Board/v3/Src/i2c.c

HAL_SRCS := $(addprefix ThirdParty/STM32F4xx_HAL_Driver/Src/, \
	stm32f4xx_hal.c stm32f4xx_hal_adc.c stm32f4xx_hal_adc_ex.c stm32f4xx_hal_can.c \
	stm32f4xx_hal_cortex.c stm32f4xx_hal_dma.c stm32f4xx_hal_dma_ex.c stm32f4xx_hal_flash.c \
	stm32f4xx_hal_flash_ex.c stm32f4xx_hal_flash_ramfunc.c stm32f4xx_hal_gpio.c stm32f4xx_hal_i2c.c \
	stm32f4xx_hal_i2c_ex.c stm32f4xx_hal_pcd.c stm32f4xx_hal_pcd_ex.c stm32f4xx_hal_pwr.c \
	stm32f4xx_hal_pwr_ex.c stm32f4xx_hal_rcc.c stm32f4xx_hal_rcc_ex.c stm32f4xx_hal_spi.c \
	stm32f4xx_hal_tim.c stm32f4xx_hal_tim_ex.c stm32f4xx_hal_uart.c stm32f4xx_ll_usb.c)

FREERTOS_SRCS := $(addprefix ThirdParty/FreeRTOS/Source/, \
	croutine.c event_groups.c list.c queue.c stream_buffer.c tasks.c timers.c \
	CMSIS_RTOS/cmsis_os.c portable/MemMang/heap_4.c)

USB_SRCS := $(addprefix ThirdParty/STM32_USB_Device_Library/, \
	Core/Src/usbd_core.c Core/Src/usbd_ctlreq.c Core/Src/usbd_ioreq.c Class/CDC/Src/usbd_cdc.c)

# fibre server only, no client, no heap, log verbosity 0 (so no logging.cpp)
FIBRE_SRCS := fibre-cpp/fibre.cpp fibre-cpp/channel_discoverer.cpp fibre-cpp/legacy_protocol.cpp

ODRIVE_SRCS := \
	syscalls.c \
	MotorControl/utils.cpp \
	MotorControl/arm_sin_f32.c \
	MotorControl/arm_cos_f32.c \
	MotorControl/low_level.cpp \
	MotorControl/axis.cpp \
	MotorControl/motor.cpp \
	MotorControl/thermistor.cpp \
	MotorControl/encoder.cpp \
	MotorControl/endstop.cpp \
	MotorControl/acim_estimator.cpp \
	MotorControl/mechanical_brake.cpp \
	MotorControl/controller.cpp \
	MotorControl/foc.cpp \
	MotorControl/open_loop_controller.cpp \
	MotorControl/capture.cpp \
	MotorControl/sensorless_estimator.cpp \
	MotorControl/trapTraj.cpp \
	MotorControl/pwm_input.cpp \
	MotorControl/main.cpp \
	Drivers/STM32/stm32_system.cpp \
	Drivers/STM32/stm32_gpio.cpp \
	Drivers/STM32/stm32_nvm.c \
	Drivers/STM32/stm32_spi_arbiter.cpp \
	communication/can/can_simple.cpp \
	communication/can/odrive_can.cpp \
	communication/communication.cpp \
	communication/ascii_protocol.cpp \
	communication/interface_uart.cpp \
	communication/interface_usb.cpp \
	communication/interface_i2c.cpp \
	FreeRTOS-openocd.c

SRCS := $(BOARD_SRCS) $(HAL_SRCS) $(FREERTOS_SRCS) $(USB_SRCS) $(FIBRE_SRCS) $(ODRIVE_SRCS)

# Include dirs and package cflags, in Tupfile.lua's add_pkg order.
PKG_FLAGS := \
	-DHW_VERSION_MINOR=6 -DHW_VERSION_VOLTAGE=56 \
	-IBoard/v3/Inc -IThirdParty/FreeRTOS/Source/portable/GCC/ARM_CM4F \
	-DSTM32F405xx -DHW_VERSION_MAJOR=3 \
	-IThirdParty/STM32F4xx_HAL_Driver/Inc \
	-DARM_MATH_CM4 -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -DFPU_FPV4 \
	-IThirdParty/FreeRTOS/Source/include -IThirdParty/FreeRTOS/Source/CMSIS_RTOS \
	-IThirdParty/CMSIS/Include -IThirdParty/CMSIS/Device/ST/STM32F4xx/Include \
	-IThirdParty/STM32_USB_Device_Library/Core/Inc -IThirdParty/STM32_USB_Device_Library/Class/CDC/Inc \
	-Ifibre-cpp/include \
	-DFIBRE_ENABLE_SERVER=1 -DFIBRE_ENABLE_CLIENT=0 -DFIBRE_ENABLE_EVENT_LOOP=0 -DFIBRE_ALLOW_HEAP=0 \
	-DFIBRE_MAX_LOG_VERBOSITY=0 -DFIBRE_DEFAULT_LOG_VERBOSITY=2 -DFIBRE_ENABLE_LIBUSB_BACKEND=0 \
	-DFIBRE_ENABLE_TCP_SERVER_BACKEND=0 -DFIBRE_ENABLE_TCP_CLIENT_BACKEND=0 \
	-I. -IMotorControl -Ifibre-cpp/include

PKG_LDFLAGS := -TBoard/v3/STM32F405RGTx_FLASH.ld -larm_cortexM4lf_math -LThirdParty/CMSIS/Lib/GCC
