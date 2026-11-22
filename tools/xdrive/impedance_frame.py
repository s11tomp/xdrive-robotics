"""Codec for the CANSimple impedance command (MSG_IMPEDANCE) and its reply. No I/O.

Mirror of the firmware's src/communication/can/impedance_frame.hpp; tests/test_impedance_frame.py
compiles that header and checks both against each other.

Command, 8 bytes, big-endian bit fields: pos 16 | vel 12 | kp 12 | kd 12 | torque 12.
Reply, 8 bytes: pos 16 | vel 12 | torque 12 | flags 8 | FET temperature 8 [°C] | bus voltage 8 [0.25 V].
Signed fields are two's complement with +range at 2^(bits-1) - 1 (zero is exact); kp and kd map
[0, max] to [0, 2^bits - 1]. Values outside a range saturate. Ranges are the board's
axis.config.can.impedance_* settings; both ends must use the same ones.

The frame uses arbitration ID node_id << 5 | MSG_IMPEDANCE in both directions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MSG_IMPEDANCE = 0x1E
FLAG_ARMED, FLAG_ERROR, FLAG_TIMEOUT = 1, 2, 4


@dataclass(frozen=True)
class Ranges:
    pos: float = 16.0      # turn, +/-
    vel: float = 32.0      # turn/s, +/-
    kp: float = 200.0      # Nm/turn, 0..max
    kd: float = 2.0        # Nm/(turn/s), 0..max
    torque: float = 4.0    # Nm, +/-


@dataclass(frozen=True)
class Reply:
    pos: float          # turn
    vel: float          # turn/s
    torque: float       # Nm, from the measured Iq
    armed: bool
    error: bool
    timeout: bool       # watchdog decelerate-and-hold active
    fet_temp: float     # °C
    vbus: float         # V


def arbitration_id(node_id: int) -> int:
    return node_id << 5 | MSG_IMPEDANCE


def _round(x: float) -> int:
    return int(math.copysign(math.floor(abs(x) + 0.5), x))  # half away from zero, as C's round()


def to_signed(x: float, rng: float, bits: int) -> int:
    full = (1 << (bits - 1)) - 1
    if not rng > 0 or math.isnan(x):
        return 0
    return max(-full, min(full, _round(x / rng * full))) & ((1 << bits) - 1)


def from_signed(raw: int, rng: float, bits: int) -> float:
    full = (1 << (bits - 1)) - 1
    v = raw - (1 << bits) if raw & (1 << (bits - 1)) else raw
    return max(v, -full) * rng / full


def to_unsigned(x: float, mx: float, bits: int) -> int:
    full = (1 << bits) - 1
    if not mx > 0 or math.isnan(x):
        return 0
    return max(0, min(full, _round(x / mx * full)))


def from_unsigned(raw: int, mx: float, bits: int) -> float:
    return raw * mx / ((1 << bits) - 1)


def encode_command(r: Ranges, pos: float, vel: float = 0.0, kp: float = 0.0, kd: float = 0.0,
                   torque: float = 0.0) -> bytes:
    p, v = to_signed(pos, r.pos, 16), to_signed(vel, r.vel, 12)
    k, d = to_unsigned(kp, r.kp, 12), to_unsigned(kd, r.kd, 12)
    t = to_signed(torque, r.torque, 12)
    return bytes([p >> 8, p & 0xFF, v >> 4, (v & 0xF) << 4 | k >> 8, k & 0xFF,
                  d >> 4, (d & 0xF) << 4 | t >> 8, t & 0xFF])


def decode_reply(r: Ranges, b: bytes) -> Reply:
    if len(b) != 8:
        raise ValueError(f"impedance reply must be 8 bytes, got {len(b)}")
    p = b[0] << 8 | b[1]
    v = b[2] << 4 | b[3] >> 4
    t = (b[3] & 0xF) << 8 | b[4]
    return Reply(pos=from_signed(p, r.pos, 16), vel=from_signed(v, r.vel, 12), torque=from_signed(t, r.torque, 12),
                 armed=bool(b[5] & FLAG_ARMED), error=bool(b[5] & FLAG_ERROR), timeout=bool(b[5] & FLAG_TIMEOUT),
                 fet_temp=float(b[6]), vbus=b[7] * 0.25)
