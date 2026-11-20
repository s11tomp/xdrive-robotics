# Developer notes

Everything outside `xdrive/` is ODrive's tree, with this firmware's changes in `Firmware/`. `xdrive/` holds the build system, host tools, examples and board documentation. Features, quick start and the host tools are in the top-level `README.md`.

## Branches and tags
- `upstream`: upstream ODrive snapshots, tagged `upstream/fw-v0.5.1` and `upstream/fw-v0.5.6`. They come from GitHub tarballs, so there's no upstream history. The 0.5.6 snapshot leaves out the five prebuilt `libfibre-*` tool binaries (Git LFS pointers only).
- `main`: ODrive v0.5.6 + the Mini changes + this firmware's features.
  - Makerbase's v0.5.1 changes are the commit after the `upstream/fw-v0.5.1` snapshot (9 lines in 3 files).
  - Tag `xdrive/v0.5.1` is the last v0.5.1-based state. It holds the byte-identical build described below.
- **Mini changes on v0.5.6:**
  - **One axis** (`AXIS_COUNT` 1 in `Board/v3/Inc/board.h`; `axis1` removed from `odrive-interface.yaml`). Stock v0.5.6 retries every idle motor's gate-driver setup every millisecond, and for the Mini's missing second driver that means endless SPI traffic on the bus the encoder shares, which is why stock v0.5.6 doesn't drive the Mini. ADC1's injected end-of-conversion interrupt (`ADC_IRQHandler` in `Board/v3/board.cpp`), at each TIM1 update event, starts the control loop; ODrive v3.6 starts it from the second motor's PWM timer, TIM8, which this firmware doesn't have.
  - **AS5047 frame checks are configurable** (`encoder.config.abs_spi_check_parity`, `abs_spi_reject_error_flag`) with counters. An AS5047P sends even parity in bit 15; an AS5047U has no parity.
  - **Makerbase's two other encoder patches are not carried over:** v0.5.6 already makes a pre-calibrated SPI absolute encoder ready on its first valid read.
- **High-rate capture internals:** the buffer is read in bulk from fibre endpoint 0x7F00 (`fibre::kRawEndpointBase`); `fibre-cpp/legacy_protocol.cpp` routes IDs from there up to `fibre::raw_endpoint_handler`.

## Toolchain
`main` (v0.5.6) builds with GNU Arm Embedded **10.3-2021.10** (GCC 10.3.1), the version v0.5.6's CI used (Ubuntu's `gcc-arm-none-eabi`). Only an Intel build exists for macOS; it runs under Rosetta 2.
```sh
mkdir -p ~/.local/arm/dl && cd ~/.local/arm/dl
curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
md5 gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2          # 7f2a7b7b23797302a9d6182c6e482449
cd .. && tar -xjf dl/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
```
The build looks for it in `~/.local/arm/gcc-arm-none-eabi-10.3-2021.10/bin/`. Override with `TOOLCHAIN=<dir>/`. On Linux, use the `x86_64-linux` archive from the same release. The tag `xdrive/v0.5.1` uses Makerbase's compiler, 7-2018-q2-update (`.../7-2018q2/gcc-arm-none-eabi-7-2018-q2-update-mac.tar.bz2`, md5 a66be9828cf3c57d7d21178e07cd8904). The code generators need `uv`; the Makefile creates `xdrive/.venv` from `requirements.txt` by itself.

## Build
```sh
make -C xdrive -j8          # -> Firmware/build/ODriveFirmware.{elf,hex,bin,map}
make -C xdrive asm          # disassembly -> Firmware/build/ODriveFirmware.asm
make -C xdrive clean
```
- **Why not tup:** ODrive builds with tup, which needs FUSE, and macOS doesn't have it. `sources.mk` transcribes the v3.6-56V board configuration from `Firmware/Tupfile.lua`: sources, include order and package flags. `firmware.mk` adds Tupfile.lua's global flags.
- **Adding a source file:** add it to the right list in `sources.mk`.
- **Version:** `tools/odrive/version.py` takes it from `git describe --match=*fw*` (see Versioning in the top-level README).

## At tag `xdrive/v0.5.1`: byte-identical to Makerbase's firmware
These instructions apply to a checkout of the tag (its `firmware.mk` has `MAKERBASE_VERSION`/`LIB_OVERRIDE`).
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
`xdrive/tools/usb_flash.py` (USB DFU) and `xdrive/tools/swd_flash.py` (ST-Link and OpenOCD) share the same checks:
- **Before writing:** the axis goes IDLE, and the whole flash is read twice (the reads must match) and saved under `backups/`, reusing an identical existing backup. `swd_flash.py` also checks that the SWD and USB serials match.
- **Write:** erases only the sectors the image covers. The config lives in sectors 10–11, so it stays.
- **Read-back:** the whole flash is read and checked: the image must match, and sectors outside the erased ones must be unchanged. `usb_flash.py` stays in the bootloader on a mismatch and prints the restore command.
- **Afterwards:** Motor moves: the board reboots and its startup sequence runs.
- **SWD wiring:** J2 GND/SWCLK/SWDIO, plus NRST (J2 pin 5) to the ST-Link's RST, so a crashed build can still be reached with connect-under-reset.
- **Never written:** the option bytes (read and write protection).

## Releasing
Pushing a tag `fw-vX.Y.Z` releases X.Y.Z: CI (`.github/workflows/build.yml`) checks that `CHANGELOG.md` has a dated section for X.Y.Z, builds, checks that the firmware reports exactly X.Y.Z (`fw_version_unreleased = 0`), and publishes a GitHub release named "xdrive-robotics X.Y.Z" with `xdrive-robotics-X.Y.Z.{elf,bin,hex}`, `SHA256SUMS` and the changelog section as its notes. A failed check publishes nothing.
1. In `CHANGELOG.md`, change the section's heading from `Unreleased` to the release date: `## xdrive-robotics [X.Y.Z] - YYYY-MM-DD`.
2. `python xdrive/tools/release_notes.py X.Y.Z` (prints the release notes, or what is missing).
3. Commit and push `main`.
4. `git tag fw-vX.Y.Z`
5. `git push origin fw-vX.Y.Z`
6. Afterwards, start the next section: `## xdrive-robotics [X.Y.Z+1] - Unreleased` (or the next minor or major, per the versioning rules in the top-level README).
