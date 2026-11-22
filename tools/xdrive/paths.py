"""Properties by dotted path, with plain values: for tools that list properties as strings (CSV
columns, settings files, saved configs) and log raw numbers.

    from xdrive import paths
    paths.get(board, "axis0.current_state")        # 8, not AxisState.CLOSED_LOOP_CONTROL
    paths.set(board, "axis0.controller.config.control_mode", 3)

`get` returns an enum's or a flag's integer value, including a value this build's enum lacks
(a setting saved by another build); `set` converts a number or bool to the property's type
(an int to its enum), so a settings file can hold plain JSON values.
"""
from __future__ import annotations

import enum
from typing import Any

from xdrive.board import Board
from xdrive.errors import InterfaceMismatch
from xdrive.model import Func, Prop, RwProp
from xdrive.props import odrv


def _walk(obj: object, out: dict[str, Prop[Any]]) -> dict[str, Prop[Any]]:
    for value in vars(obj).values():
        if isinstance(value, Prop):
            out[value.path] = value
        elif not isinstance(value, Func):
            _walk(value, out)
    return out


HANDLES = _walk(odrv, {})


def prop(path: str) -> Prop[Any]:
    try:
        return HANDLES[path]
    except KeyError:
        raise KeyError(f"no property {path!r} in xdrive.props") from None


def rw(path: str) -> RwProp[Any]:
    p = prop(path)
    if not isinstance(p, RwProp):
        raise KeyError(f"{path} is read-only")
    return p


def plain(value: Any) -> Any:
    """An enum or flag as its integer; other values unchanged."""
    if isinstance(value, enum.Flag):
        return int(value)  # type: ignore[call-overload]
    if isinstance(value, enum.Enum):
        return value.value
    return value


def typed(p: Prop[Any], value: Any) -> Any:
    """A plain JSON value as the property's type: int -> enum, int -> float. bool stays strict."""
    kind = p.kind
    if issubclass(kind, enum.Enum) and not isinstance(value, kind):
        return kind(value)
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def get(board: Board, path: str) -> Any:
    p = prop(path)
    try:
        return plain(board.get(p))
    except InterfaceMismatch:
        if not issubclass(p.kind, enum.Enum):
            raise
        return board.get(type(p)(p.path, int))  # an enum value this build lacks: its number


def set(board: Board, path: str, value: Any) -> Any:  # noqa: A001
    """Writes the property; returns the plain value read back."""
    p = rw(path)
    return plain(board.set(p, typed(p, value)))


def read(board: Board, props: list[Prop[Any]]) -> list[Any]:
    """Plain values, one read each, in order (a CSV row)."""
    return [plain(board.get(p)) for p in props]
