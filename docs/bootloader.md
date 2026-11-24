# CAN bootloader

A board with the CAN bootloader takes firmware updates over its CAN bus, so boards built into a machine update without USB or SWD. The STM32F405's built-in bootloader speaks CAN only on CAN2 (PB5 and PB13), not on the Mini's CAN1 pins (PB8 and PB9), so this firmware brings its own: a 4 KB program in the first two flash sectors. The built-in bootloader stays available: USB DFU (`tools/usb_flash.py`, or holding S2 through a reset) and SWD recover a board whatever its flash holds.

## Flash layout

| Sectors | Address | Size | Contents |
|---|---|---|---|
| 0-1 | 0x08000000 | 32 KB | the CAN bootloader; never written over CAN |
| 2-9 | 0x08008000 | 736 KB | the firmware, with an image header at 0x08008200 |
| 10-11 | 0x080C0000 | 256 KB | the config; untouched by updates |

The build links the firmware at 0x08008000 and seals it (`tools/seal_image.py`): the image header gets the image's length, its CRC-32 and the firmware version. `build/firmware.elf`, `.bin` and `.hex` hold the same bytes. `build/bootloader.elf` is the bootloader, and `build/firmware-with-bootloader.bin` both together from 0x08000000.

## What the bootloader does at a reset

1. After a reset it caused itself to start the firmware, it starts the firmware at once.
2. It checks the firmware's header and CRC (about 18 ms).
3. It stays and serves the bus when the firmware asked for it (`enter_can_bootloader()`) or when the image doesn't check out.
4. After a power-up, it listens 100 ms at 1 Mbit/s for a DISCOVER; one holds it in the bootloader.
5. Otherwise it starts the firmware, by resetting into step 1, so the firmware starts from a reset's state.

The gate driver stays off throughout: the motor is limp while the bootloader runs.

## Moving a board onto the bootloader (once, over USB)

```sh
make                                                   # builds the bootloader, the firmware and the combined image
python tools/usb_flash.py --bin build/firmware-with-bootloader.bin          # dry run: backup and compare
python tools/usb_flash.py --bin build/firmware-with-bootloader.bin --write  # writes sectors 0-6; the config stays
```

From then on, `usb_flash.py --elf build/firmware.elf` and `can_flash.py` both replace only the firmware. `usb_flash.py` and `swd_flash.py` refuse to write firmware linked at 0x08008000 to a board without the bootloader, which would leave it unable to start. Flashing an image linked at 0x08000000, such as an older release or a backup's `flash.bin`, replaces the bootloader: the way back.

## Updating over CAN

```sh
python tools/can_flash.py --elf build/firmware.elf --node 0 --interface slcan --channel /dev/cu.usbmodemX           # dry run
python tools/can_flash.py --elf build/firmware.elf --node 0 --interface slcan --channel /dev/cu.usbmodemX --write
```

`--node` reaches a board running its firmware: it calls `enter_can_bootloader()` (refused while the motor is armed), finds the board in the bootloader, erases, writes the image in 1 KB blocks with a CRC each (a block the board rejects is sent again), verifies the whole image, starts it and checks the version the board then reports. `--serial` reaches a board already in the bootloader: one whose firmware doesn't start, or one held there at power-up. The bootloader runs at the bit rate the firmware passed on, or at 1 Mbit/s after a power-up.

If an update stops partway, the board's image fails its CRC and the board waits in the bootloader: run `can_flash.py` again, with `--serial` (the serial number is in `can_flash.py`'s output and the logs).

## Protocol

29-bit CAN IDs, which CANSimple's 11-bit IDs never collide with; each carries the low 20 bits of the board's serial number, so boards in the bootloader never send the same ID. The commands are DISCOVER, ERASE, BLOCK_START, DATA, BLOCK_END, VERIFY and START_APP; `src/bootloader/boot_protocol.hpp` documents the frames, and `tools/xdrive/boot_frame.py` is the host codec.

The bootloader itself is updated only over USB or SWD, so a failed update never touches the part that recovers a board over CAN.
