"""The interface every transport (USB, CAN) offers `Board`: four operations on an endpoint ID.

Values are raw little-endian bytes; `Board` packs and unpacks them by the interface JSON's types.
Failures raise `LinkTimeout` or `LinkLost` (transport) or `Refused` (the board answered, but no).
"""
from __future__ import annotations

from typing import Protocol


class Link(Protocol):
    def describe(self) -> str:
        """The board's address on this link, for messages: 'USB 0123456789AB', 'CAN node 1'."""
        ...

    def read(self, endpoint_id: int, size: int) -> bytes:
        """A property's value: exactly `size` bytes."""
        ...

    def write(self, endpoint_id: int, data: bytes) -> bytes:
        """Writes a property; returns its value read back after the write, `len(data)` bytes."""
        ...

    def call(self, endpoint_id: int) -> None:
        """Runs a function whose input endpoints are already written."""
        ...

    def read_buffer(self, endpoint_id: int, offset: int) -> bytes:
        """Bytes of a buffer endpoint (the JSON, the capture readout) from `offset`; empty or zeros past its end."""
        ...

    def reconnect(self, timeout: float) -> None:
        """Waits for the same board to answer again, after a reboot."""
        ...

    def close(self) -> None:
        ...
