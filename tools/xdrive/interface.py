"""The board's interface JSON: endpoint IDs and wire types by dotted name, and the on-disk cache.

The firmware embeds its interface JSON and serves it as endpoint 0's buffer. Its version ID (offset
0xFFFFFFFF of that buffer) is two CRC-16s over the JSON: the high half is the CRC that every USB
packet's trailer carries. The cache keeps one file per version ID under ~/.cache/xdrive (or
$XDG_CACHE_HOME/xdrive), so a board's JSON crosses the link once per firmware build.
"""
from __future__ import annotations

import json
import os
import pathlib
import struct
import warnings
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1           # the CRC seed, and endpoint 0's USB trailer
CRC16_POLYNOMIAL = 0x3D65
JSON_ENDPOINT = 0
VERSION_OFFSET = 0xFFFFFFFF    # endpoint 0 at this offset reads the version ID

# Wire type (the JSON's "type") -> struct format, little-endian.
FORMATS = {"float": "<f", "bool": "<?", "uint8": "<B", "uint16": "<H", "uint32": "<I", "int32": "<i",
           "uint64": "<Q", "int64": "<q", "endpoint_ref": "<HH"}


def crc16(data: bytes, remainder: int) -> int:
    """fibre's CRC-16: polynomial 0x3D65, MSB first, no reflection, no final XOR."""
    for byte in data:
        remainder ^= byte << 8
        for _ in range(8):
            remainder = ((remainder << 1) ^ CRC16_POLYNOMIAL if remainder & 0x8000 else remainder << 1) & 0xFFFF
    return remainder


def version_id(data: bytes) -> int:
    crc = crc16(data, PROTOCOL_VERSION)
    return crc << 16 | crc16(data, crc)


@dataclass(frozen=True)
class Endpoint:
    id: int
    type: str        # a FORMATS key
    writable: bool


@dataclass(frozen=True)
class Function:
    id: int
    inputs: tuple[tuple[str, Endpoint], ...]
    outputs: tuple[tuple[str, Endpoint], ...]


class Interface:
    """The parsed JSON: `properties` and `functions` by dotted name ('axis0.encoder.pos_estimate')."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.version_id = version_id(data)
        self.properties: dict[str, Endpoint] = {}
        self.functions: dict[str, Function] = {}
        self._walk(json.loads(data), "")

    def _walk(self, members: list[dict[str, Any]], prefix: str) -> None:
        for m in members:
            name = prefix + m["name"]
            if m["type"] == "object":
                self._walk(m["members"], name + ".")
            elif m["type"] == "function":
                self.functions[name] = Function(m["id"], *(tuple((a["name"], self._endpoint(a)) for a in m[k])
                                                           for k in ("inputs", "outputs")))
            elif m["type"] != "json":
                self.properties[name] = self._endpoint(m)

    @staticmethod
    def _endpoint(m: dict[str, Any]) -> Endpoint:
        if m["type"] not in FORMATS:
            raise ValueError(f"interface JSON: unknown type {m['type']!r} for {m['name']!r}")
        return Endpoint(m["id"], m["type"], "w" in m.get("access", "rw"))


def cache_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_CACHE_HOME") or pathlib.Path.home() / ".cache") / "xdrive"


def cached(vid: int) -> bytes | None:
    """The cached JSON for this version ID, or None. A file whose content doesn't match its ID is ignored."""
    path = cache_dir() / f"interface-{vid:08x}.json"
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data if version_id(data) == vid else None


def store(data: bytes) -> None:
    """Caches the JSON; a cache that can't be written only warns, and the next connect reads the JSON again."""
    path = cache_dir() / f"interface-{version_id(data):08x}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError as ex:
        warnings.warn(f"xdrive: can't cache the interface JSON in {path.parent}: {ex}", stacklevel=2)


def unpack_u32(data: bytes) -> int:
    return int(struct.unpack_from("<I", data)[0])
