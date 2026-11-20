# XDRIVE Mini firmware

Firmware for the MKS XDRIVE Mini (an ODrive v3.6 clone).
Everything outside `xdrive/` is ODrive's tree; `xdrive/` holds our build system, notes and
reference material.

## Branches and tags
- `upstream`: upstream ODrive snapshots, tagged `upstream/fw-v0.5.1` and `upstream/fw-v0.5.6`.
  They come from GitHub tarballs, so there's no upstream history. The 0.5.6 snapshot leaves out the
  five prebuilt `libfibre-*` tool binaries (Git LFS pointers only).
- `main`: **ODrive v0.5.6** (merged from `upstream` on 2026-11-18) + the Mini changes + our work.
  - Makerbase's v0.5.1 changes are commit 8ebfc62.
  - Tag `xdrive/v0.5.1` is the last v0.5.1-based state. It holds the byte-identical build described below.
- **Mini changes on v0.5.6:**
  - **Second DRV8301 marked not populated** (`-DXDRIVE_MINI`, `board.cpp`). v0.5.6 retries every idle motor's gate-driver setup every millisecond. For the missing second driver, that meant endless SPI traffic on the bus the encoder shares. This is the likely reason stock v0.5.6 "doesn't drive the Mini".
  - **AS5047 frame checks are configurable** (`encoder.config.abs_spi_check_parity`, `abs_spi_reject_error_flag`) with counters. The test-stand board's chip sends even parity in bit 15 (an AS5047P in practice), so its check is on.
  - **Makerbase's two other encoder patches were dropped:** v0.5.6 already makes a pre-calibrated SPI absolute encoder ready on its first valid read.
- **Features added on `main`**:
  - Encoder integrity: SPI frame diagnostics and impossible-jump rejection.
  - Encoder correction table (`AXIS_STATE_ENCODER_CORRECTION_CALIBRATION`, 256 bins, harmonics 1..12).
  - Watchdog `DECEL_HOLD` (`axis.config.watchdog_action`, `watchdog_decel`, `watchdog_torque_lim`; status in `controller.timeout_active`). Feed the watchdog, then `clear_errors()` to resume.
  - Soft position limits (`controller.config.pos_min`/`pos_max`, `pos_limit_margin`) and following-error faults (`max_pos_error`, `max_vel_error`). All off (infinite) by default.
  - Closed-loop entry starts from rest (zero velocity/torque setpoints, no running trajectory).
  - Impedance control (`CONTROL_MODE_IMPEDANCE_CONTROL` = 4): torque = `controller.input_kp`·pos error + `input_kd`·vel error + `input_torque`, no integrator.
  - CAN impedance command (CANSimple ID 0x1E: position, velocity, kp, kd, torque in 8 bytes) with an immediate reply on the same ID (position, velocity, measured torque, flags, FET temperature, bus voltage). Layout: `Firmware/communication/can/impedance_frame.hpp`; full scales: `axis.config.can.impedance_*`.
  - High-rate capture (`odrv.capture`, replacing the hard-wired oscilloscope): up to 8 properties by endpoint ID into a 32 KiB RAM buffer at the 8 kHz control rate (or decimated), with a level, manual or immediate trigger. The buffer is read in bulk from fibre endpoint 0x7F00 (`fibre::kRawEndpointBase`; `fibre-cpp/legacy_protocol.cpp` routes IDs from there up to `fibre::raw_endpoint_handler`). Host tool: `capture.py`.

## Toolchain
`main` (v0.5.6) builds with GNU Arm Embedded **10.3-2021.10** (GCC 10.3.1), the version v0.5.6's CI
used (Ubuntu's `gcc-arm-none-eabi`). Only an Intel build exists for macOS; it runs under Rosetta 2.
```sh
mkdir -p ~/.local/arm/dl && cd ~/.local/arm/dl
curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
md5 gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2          # 7f2a7b7b23797302a9d6182c6e482449
cd .. && tar -xjf dl/gcc-arm-none-eabi-10.3-2021.10-mac.tar.bz2
```
The build looks for it in `~/.local/arm/gcc-arm-none-eabi-10.3-2021.10/bin/`. Override with
`TOOLCHAIN=<dir>/`. The tag `xdrive/v0.5.1` uses Makerbase's compiler, 7-2018-q2-update
(`.../7-2018q2/gcc-arm-none-eabi-7-2018-q2-update-mac.tar.bz2`, md5 a66be9828cf3c57d7d21178e07cd8904). The code generators need `uv`; the Makefile creates
`xdrive/.venv` from `requirements.txt` by itself.

## Build
```sh
make -C xdrive -j8          # -> Firmware/build/ODriveFirmware.{elf,hex,bin,map}
make -C xdrive asm          # disassembly -> Firmware/build/ODriveFirmware.asm
make -C xdrive clean
```
- **Why not tup:** ODrive builds with tup, which needs FUSE, and macOS doesn't have it.
  `sources.mk` transcribes the v3.6-56V board configuration from `Firmware/Tupfile.lua`: sources,
  include order and package flags. `firmware.mk` adds Tupfile.lua's global flags and `-DXDRIVE_MINI`.
- **Adding a source file:** add it to the right list in `sources.mk`.
- **Version:** taken from `git describe` (e.g. 0.5.6-dev).

## At tag `xdrive/v0.5.1`: byte-identical to Makerbase's firmware (verified 2026-11-18)
These instructions apply to a checkout of the tag (its `firmware.mk` has `MAKERBASE_VERSION`/`LIB_OVERRIDE`).
```sh
# The Windows release's target libraries; Makerbase linked against these.
cd ~/.local/arm/dl && curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/7-2018q2/gcc-arm-none-eabi-7-2018-q2-update-win32.zip
mkdir -p win && cd win && unzip -q ../gcc-arm-none-eabi-7-2018-q2-update-win32.zip \
  'arm-none-eabi/lib/thumb/v7e-m/fpv4-sp/hard/*' 'lib/gcc/arm-none-eabi/7.3.1/thumb/v7e-m/fpv4-sp/hard/*'
make -C xdrive MAKERBASE_VERSION=1 LIB_OVERRIDE=$HOME/.local/arm/dl/win clean verify-makerbase
```
The `.bin` and `.hex` are then identical to `reference/makerbase-20250326/`. That build is
what the test-stand board runs: it matches the 2026-11-18 SWD backup except the 8-byte gap after
the vector table, which isn't programmed from a hex.
- **Why the Windows libraries:** the Mac and Windows releases ship different `libc`, `libstdc++`
  and `libgcc` archives, with members in a different order. With the Mac ones, every section from
  our own sources lands at the same address and size, but library code is ordered differently.
- **What this proves:** the sources, generated code, flags, link order and compiler reproduce the
  running firmware exactly, so any change from here on is only what we add.

## Flashing
Flash over SWD (ST-Link + OpenOCD) with `swd_flash.py`.
```sh
cd <tools directory>
python scripts/swd_flash.py --elf ../firmware/Firmware/build/ODriveFirmware.elf           # dry run
python scripts/swd_flash.py --elf ../firmware/Firmware/build/ODriveFirmware.elf --write   # flash
python scripts/swd_flash.py --bin firmware/backups/<dir>/flash.bin --write                 # restore a backup
```
- **Checks:** the SWD and USB serials must match. The script sets IDLE and takes a pre-flash
  backup, reusing an identical existing one.
- **Write:** erases only the sectors the image covers. The config lives in sectors 10–11, so it
  stays. Then it verifies and resets: ⚠️ the board reboots and calibrates, and the motor moves.
- **Read-back:** reads the whole flash and checks it.
- **Wiring:** J2 GND/SWCLK/SWDIO, plus NRST to the ST-Link's RST, so a crashed build can still be
  reached with connect-under-reset.

**Round trip, 2026-11-18:** flashed the byte-identical build (`MAKERBASE_VERSION=1 LIB_OVERRIDE=…`).
- 233,024 bytes written in 6.5 s and verified.
- The read-back was clean. The only change on the chip was the vector-table gap (`FF` → `00`), so it
  now equals Makerbase's `.bin` exactly.
- The board rebooted, calibrated and reached closed loop, with no errors and its config unchanged.
