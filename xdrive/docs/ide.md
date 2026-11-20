# Building and debugging in VS Code

`Firmware/.vscode/` holds a build task and two debug configurations for VS Code. The toolchain, the build and flashing are described in `xdrive/README.md`; this page covers the editor setup and debugging over SWD.

## Setup

1. Install the toolchain and `uv` (`xdrive/README.md`, Toolchain).
2. Install the extensions C/C++ (`ms-vscode.cpptools`) and Cortex-Debug (`marus25.cortex-debug`), and OpenOCD (on macOS: `brew install open-ocd`).
3. Point Cortex-Debug at the toolchain: the setting `cortex-debug.armToolchainPath` = `~/.local/arm/gcc-arm-none-eabi-10.3-2021.10/bin`.
4. Open the `Firmware/` folder.

## Build

**Terminal ▸ Run Build Task** runs `make -C ../xdrive -j8`; the `clean` task runs `make -C ../xdrive clean`. The output is `Firmware/build/ODriveFirmware.elf`, with debug symbols (`-g`) at `-O2`.

Flashing is not a task. Flash with `xdrive/tools/usb_flash.py` or `swd_flash.py` ([Getting started](getting-started.md#flash-the-firmware)): they back up the whole flash first and check the write.

## Debug

Wire an ST-Link to J2, including NRST ([Getting started](getting-started.md#wire-it)), and build the same source the board runs, so the symbols match.

Both configurations in **Run and Debug** attach to the running firmware and never flash it:

- **Attach - ST-Link**: registers (with the STM32F40x peripheral view), breakpoints, variables.
- **Attach - ST-Link - FreeRTOS threads**: the same, plus each FreeRTOS thread's stack.

> **Warning:** attaching halts the core, and so does every breakpoint. While the core is halted, TIM1 (the PWM timer) is frozen with its outputs off, so the motor stops driving and turns freely. A joint holding a load drops. Debug with the motor IDLE or free to coast.

A halt can also trip the control loop's timing checks on resume (`MOTOR_ERROR_CONTROL_DEADLINE_MISSED`, `TIMER_UPDATE_MISSED`), which disarm the axis. Clear the errors and enter closed loop again.

`xdrive/tools/swd_backup.py` reads the whole flash over the same ST-Link without halting the core.
