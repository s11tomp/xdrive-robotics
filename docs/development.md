# Developer notes

How the repository is laid out, how to build and test it, how to debug a running board, and how releases are made. Features, quick start and the host tools are in the top-level `README.md`.

## Layout

| Path | Contents |
|---|---|
| `Makefile` | The entry point: `make`, `make test`, `make generate`, `make clean` |
| `requirements.txt` | One Python env (`.venv`) for the code generators and the host tools |
| `src/` | The firmware, built by `src/Makefile` from the file lists in `src/sources.mk` |
| `src/MotorControl/`, `src/communication/`, `src/Drivers/`, `src/Board/v3/` | Control loop, axis state machine and estimators; USB, CAN and UART protocols; the DRV8301 and STM32 drivers; the board's startup code, timers and ADCs |
| `src/odrive-interface.yaml` | Every property and function exposed over USB; the build generates the fibre headers from it |
| `src/ThirdParty/`, `src/fibre-cpp/` | Vendored libraries: CMSIS, STM32 HAL, FreeRTOS, the STM32 USB device library, and ODrive's fibre protocol |
| `src/tests/` | Unit tests of the firmware's algorithms, built for the host with doctest |
| `tools/` | Host tools (flash, configure, calibrate, bench tests, analysis) and their tests in `tools/tests/` |
| `tools/codegen/` | ODrive's fibre interface generator, with the template for `tools/enums_v056.py` |
| `docs/` | User documentation, `figures/` (SVG, with `plots.py` for the plotted ones), the generated `reference.md` and `cansimple.dbc` |
| `examples/` | Example settings and a CAN example |
| `build/` | All build output: `firmware.{elf,hex,bin,map}`, generated headers (`autogen/`), object files, the unit-test binary |

The firmware's sources keep the directory layout of ODrive v0.5.6's `Firmware/` tree, so `git diff -M upstream/fw-v0.5.6 main -- Firmware src` shows every change to them.

## Branches and tags
- `upstream`: upstream ODrive snapshots, tagged `upstream/fw-v0.5.1` and `upstream/fw-v0.5.6`. They come from GitHub tarballs, so there's no upstream history. The 0.5.6 snapshot leaves out the five prebuilt `libfibre-*` tool binaries (Git LFS pointers only).
- `main`: ODrive v0.5.6 + the Mini changes + this firmware's features.
  - Makerbase's v0.5.1 changes are the commit after the `upstream/fw-v0.5.1` snapshot (9 lines in 3 files).
  - Tag `xdrive/v0.5.1` is the last v0.5.1-based state, in the upstream layout. It holds the byte-identical build described below.
- **Mini changes on v0.5.6:**
  - **One axis** (`AXIS_COUNT` 1 in `src/Board/v3/Inc/board.h`; `axis1` removed from `odrive-interface.yaml`). Stock v0.5.6 retries every idle motor's gate-driver setup every millisecond, and for the Mini's missing second driver that means endless SPI traffic on the bus the encoder shares, which is why stock v0.5.6 doesn't drive the Mini. ADC1's injected end-of-conversion interrupt (`ADC_IRQHandler` in `src/Board/v3/board.cpp`), at each TIM1 update event, starts the control loop; ODrive v3.6 starts it from the second motor's PWM timer, TIM8, which this firmware doesn't have.
  - **AS5047 frame checks are configurable** (`encoder.config.abs_spi_check_parity`, `abs_spi_reject_error_flag`) with counters. An AS5047P sends even parity in bit 15; an AS5047U has no parity.
  - **Makerbase's two other encoder patches are not carried over:** v0.5.6 already makes a pre-calibrated SPI absolute encoder ready on its first valid read.
- **High-rate capture internals:** the buffer is read in bulk from fibre endpoint 0x7F00 (`fibre::kRawEndpointBase`); `src/fibre-cpp/legacy_protocol.cpp` routes IDs from there up to `fibre::raw_endpoint_handler`.

## Toolchain
`main` (v0.5.6) builds with GNU Arm Embedded **10.3-2021.10** (GCC 10.3.1), the version v0.5.6's CI used (Ubuntu's `gcc-arm-none-eabi`). Only an Intel build exists for macOS; it runs under Rosetta 2.
```sh
mkdir -p ~/.local/arm/dl && cd ~/.local/arm/dl
curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
md5 gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2          # 7f2a7b7b23797302a9d6182c6e482449
cd .. && tar -xjf dl/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
```
The build looks for it in `~/.local/arm/gcc-arm-none-eabi-10.3-2021.10/bin/`. Override with `TOOLCHAIN=<dir>/`. On Linux, use the `x86_64-linux` archive from the same release. The tag `xdrive/v0.5.1` uses Makerbase's compiler, 7-2018-q2-update (`.../7-2018q2/gcc-arm-none-eabi-7-2018-q2-update-mac.tar.bz2`, md5 a66be9828cf3c57d7d21178e07cd8904). The Makefile also needs `uv`: it creates `.venv` from `requirements.txt` by itself.

## Build
```sh
make -j8          # -> build/firmware.{elf,hex,bin,map}
make asm          # disassembly -> build/firmware.asm
make clean        # removes build/
```
- **Plain make, not tup:** ODrive builds with tup, which needs FUSE, and macOS doesn't have it. `src/sources.mk` transcribes the v3.6-56V board configuration from ODrive v0.5.6's `Firmware/Tupfile.lua` (at the tag `upstream/fw-v0.5.6`): sources, include order and package flags. `src/Makefile` adds Tupfile.lua's global flags. The compiler runs in `src/`, so `__FILE__` strings and the binary don't depend on where the repository is checked out.
- **Adding a source file:** add it to the right list in `src/sources.mk`.
- **Version:** `tools/version.py` takes it from `git describe --match=*fw*` (see Versioning in the top-level README).

## Generated files
`make generate` rewrites five committed files from `src/odrive-interface.yaml`; run it after every interface change. CI runs it and fails when the result differs from what is committed.
- `docs/reference.md`, the property reference (`tools/gen_reference.py`). It marks the items ODrive v0.5.6 doesn't have, read from the tag `upstream/fw-v0.5.6`.
- `docs/cansimple.dbc`, the CAN database (`tools/gen_dbc.py`). The message layouts are written out in the generator, following `src/communication/can/can_simple.cpp`; only the enum values come from the interface file, so a new or changed CAN message needs an edit to `gen_dbc.py` as well.
- `tools/enums_v056.py`, the enum and error-bit values the CAN database generator uses (`tools/codegen/enums_template.j2`).
- `tools/xdrive/props.py` and `tools/xdrive/enums.py`, the host library's typed names for every property and function and its enum and error-flag classes (`tools/gen_props.py`). `tools/tests/test_xdrive.py` checks the names against the interface JSON the firmware embeds, produced by the same generator.

The diagrams in `docs/figures/` are hand-written SVG; `python docs/figures/plots.py` redraws the plots (its docstring lists which logs each needs).

## Tests
`make test` builds the firmware's unit tests (`src/tests/`) for the host with `HOST_CXX` (default `c++`) and runs them, then runs the host tools' tests (`tools/tests/`, which compile firmware headers with `clang++`). Neither needs a board. The bench tests that do are in `docs/testing.md`.

## Debugging over SWD
Wire an ST-Link to J2, including NRST ([Getting started](getting-started.md#wire-it)), and build the same source the board runs, so the symbols match. Then, in two terminals:
```sh
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c 'stm32f4x.cpu configure -rtos FreeRTOS'
arm-none-eabi-gdb build/firmware.elf -ex 'target extended-remote :3333'
```
These commands are not yet run against a board here. GDB attaches without flashing or resetting; `info threads` lists the FreeRTOS threads (`src/FreeRTOS-openocd.c` exports what OpenOCD needs for that). Flash with `tools/usb_flash.py` or `tools/swd_flash.py`, which back up the whole flash first and check the write.

> **Warning:** attaching halts the core, and so does every breakpoint. While the core is halted, TIM1 (the PWM timer) is frozen with its outputs off, so the motor stops driving and turns freely. A joint holding a load drops. Debug with the motor IDLE or free to coast.

A halt can also trip the control loop's timing checks on resume (`MOTOR_ERROR_CONTROL_DEADLINE_MISSED`, `TIMER_UPDATE_MISSED`), which disarm the axis. Clear the errors and enter closed loop again. `tools/swd_backup.py` reads the whole flash over the same ST-Link without halting the core.

## At tag `xdrive/v0.5.1`: byte-identical to Makerbase's firmware
These instructions apply to a checkout of the tag, which has the upstream layout (`xdrive/firmware.mk` has `MAKERBASE_VERSION`/`LIB_OVERRIDE`).
```sh
# The Windows release's target libraries; Makerbase linked against these.
cd ~/.local/arm/dl && curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/7-2018q2/gcc-arm-none-eabi-7-2018-q2-update-win32.zip
mkdir -p win && cd win && unzip -q ../gcc-arm-none-eabi-7-2018-q2-update-win32.zip \
  'arm-none-eabi/lib/thumb/v7e-m/fpv4-sp/hard/*' 'lib/gcc/arm-none-eabi/7.3.1/thumb/v7e-m/fpv4-sp/hard/*'
make -C xdrive MAKERBASE_VERSION=1 LIB_OVERRIDE=$HOME/.local/arm/dl/win clean verify-makerbase
```
The `.bin` and `.hex` are then identical to the build outputs in Makerbase's source archive ([makerbase-motor/MKS-ODrive](https://github.com/makerbase-motor/MKS-ODrive), `Firmware/MKS ODrive MINI/ODriveMINI-fw-v0.5.1-20250326.rar`, `Firmware/build/`). The one Mini checked ran exactly this build, apart from the 8-byte gap after the vector table, which isn't programmed from a hex; other Minis can ship with other v0.5.1 builds.
- **Why the Windows libraries:** the Mac and Windows releases ship different `libc`, `libstdc++` and `libgcc` archives, with members in a different order. With the Mac ones, every section built from the firmware's sources lands at the same address and size, but library code is ordered differently.
- **What this proves:** the sources, generated code, flags, link order and compiler reproduce Makerbase's firmware exactly, so every difference in later builds comes from source changes.

## Flashing details
`tools/usb_flash.py` (USB DFU) and `tools/swd_flash.py` (ST-Link and OpenOCD) share the same checks:
- **Before writing:** the axis goes IDLE, and the whole flash is read twice (the reads must match) and saved under `backups/`, reusing an identical existing backup. `swd_flash.py` also checks that the SWD and USB serials match.
- **Write:** erases only the sectors the image covers. The config lives in sectors 10–11, so it stays.
- **Read-back:** the whole flash is read and checked: the image must match, and sectors outside the erased ones must be unchanged. `usb_flash.py` stays in the bootloader on a mismatch and prints the restore command.
- **Afterwards:** Motor moves: the board reboots and its startup sequence runs.
- **SWD wiring:** J2 GND/SWCLK/SWDIO, plus NRST (J2 pin 5) to the ST-Link's RST, so a crashed build can still be reached with connect-under-reset.
- **Never written:** the option bytes (read and write protection).

## Releasing
Pushing a tag `fw-vX.Y.Z` releases X.Y.Z: CI (`.github/workflows/build.yml`) checks that `CHANGELOG.md` has a dated section for X.Y.Z, builds, checks that the firmware reports exactly X.Y.Z (`fw_version_unreleased = 0`), and publishes a GitHub release named "xdrive-robotics X.Y.Z" with `xdrive-robotics-X.Y.Z.{elf,bin,hex}`, `SHA256SUMS` and the changelog section as its notes. A failed check publishes nothing.
1. In `CHANGELOG.md`, change the section's heading from `Unreleased` to the release date: `## xdrive-robotics [X.Y.Z] - YYYY-MM-DD`.
2. `python tools/release_notes.py X.Y.Z` (prints the release notes, or what is missing).
3. Commit and push `main`.
4. `git tag fw-vX.Y.Z`
5. `git push origin fw-vX.Y.Z`
6. Afterwards, start the next section: `## xdrive-robotics [X.Y.Z+1] - Unreleased` (or the next minor or major, per the versioning rules in the top-level README).
