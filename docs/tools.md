# Host tools

The scripts in `tools/` flash, configure, calibrate and bench-test a board. They all use the [Python library](python-library.md) (`tools/xdrive`) and talk only to this firmware. This page lists them and the conventions they share; each tool's docstring (`python tools/<tool>.py --help`) gives its full usage.

## Conventions

- **Setup:** `make venv`, then `source .venv/bin/activate` ([Getting started](getting-started.md#install-the-host-tools)).
- **Run from the repository root.** The tools write logs to `logs/` and flash backups to `backups/` under the working directory, creating the folders as needed; `regress.py` keeps its baselines in `configs/`. Changes to a board are appended to `logs/actions.jsonl`.
- **"Motor moves"** marks a tool that drives the motor or reboots the board (a reboot runs the startup sequence, which can calibrate or enter closed loop). Keep `python tools/idle.py` ready.
- **Test settings are RAM only:** the bench tools set what they need, restore the previous values and end with the axis IDLE. Nothing is saved unless a tool says so (`--save`).
- **One USB client at a time:** while one tool holds the board's USB interface, another fails with "can't claim the interface".

## Configure and inspect

| Tool | What it does |
|---|---|
| `dump_board.py [--label L] [--compare F]` | Read-only snapshot of every property with decoded errors, plus a config backup that `set_config.py --file` restores; `--compare` diffs the board against a settings file |
| `set_config.py [--save] [--file F] path=value ...` | Changes settings: refuses unless the axis is IDLE, dumps first, writes, reads back. `--save` saves (the board reboots: motor moves) and reports a failed store |
| `idle.py` | The stop command: puts axis0 in IDLE and prints the errors |
| `calibrate.py --motor --offset [--correction] [--save]` | Motor moves. Motor, encoder offset and correction-table calibration, one state at a time, with the results |
| `correction_table.py [--show \| --save-json F \| --load-json F \| --smooth H]` | Reads, saves, restores or smooths the [encoder correction table](encoders.md#correction-table); writes are RAM only until saved |
| `reboot_watch.py` | Motor moves. Reboots and prints the startup state transitions, the offset calibration result and errors |
| `sample.py [--duration S]` | Read-only sampler over USB, about 340 samples per second |
| `capture.py field ... [--trigger 'field>level'] [--post N] [--decimation N]` | Records up to 8 properties at 8 kHz with the firmware's [capture](capture.md); read-only for the axis |

## Flashing

| Tool | What it does |
|---|---|
| `usb_flash.py (--elf F \| --bin F) [--write]` | Motor moves (every run, the dry run included, ends with a reboot). Flashes over USB through the STM32's built-in DFU bootloader; no probe needed |
| `swd_flash.py (--elf F \| --bin F) [--write] [--no-usb]` | Motor moves (reboot). Flashes over SWD with an ST-Link and OpenOCD |
| `can_flash.py (--elf F \| --bin F) [--node N \| --serial S] [--write]` | The motor goes limp, then the startup runs. Updates the firmware over CAN through the [CAN bootloader](bootloader.md#updating-over-can) |
| `swd_backup.py [--probe]` | Read-only whole-flash backup over SWD, without halting the core |

Without `--write`, each flash tool runs dry: it finds the board, backs up and compares, and writes nothing.

`usb_flash.py` and `swd_flash.py` share these checks:

- **Before writing:** the axis goes IDLE (a board on Makerbase's firmware must be put in the bootloader by hand: S2 held through a reset), and the whole flash is read twice (the reads must match) and saved under `backups/`, reusing an identical earlier backup. `swd_flash.py` also checks that the SWD and USB serial numbers match; `--no-usb` skips that, and the IDLE step, for a board that isn't on USB.
- **Write:** only the sectors the image covers are erased. The config lives in sectors 10 and 11, so it stays.
- **Bootloader check:** firmware linked behind the [CAN bootloader](bootloader.md) (at 0x08008000) is refused on a board without the bootloader in sectors 0 and 1, where it couldn't start. An image linked at 0x08000000, such as a backup's `flash.bin`, replaces the bootloader, with a note.
- **Read-back:** the whole flash is read and checked: the image must match, and every sector outside the erased ones must be unchanged. `usb_flash.py` stays in the bootloader on a mismatch and prints the restore command.
- **Never written:** the option bytes (read and write protection).
- **Restore:** `--bin backups/<dir>/flash.bin --write` writes a backup back, bootloader and config sectors included.

## Bench tests

These check the firmware's features on a real board with PASS/FAIL per check; [Testing](testing.md) describes what each one checks.

| Tool | Motion |
|---|---|
| `capture_test.py` | None |
| `safety_test.py [--tests watchdog,limits,following]` | Moves, about 1 min |
| `impedance_test.py` | Moves, about 25 s |
| `feedforward_test.py` | Moves, about 20 s |
| `regen_test.py` | Moves, about 35 s, with hard stops |
| `can_test.py [--interface I --channel C] [--node N] [--rate HZ] [--tests ...]` | Moves, about 75 s; the board reboots twice. Over a USB-CAN adapter |
| `regress.py --tag T [--compare F] [--baseline F \| --save-baseline] [--hold-at F]` | Moves, about 1 min. Regression suite; compares with a saved baseline only when given `--baseline` |

## Measurement and diagnostics

| Tool | What it does |
|---|---|
| `move_test.py --moves 1,2,5 [--label L]` | Motor moves. Out-and-back trapezoidal moves, logged at about 275 Hz; IDLE on any error, a following error over 0.25 turn or Ctrl-C. Test settings such as `--current-lim` and `--trap-vel` are RAM only |
| `move_to.py F` | Motor moves (one move of at most half a turn). Turns the rotor to fractional turn F and leaves it IDLE |
| `hold_ab.py --variant "A:key=val" --variant "B:key=val"` | Motor holds. Compares hold noise between setting variants |
| `disturb_test.py [--torque T]` | Motor moves about 1°. Steps a torque against the hold to measure stiffness and recovery |
| `hold_sweep.py --span S [--points N]` | Motor moves (small). Holding current and position error at evenly spaced angles, approached from both sides: separates position-dependent torque (cogging, gearbox detents) from static friction |
| `runin.py --speed V --minutes M` | Motor runs continuously. Constant-speed run-in that reverses at an interval, with stall, drag and temperature stops and a log per second; touching `logs/STOP` stops it |
| `demo.py [--loop N \| --spring [S]]` | Motor moves. Moves and a sine sweep in a loop, or with `--spring` only a spring to twist by hand |
| `profile_loop.py` | Motor holds. Time of each task in one control period, and thread stack headroom |
| `analyze_encoder.py`, `analyze_ripple.py`, `analyze_settle.py` | Offline analysis of the logs: raw encoder jumps, 4x-per-turn ripple, tracking and settling |
