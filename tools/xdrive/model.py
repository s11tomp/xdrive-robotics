"""Typed handles for the board's properties and functions.

The generated module `xdrive.props` builds the tree of these handles (`odrv.axis0.encoder.pos_estimate`)
from src/odrive-interface.yaml. A handle holds only a dotted path and the Python type of its value: a
`Board` looks the path up in the board's interface JSON for the endpoint ID and wire type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, NamedTuple, TypeVar

T = TypeVar("T")


class EndpointRef(NamedTuple):
    """An `endpoint_ref` property's value: an endpoint ID and the interface JSON's CRC-16 it belongs to."""
    endpoint_id: int
    json_crc: int


class Prop(Generic[T]):
    """A property the host can read."""
    __slots__ = ("path", "kind")

    def __init__(self, path: str, kind: type[T]) -> None:
        self.path = path
        self.kind: type[Any] = kind

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path!r}, {self.kind.__name__})"


class RwProp(Prop[T]):
    """A property the host can read and write."""
    __slots__ = ()


@dataclass(frozen=True)
class Arg:
    name: str
    kind: type[Any]


class Func(Generic[T]):
    """A function on the board; T is what `Board.call` returns (None, one value or a tuple).

    The generated subclasses' `__call__` takes the function's arguments, typed, and returns a `Call`
    for `Board.call`.
    """
    __slots__ = ("path", "inputs", "outputs")

    def __init__(self, path: str, inputs: tuple[Arg, ...], outputs: tuple[Arg, ...]) -> None:
        self.path = path
        self.inputs = inputs
        self.outputs = outputs

    def __repr__(self) -> str:
        return f"Func({self.path!r})"


@dataclass(frozen=True)
class Call(Generic[T]):
    """A function with its arguments, ready for `Board.call`."""
    func: Func[T]
    args: tuple[Any, ...]
