# Generated from the .tup/db in Makerbase's fw-v0.5.1-20250326 source archive. Paths are relative to Firmware/.
# LINK_SRCS is the link order, which matters for a byte-identical build; the four *_SRCS lists pick the flag set.
LINK_SRCS := \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c \
	Board/v3/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_ioreq.c \
	Board/v3/Src/stm32f4xx_hal_timebase_TIM.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_can.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_usb.c \
	Board/v3/Src/tim.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd_ex.c \
	Board/v3/Src/dma.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c \
	Board/v3/Src/freertos.c \
	Board/v3/Src/main.c \
	Board/v3/Src/usbd_conf.c \
	Board/v3/Src/spi.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F/port.c \
	Board/v3/Src/usart.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/croutine.c \
	Board/v3/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_core.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/portable/MemMang/heap_4.c \
	Board/v3/Src/usbd_cdc_if.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd.c \
	Board/v3/Src/adc.c \
	Board/v3/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_ctlreq.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/list.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c \
	Board/v3/Src/stm32f4xx_hal_msp.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c \
	Board/v3/Src/usbd_desc.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c \
	Board/v3/Src/stm32f4xx_it.c \
	Board/v3/Src/usb_device.c \
	Board/v3/Src/can.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/queue.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS/cmsis_os.c \
	Board/v3/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c \
	Board/v3/Src/system_stm32f4xx.c \
	Board/v3/Src/gpio.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/tasks.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/timers.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c \
	Board/v3/Middlewares/Third_Party/FreeRTOS/Source/event_groups.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c.c \
	Board/v3/Src/i2c.c \
	Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c_ex.c \
	Board/v3/startup_stm32f405xx.s \
	Board/v3/Src/syscalls.c \
	Drivers/DRV8301/drv8301.c \
	MotorControl/utils.cpp \
	MotorControl/arm_sin_f32.c \
	MotorControl/arm_cos_f32.c \
	MotorControl/low_level.cpp \
	MotorControl/nvm.c \
	MotorControl/axis.cpp \
	MotorControl/motor.cpp \
	MotorControl/thermistor.cpp \
	MotorControl/encoder.cpp \
	MotorControl/endstop.cpp \
	MotorControl/controller.cpp \
	MotorControl/sensorless_estimator.cpp \
	MotorControl/trapTraj.cpp \
	MotorControl/main.cpp \
	communication/can_simple.cpp \
	communication/communication.cpp \
	communication/ascii_protocol.cpp \
	communication/interface_uart.cpp \
	communication/interface_usb.cpp \
	communication/interface_can.cpp \
	communication/interface_i2c.cpp \
	fibre/cpp/protocol.cpp \
	FreeRTOS-openocd.c \
	autogen/version.c \

BOARD_C_SRCS := Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c Board/v3/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_ioreq.c Board/v3/Src/stm32f4xx_hal_timebase_TIM.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_can.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_usb.c Board/v3/Src/tim.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd_ex.c Board/v3/Src/dma.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c Board/v3/Src/freertos.c Board/v3/Src/main.c Board/v3/Src/usbd_conf.c Board/v3/Src/spi.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F/port.c Board/v3/Src/usart.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/croutine.c Board/v3/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_core.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/portable/MemMang/heap_4.c Board/v3/Src/usbd_cdc_if.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd.c Board/v3/Src/adc.c Board/v3/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_ctlreq.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/list.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c Board/v3/Src/stm32f4xx_hal_msp.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c Board/v3/Src/usbd_desc.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c Board/v3/Src/stm32f4xx_it.c Board/v3/Src/usb_device.c Board/v3/Src/can.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/queue.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS/cmsis_os.c Board/v3/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c Board/v3/Src/system_stm32f4xx.c Board/v3/Src/gpio.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/tasks.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/timers.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c Board/v3/Middlewares/Third_Party/FreeRTOS/Source/event_groups.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c.c Board/v3/Src/i2c.c Board/v3/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c_ex.c Board/v3/Src/syscalls.c

ODRIVE_C_SRCS := Drivers/DRV8301/drv8301.c MotorControl/arm_sin_f32.c MotorControl/arm_cos_f32.c MotorControl/nvm.c FreeRTOS-openocd.c autogen/version.c

CXX_SRCS := MotorControl/utils.cpp MotorControl/low_level.cpp MotorControl/axis.cpp MotorControl/motor.cpp MotorControl/thermistor.cpp MotorControl/encoder.cpp MotorControl/endstop.cpp MotorControl/controller.cpp MotorControl/sensorless_estimator.cpp MotorControl/trapTraj.cpp MotorControl/main.cpp communication/can_simple.cpp communication/communication.cpp communication/ascii_protocol.cpp communication/interface_uart.cpp communication/interface_usb.cpp communication/interface_can.cpp communication/interface_i2c.cpp fibre/cpp/protocol.cpp

ASM_SRCS := Board/v3/startup_stm32f405xx.s

