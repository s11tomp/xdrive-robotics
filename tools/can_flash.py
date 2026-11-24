#!/usr/bin/env python3
"""Update a board's firmware over CAN, through its CAN bootloader.  *** The board resets into the bootloader
and back: the motor goes limp during the update, and its startup sequence runs afterwards ***

  1. The image: a firmware ELF (the build seals build/firmware.elf) or a .bin starting at the application's
     address; its header and CRC must check out, as the bootloader checks them before starting it.
  2. The board:
       --node N    a board running its application: enter_can_bootloader() over CAN (refused while the
                   motor is armed, or by a board without the bootloader), then a DISCOVER finds it in the
                   bootloader by its node ID
       --serial S  a board already in the bootloader: one whose application can't start, or one held
                   there at power-up by a DISCOVER within its 100 ms window
     Without either, the only board found in the bootloader.
  3. Dry run (no --write): VERIFY reports whether the board's current image is valid, then START_APP.
  4. --write: ERASE, the image in 1 KB blocks (a block the board rejects or doesn't answer is sent again,
     up to RETRIES times), VERIFY, START_APP.
  5. With a node ID: waits for the board's heartbeat and checks the firmware version it reports.
Logs to logs/actions.jsonl. Recovery when this fails: the board stays in the bootloader, so run it again
(with --serial if the application never came back); USB DFU and SWD always work as well.

Usage (from the repo root):
  python tools/can_flash.py --elf build/firmware.elf --node 0 [--write] [--interface slcan --channel /dev/cu.usbmodemX]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys
import time
from typing import Any

import can as python_can

import seal_image
from xdrive import boot_frame as bf
from xdrive import can
from xdrive.errors import InterfaceMismatch, LinkError, LinkLost, LinkTimeout
from xdrive.props import odrv

WORKDIR = pathlib.Path.cwd()  # logs/ goes under the working directory
LOGS = WORKDIR / "logs"
RETRIES = 3
ERASE_TIMEOUT = 30.0      # s: erasing all eight application sectors takes up to about 16 s
ANSWER_TIMEOUT = 1.0      # s: any other answer
ENTER_TIMEOUT = 3.0       # s: from enter_can_bootloader() to the board answering DISCOVER
START_TIMEOUT = 15.0      # s: from START_APP to the application's heartbeat


class Failed(Exception):
    pass


def load_image(args: argparse.Namespace) -> tuple[bytes, pathlib.Path]:
    path = pathlib.Path(args.elf or args.bin)
    raw = path.read_bytes()
    image = seal_image.flash_image(raw) if args.elf else raw
    if not bf.header_valid(image):
        raise Failed(f"{path}: no valid image header (magic, hardware, length, CRC): the bootloader wouldn't start it")
    return image, path


def answer(bus: can.Bus, serial: int, cmd: bf.Cmd, timeout: float) -> bytes | None:
    """The data of the board's next answer to `cmd`, or None after `timeout`."""
    end = time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        got = bus.recv_extended(left)
        if got is None:
            return None
        i = bf.parse_id(got[0])
        if i.ours and i.from_board and i.cmd == cmd and i.serial20 == bf.serial20(serial):
            return got[1]
    return None


def request(bus: can.Bus, serial: int, frame: tuple[int, bytes], cmd: bf.Cmd, timeout: float = ANSWER_TIMEOUT) -> bytes:
    bus.drain_extended()
    bus.send_raw(*frame, extended=True)
    data = answer(bus, serial, cmd, timeout)
    if data is None:
        raise Failed(f"no answer to {cmd.name} within {timeout:g} s")
    return data


def discover(bus: can.Bus, timeout: float = 0.3) -> list[bf.Discovered]:
    """Every board in the bootloader that answers a broadcast DISCOVER within `timeout`."""
    bus.drain_extended()
    bus.send_raw(*bf.discover(), extended=True)
    found: dict[int, bf.Discovered] = {}
    end = time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        got = bus.recv_extended(left)
        if got is None:
            break
        i = bf.parse_id(got[0])
        if i.ours and i.from_board and i.cmd == bf.Cmd.DISCOVER and len(got[1]) == 8:
            d = bf.decode_discover(got[1])
            found[d.serial] = d
    return sorted(found.values(), key=lambda d: d.serial)


def enter_bootloader(bus: can.Bus, node: int) -> None:
    """enter_can_bootloader() on the node's application; the board resets before it can answer."""
    if bus.heartbeat(node) is None and node not in bus.scan(0.3):
        raise Failed(f"no heartbeat from node {node}: is its application running? (a board already in the "
                     "bootloader is found with --serial, or without --node)")
    board = bus.connect(node)
    try:
        ok = board.call(odrv.enter_can_bootloader())
    except InterfaceMismatch as ex:
        raise Failed(f"node {node}'s firmware has no enter_can_bootloader(): update it over USB once ({ex})") from None
    except (LinkTimeout, LinkLost):
        ok = True  # the reset came before the answer
    finally:
        board.close()
    if not ok:
        raise Failed(f"node {node} refused enter_can_bootloader(): its motor is armed, or it has no CAN bootloader")


def find_board(bus: can.Bus, node: int | None, serial: int | None) -> bf.Discovered:
    if node is not None:
        enter_bootloader(bus, node)
        end = time.monotonic() + ENTER_TIMEOUT
        while time.monotonic() < end:
            hits = [d for d in discover(bus) if d.node_id == node]
            if hits:
                return hits[0]
        raise Failed(f"node {node} didn't answer in the bootloader within {ENTER_TIMEOUT:g} s")
    found = discover(bus)
    if serial is not None:
        hits = [d for d in found if d.serial == serial]
        if not hits:
            raise Failed(f"no board with serial {serial:X} in the bootloader (found: {[f'{d.serial:X}' for d in found]})")
        return hits[0]
    if len(found) != 1:
        raise Failed(f"{len(found)} boards in the bootloader ({[f'{d.serial:X}' for d in found]}): pass --serial or --node")
    return found[0]


def write_image(bus: can.Bus, serial: int, image: bytes, block_size: int, record: dict[str, Any]) -> None:
    s = bf.status(request(bus, serial, bf.erase(serial, len(image)), bf.Cmd.ERASE, ERASE_TIMEOUT))
    if s is not bf.Status.OK:
        raise Failed(f"ERASE: {s.name}")
    padded = image + b"\xff" * (-len(image) % 4)
    retries, shown = 0, -1
    t0 = time.monotonic()
    for off in range(0, len(padded), block_size):
        data = padded[off:off + block_size]
        for attempt in range(RETRIES + 1):
            bus.drain_extended()
            for frame in bf.block(serial, off, data):
                bus.send_raw(*frame, extended=True)
            got = answer(bus, serial, bf.Cmd.BLOCK_END, ANSWER_TIMEOUT)
            result = None if got is None else bf.decode_block_end(got)
            if result == (bf.Status.OK, off):
                break
            why = "no answer" if result is None else f"{result[0].name} at offset {result[1]}"
            if attempt == RETRIES:
                raise Failed(f"block at offset {off}: {why}, {RETRIES + 1} times")
            retries += 1
            print(f"  block at offset {off}: {why}; sending it again")
        pct = 100 * (off + len(data)) // len(padded)
        if pct // 10 != shown:
            shown = pct // 10
            print(f"  {pct:3d} %  {off + len(data)} of {len(padded)} bytes, {time.monotonic() - t0:.1f} s")
    record.update(write_s=round(time.monotonic() - t0, 1), block_retries=retries)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--elf", help="firmware ELF linked behind the bootloader (build/firmware.elf)")
    src.add_argument("--bin", help="firmware image starting at the application's address (build/firmware.bin)")
    who = ap.add_mutually_exclusive_group()
    who.add_argument("--node", type=int, help="node ID of a board running its application")
    who.add_argument("--serial", type=lambda s: int(s, 16), help="serial number (hex) of a board in the bootloader")
    ap.add_argument("--interface", default="gs_usb", help="python-can interface (default gs_usb: candleLight adapters)")
    ap.add_argument("--channel", default="0", help="python-can channel (gs_usb: any; slcan: the serial port)")
    ap.add_argument("--bitrate", type=int, default=1_000_000)
    ap.add_argument("--block-size", type=int, default=bf.BLOCK_MAX, help=f"bytes per block, a multiple of 8 up to {bf.BLOCK_MAX}")
    ap.add_argument("--write", action="store_true", help="erase and write (without it: a dry run)")
    args = ap.parse_args(argv)
    if not (8 <= args.block_size <= bf.BLOCK_MAX and args.block_size % 8 == 0):
        ap.error(f"--block-size must be a multiple of 8 up to {bf.BLOCK_MAX}")

    record: dict[str, Any] = {"t": datetime.datetime.now().astimezone().isoformat(),
                    "action": "can_flash" if args.write else "can_flash_dry_run", "node": args.node}
    try:
        image, path = load_image(args)
    except Failed as ex:
        print(f"REFUSED: {ex}")
        return 1
    h = bf.read_header(image)
    assert h is not None
    version = ".".join(map(str, h.fw_version[:3])) + ("-dev" if h.fw_version[3] else "")
    record.update(image=str(path), image_sha256=hashlib.sha256(image).hexdigest(), image_bytes=len(image),
                  image_version=version)
    print(f"Image {path}: {len(image)} bytes, CRC-32 0x{h.crc:08X}, firmware {version}")
    print("*** The board resets into the bootloader and back: the motor goes limp, then its startup sequence runs. ***")

    t0 = time.monotonic()
    try:
        opened = can.open(timeout=0.5, interface=args.interface, channel=args.channel, bitrate=args.bitrate)
    except python_can.CanError as ex:
        print(f"Can't open the CAN adapter (interface {args.interface}, channel {args.channel}): {ex}")
        return 1
    code = 0
    with opened as bus:
        try:
            d = find_board(bus, args.node, args.serial)
            record.update(serial=f"{d.serial:X}", requested=d.requested)
            print(f"Bootloader: board {d.serial:X}, node {d.node_id if d.node_id is not None else 'unknown'}, "
                  f"protocol {d.protocol_version}, current image {'valid' if d.image_valid else 'NOT valid'}")
            if d.protocol_version != bf.PROTOCOL_VERSION:
                raise Failed(f"the bootloader speaks protocol {d.protocol_version}, this tool {bf.PROTOCOL_VERSION}")
            if args.write:
                write_image(bus, d.serial, image, args.block_size, record)
            s, length = bf.decode_verify(request(bus, d.serial, bf.verify(d.serial), bf.Cmd.VERIFY))
            print(f"VERIFY: {s.name}" + (f", {length} bytes" if s is bf.Status.OK else ""))
            if args.write and (s is not bf.Status.OK or length != len(image)):
                raise Failed(f"VERIFY after writing: {s.name}, length {length} (image {len(image)})")
            if s is not bf.Status.OK:
                raise Failed("no valid image on the board: the board stays in the bootloader (run with --write)")
            s = bf.status(request(bus, d.serial, bf.start_app(d.serial), bf.Cmd.START_APP))
            if s is not bf.Status.OK:
                raise Failed(f"START_APP: {s.name}")
            print("START_APP: the application starts")
            node = args.node if args.node is not None else d.node_id
            if node is not None:
                end = time.monotonic() + START_TIMEOUT
                t_start = time.monotonic()
                while time.monotonic() < end:
                    hb = bus.heartbeat(node)
                    if hb is not None and hb.t > t_start:
                        break
                    time.sleep(0.05)
                else:
                    raise Failed(f"node {node} sent no heartbeat within {START_TIMEOUT:g} s of START_APP")
                board = bus.connect(node)
                try:
                    running = (board.get(odrv.fw_version_major), board.get(odrv.fw_version_minor),
                               board.get(odrv.fw_version_revision), board.get(odrv.fw_version_unreleased))
                finally:
                    board.close()
                record["running_version"] = list(running)
                if args.write and tuple(running) != h.fw_version:
                    raise Failed(f"node {node} runs firmware {running}, the image is {h.fw_version}")
                print(f"Node {node} is back: firmware {'.'.join(map(str, running[:3]))}, state {hb.state.name}")
            record["result"] = "OK"
            print(f"RESULT: OK ({time.monotonic() - t0:.1f} s)")
        except (Failed, LinkError) as ex:
            record["result"] = f"FAILED: {ex}"
            print(f"RESULT: FAILED: {ex}\n  The board stays in the bootloader if its image isn't valid: run this again "
                  "(--serial if its node ID is unknown); USB DFU and SWD always work.")
            code = 2
    record["total_s"] = round(time.monotonic() - t0, 1)
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "actions.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
