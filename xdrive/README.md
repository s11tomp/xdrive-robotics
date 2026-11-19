# XDRIVE Mini firmware

Firmware for the MKS XDRIVE Mini (an ODrive v3.6 clone).
Everything outside `xdrive/` is ODrive's tree; `xdrive/` holds our build system, notes and
reference material.

## Branches and tags
- `upstream`: upstream ODrive snapshots, tagged `upstream/fw-v0.5.1` and `upstream/fw-v0.5.6`.
  They come from GitHub tarballs, so there's no upstream history. The 0.5.6 snapshot leaves out the
  five prebuilt `libfibre-*` tool binaries (Git LFS pointers only).
- `main`: `upstream/fw-v0.5.1` + Makerbase's fw-v0.5.1-20250326 changes (one commit) + our work.
  To port our work to 0.5.6: `git rebase --onto upstream/fw-v0.5.6 upstream/fw-v0.5.1 <branch>`.

## Toolchain
GNU Arm Embedded **7-2018-q2-update** (GCC 7.3.1), the compiler Makerbase used. Only an Intel
build exists for macOS; it runs under Rosetta 2.
```sh
mkdir -p ~/.local/arm/dl && cd ~/.local/arm/dl
curl -LO https://developer.arm.com/-/media/Files/downloads/gnu-rm/7-2018q2/gcc-arm-none-eabi-7-2018-q2-update-mac.tar.bz2
md5 gcc-arm-none-eabi-7-2018-q2-update-mac.tar.bz2      # a66be9828cf3c57d7d21178e07cd8904
cd .. && tar -xjf dl/gcc-arm-none-eabi-7-2018-q2-update-mac.tar.bz2
```
The build looks for it in `~/.local/arm/gcc-arm-none-eabi-7-2018-q2-update/bin/`. Override with
`TOOLCHAIN=<dir>/` to use another compiler. The code generators need `uv`; the Makefile creates
`xdrive/.venv` from `requirements.txt` by itself.

## Build
```sh
make -C xdrive -j8          # -> Firmware/build/ODriveFirmware.{elf,hex,bin,map}
make -C xdrive asm          # disassembly -> Firmware/build/ODriveFirmware.asm
make -C xdrive clean
```
- **Why not tup:** ODrive builds with tup, which needs FUSE, and macOS doesn't have it. `firmware.mk`
  replays the commands from tup's database in Makerbase's archive instead: same flags, defines and
  include order. `sources.mk` holds the source lists, in their link order.
- **Adding a source file:** add it to `LINK_SRCS` and to the `*_SRCS` list for its flag set
  (`BOARD_C` = ST HAL / board, `ODRIVE_C`, `CXX`, `ASM`).
- **Version:** default builds take it from `git describe` and report fw 0.5.1 (unreleased).
  Makerbase's build reports 0.0.0.

## Verified: byte-identical to the board's firmware (2026-11-18)
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
