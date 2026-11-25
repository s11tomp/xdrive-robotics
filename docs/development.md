# Development

How the repository is laid out, how to build and test it, how to debug a running board, and how releases are made. For using the firmware, start at the top-level `README.md`.

## Layout

| Path | Contents |
|---|---|
| `Makefile` | The entry point: `make`, `make test`, `make generate`, `make asm`, `make size`, `make clean`, `make venv` |
| `requirements.txt` | One Python env (`.venv`) for the code generators and the host tools |
| `src/` | The firmware, built by `src/Makefile` from the file lists in `src/sources.mk` |
| `src/MotorControl/`, `src/communication/`, `src/Drivers/`, `src/Board/v3/` | Control loop, axis state machine and estimators; USB, CAN and UART protocols; the DRV8301 and STM32 drivers; the board's startup code, timers and ADCs |
| `src/bootloader/` | The [CAN bootloader](bootloader.md): its program, linker script and protocol (`boot_protocol.hpp`) |
| `src/odrive-interface.yaml` | Every property and function exposed over USB and CAN, with its description; the build generates the fibre headers from it |
| `src/ThirdParty/`, `src/fibre-cpp/` | Vendored libraries: CMSIS, STM32 HAL, FreeRTOS, the STM32 USB device library, and ODrive's fibre protocol |
| `src/tests/` | Unit tests of the firmware's algorithms, built for the host with doctest |
| `tools/` | Host tools ([Host tools](tools.md)), the host library `xdrive/`, their tests in `tests/`, and the generators (`gen_reference.py`, `gen_dbc.py`, `gen_props.py`, `seal_image.py`, `version.py`, `release_notes.py`) |
| `tools/codegen/` | ODrive's fibre interface parser and generator |
| `docs/` | User documentation, `figures/` (SVG, with `plots.py` for the plotted ones), the generated `reference.md` and `cansimple.dbc` |
| `examples/` | Example settings for a DJI 10018 and a CAN example |
| `build/` | All build output: firmware and bootloader images, generated headers (`autogen/`), object files, the unit-test binary (not committed) |

The firmware's sources keep the directory layout of ODrive v0.5.6's `Firmware/` tree, so `git diff -M upstream/fw-v0.5.6 main -- Firmware src` shows every change to them.

## Branches and tags

- `upstream`: snapshots of upstream ODrive, tagged `upstream/fw-v0.5.1` and `upstream/fw-v0.5.6`. They come from GitHub tarballs, so they carry no upstream history. The v0.5.6 snapshot leaves out the five prebuilt `libfibre-*` tool binaries, which upstream stores in Git LFS.
- `main`: ODrive v0.5.6 with the Mini support and this firmware's features. Makerbase's v0.5.1 changes are the commit after the `upstream/fw-v0.5.1` snapshot (9 lines in 3 files).
- Tag `xdrive/v0.5.1`: Makerbase's firmware rebuilt from source in the upstream layout ([Rebuilding Makerbase's firmware](#rebuilding-makerbases-firmware)).
- Tags `fw-vX.Y.Z`: releases ([Releasing](#releasing)).

## Where the Mini support lives

- **One axis:** `AXIS_COUNT` is 1 in `src/Board/v3/Inc/board.h`, and `odrive-interface.yaml` has no `axis1`. Stock v0.5.6 retries every idle motor's gate-driver setup every millisecond; for the Mini's missing second driver that means endless traffic on the SPI bus the encoder shares, which is why stock v0.5.6 doesn't drive the Mini.
- **Control-loop trigger:** ADC1's injected end-of-conversion interrupt (`ADC_IRQHandler` in `src/Board/v3/board.cpp`) runs at every TIM1 update event, at the top and the bottom of the center-aligned PWM count (16 kHz). It starts the control loop only after the bottom one, when the counter counts up, so the loop runs at 8 kHz. ODrive v3.6 starts the loop from the second motor's PWM timer, TIM8, which this firmware doesn't use.
- **AS5047 frame checks:** `src/MotorControl/encoder.cpp`, configurable through `encoder.config.abs_spi_check_parity`, `abs_spi_reject_error_flag` and `abs_spi_max_jump`. Makerbase's other encoder patches have no counterpart: v0.5.6 already makes a pre-calibrated SPI absolute encoder ready on its first valid read.
- **Capture readout:** the host reads the capture buffer in bulk from fibre endpoint 0x7F00 (`fibre::kRawEndpointBase`); `src/fibre-cpp/legacy_protocol.cpp` routes IDs from there up to `fibre::raw_endpoint_handler`.
- **fibre's serializer:** `SimpleSerializer::read` treats a null end pointer as an unbounded buffer, so calling a generated endpoint handler with a default-constructed (null) input buffer decodes bytes from address 0 into a writable property. An empty input needs a non-null pointer with zero length.

## Toolchain

`main` builds with GNU Arm Embedded **10.3-2021.10** (GCC 10.3.1), the version ODrive v0.5.6's CI used. Only an Intel build exists for macOS; it runs under Rosetta 2.

```sh
mkdir -p ~/.local/arm/dl && cd ~/.local/arm/dl
curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
md5 gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2          # 7f2a7b7b23797302a9d6182c6e482449
cd .. && tar -xjf dl/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
```

The build looks for it in `~/.local/arm/gcc-arm-none-eabi-10.3-2021.10/bin/`; `TOOLCHAIN=<dir>/` overrides that. On Linux, use the `x86_64-linux` archive from the same release. The Makefile also needs `uv`: it creates `.venv` from `requirements.txt` by itself.

## Build

```sh
make -j8          # -> build/firmware.{elf,hex,bin,map} (sealed for the CAN bootloader), build/bootloader.{elf,bin,hex},
                  #    build/firmware-with-bootloader.bin
make asm          # disassembly -> build/firmware.asm
make size         # section sizes
make clean        # removes build/
```

- **Plain make, not tup:** ODrive builds with tup, which needs FUSE, and macOS doesn't have it. `src/sources.mk` transcribes the v3.6-56V board configuration from ODrive v0.5.6's `Firmware/Tupfile.lua` (at the tag `upstream/fw-v0.5.6`): sources, include order and package flags. `src/Makefile` adds Tupfile.lua's global flags. The compiler runs in `src/` with relative paths, so `__FILE__` strings and the binary don't depend on where the repository is checked out.
- **Binary check for refactors:** a change that moves or renames files without changing code gives a byte-identical `build/firmware.bin`; compare it with a build of the previous commit.
- **Adding a source file:** add it to the right list in `src/sources.mk`.
- **Sealing:** `tools/seal_image.py` writes the image header's length, CRC-32 and version, which the CAN bootloader checks before starting the firmware.
- **Version:** `tools/version.py` takes it from `git describe --match=*fw*` (see Versioning in the top-level `README.md`).

## Generated files

`make generate` rewrites four committed files from `src/odrive-interface.yaml`; run it after every interface change. CI runs it and fails when the result differs from what is committed.

- `docs/reference.md`, the property reference (`tools/gen_reference.py`), from the descriptions in the interface file. It marks the items ODrive v0.5.6 doesn't have, read from the tag `upstream/fw-v0.5.6`.
- `docs/cansimple.dbc`, the CAN database (`tools/gen_dbc.py`). The message layouts are written out in the generator, following `src/communication/can/can_simple.cpp`; only the enum values come from the interface (through `xdrive.enums`), so a new or changed CAN message needs an edit to `gen_dbc.py` as well.
- `tools/xdrive/props.py` and `tools/xdrive/enums.py`, the host library's typed names for every property and function and its enum and error-flag classes (`tools/gen_props.py`). `tools/tests/test_xdrive.py` checks the names against the interface JSON the firmware embeds, produced by the same generator.

The diagrams in `docs/figures/` are hand-written SVG on an opaque white panel, so they read the same in GitHub's light and dark themes; `python docs/figures/plots.py` redraws the plots (its docstring lists which logs each needs). Flows, decisions and sequences are Mermaid blocks in the Markdown itself, which GitHub renders in the reader's theme.

## Tests

`make test` builds the firmware's unit tests (`src/tests/`) for the host with `HOST_CXX` (default `c++`) and runs them, runs mypy on the host library and the tools that use it, then runs the host tools' tests (`tools/tests/`, which compile firmware headers with `clang++`). None of them needs a board. [Testing](testing.md) lists what they check, and the bench tests that do need a board.

## Debugging over SWD

Wire an ST-Link to J2, including NRST ([Hardware](hardware.md#header-pinouts)), and build the same source the board runs, so the symbols match. Then, in two terminals:

```sh
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c 'stm32f4x.cpu configure -rtos FreeRTOS'
arm-none-eabi-gdb build/firmware.elf -ex 'target extended-remote :3333'
```

These commands are untested against a board. GDB attaches without flashing or resetting; `info threads` lists the FreeRTOS threads (`src/FreeRTOS-openocd.c` exports what OpenOCD needs for that). Flash with `tools/usb_flash.py` or `tools/swd_flash.py`, which back up the whole flash first and check the write ([Host tools](tools.md#flashing)).

> **Warning:** attaching halts the core, and so does every breakpoint. While the core is halted, TIM1 (the PWM timer) is frozen with its outputs off, so the motor stops driving and turns freely. A joint holding a load drops. Debug with the motor IDLE or free to coast.

A halt can also trip the control loop's timing checks on resume (`MOTOR_ERROR_CONTROL_DEADLINE_MISSED`, `TIMER_UPDATE_MISSED`), which disarm the axis. Clear the errors and enter closed loop again. `tools/swd_backup.py` reads the whole flash over the same ST-Link without halting the core.

## Rebuilding Makerbase's firmware

The tag `xdrive/v0.5.1` rebuilds Makerbase's release `ODriveMINI-fw-v0.5.1-20250326` byte for byte. It has the upstream layout (`Firmware/`, plus the build in `xdrive/`) and needs Makerbase's compiler, GNU Arm Embedded 7-2018-q2-update (`gcc-arm-none-eabi-7-2018-q2-update-mac.tar.bz2` from the 7-2018q2 release, md5 a66be9828cf3c57d7d21178e07cd8904, unpacked in `~/.local/arm/`), and the Windows release's target libraries, which Makerbase linked against:

```sh
(cd ~/.local/arm/dl && curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/7-2018q2/gcc-arm-none-eabi-7-2018-q2-update-win32.zip \
  && mkdir -p win && cd win && unzip -q ../gcc-arm-none-eabi-7-2018-q2-update-win32.zip \
  'arm-none-eabi/lib/thumb/v7e-m/fpv4-sp/hard/*' 'lib/gcc/arm-none-eabi/7.3.1/thumb/v7e-m/fpv4-sp/hard/*')
git checkout xdrive/v0.5.1      # from the repository root
make -C xdrive MAKERBASE_VERSION=1 LIB_OVERRIDE=$HOME/.local/arm/dl/win clean all
cmp Firmware/build/ODriveFirmware.bin <archive>/Firmware/build/ODriveFirmware.bin
```

`<archive>` is Makerbase's source archive, `Firmware/MKS ODrive MINI/ODriveMINI-fw-v0.5.1-20250326.rar` in [makerbase-motor/MKS-ODrive](https://github.com/makerbase-motor/MKS-ODrive), unpacked. The `.bin` has the SHA-256 `db50df8beeeee7cfe90c711bebdef5c9c147dc9d7a036d905e7f37ffc1c8afd5`. The one Mini checked ran exactly this build, apart from the 8-byte gap after the vector table, which a flash from the `.hex` doesn't program; other Minis can ship with other v0.5.1 builds.

- **Why the Windows libraries:** the Mac and Windows releases ship different `libc`, `libstdc++` and `libgcc` archives, with members in a different order. With the Mac ones, every section built from the firmware's sources lands at the same address and size, but library code is ordered differently.
- **What this shows:** the sources, generated code, flags, link order and compiler reproduce Makerbase's firmware exactly, so every difference in later builds comes from source changes.

## Releasing

Pushing a tag `fw-vX.Y.Z` releases X.Y.Z. CI (`.github/workflows/build.yml`) checks that `CHANGELOG.md` has a dated section for X.Y.Z, builds, checks that the firmware reports exactly X.Y.Z (`fw_version_unreleased = 0`), and publishes a GitHub release named "xdrive-robotics X.Y.Z" with the changelog section as its notes and the images: `xdrive-robotics-X.Y.Z.{elf,bin,hex}`, `xdrive-robotics-X.Y.Z-bootloader.elf`, `xdrive-robotics-X.Y.Z-with-bootloader.bin` (a board's first flash) and `SHA256SUMS`. A failed check publishes nothing.

`CHANGELOG.md` holds one section per release, headed `## xdrive-robotics [X.Y.Z] - YYYY-MM-DD`; unreleased changes collect under the next version, dated `Unreleased`. `tools/release_notes.py` extracts a section and refuses one that is missing, empty or undated.

1. In `CHANGELOG.md`, change the section's date from `Unreleased` to the release date.
2. `python tools/release_notes.py X.Y.Z` (prints the release notes, or what is missing).
3. Commit and push `main`.
4. `git tag fw-vX.Y.Z`
5. `git push origin fw-vX.Y.Z`
6. Start the next section: `## xdrive-robotics [X.Y.Z+1] - Unreleased` (or the next minor or major, per the versioning rules in the top-level `README.md`).
