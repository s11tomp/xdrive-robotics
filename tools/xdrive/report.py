"""The axis's error flags, read and formatted for printing and for JSON logs."""
from __future__ import annotations

import enum
from typing import Any

from xdrive.board import Board
from xdrive.props import odrv


def errors(board: Board) -> dict[str, enum.IntFlag]:
    """axis0's error flags by component: axis, motor (64 bits), encoder, controller."""
    ax = odrv.axis0
    return {"axis": board.get(ax.error), "motor": board.get(ax.motor.error),
            "encoder": board.get(ax.encoder.error), "controller": board.get(ax.controller.error)}


def flag_names(value: enum.IntFlag) -> list[str]:
    return [str(m.name) for m in type(value) if m in value]


def unknown_bits(value: enum.IntFlag) -> int:
    known = 0
    for m in type(value):
        known |= m.value
    return int(value) & ~known


def jsonable(value: enum.IntFlag) -> dict[str, Any]:
    """{"hex", "flags"[, "unknown_bits"]}: every bit, at the property's full width."""
    out: dict[str, Any] = {"hex": f"0x{int(value):08X}", "flags": flag_names(value)}
    if unknown_bits(value):
        out["unknown_bits"] = f"0x{unknown_bits(value):08X}"
    return out


def line(value: enum.IntFlag) -> str:
    """'0x00000041 INVALID_STATE | MOTOR_FAILED', with any bits the class doesn't name."""
    parts = flag_names(value) + ([f"unknown 0x{unknown_bits(value):X}"] if unknown_bits(value) else [])
    return f"0x{int(value):08X} {' | '.join(parts)}".rstrip()
