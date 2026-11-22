"""Host side of CANSimple endpoint access (MSG_ENDPOINT): read or write any property, call any
function, or read a buffer (the interface JSON, the capture readout) by fibre endpoint ID.

Mirror of the firmware's src/communication/can/endpoint_frame.hpp, which has the full frame
layout; tests/test_endpoint_frame.py compiles that header and checks both against each other.

Request, 8 bytes, little-endian: opcode | endpoint ID (uint16) | 0 | value or offset (4 bytes).
Reply, same arbitration ID: opcode | 0x80 | endpoint ID | status | value or data (4 bytes).
The arbitration ID is node_id << 5 | MSG_ENDPOINT in both directions.

Endpoint IDs and types come from the board's interface JSON (endpoints() maps it to dotted
names). A function's inputs and outputs are endpoints of their own: write the inputs, call the
function, read the outputs. save_configuration and reboot send no reply: the board reboots.
"""
import struct
from dataclasses import dataclass
from enum import IntEnum

MSG_ENDPOINT = 0x1F
REPLY_FLAG = 0x80
JSON_ENDPOINT = 0              # OP_READ_BUFFER on it reads the interface JSON
JSON_VERSION_OFFSET = 0xFFFFFFFF  # ... and at this offset, the JSON version ID (uint32)
CAPTURE_READOUT = 0x7F00       # odrv.capture's readout buffer (capture.readout_endpoint)


class Op(IntEnum):
    READ = 1
    WRITE = 2
    CALL = 3
    READ_BUFFER = 4


class Status(IntEnum):
    OK = 0
    UNKNOWN_ENDPOINT = 1
    WRONG_KIND = 2         # read/write of a function, call of a property, write of a read-only property
    UNSUPPORTED_TYPE = 3   # property wider than 4 bytes
    BAD_VALUE = 4          # write with non-zero bytes past the property's size
    FAILED = 5             # the board's endpoint handler refused the request
    BAD_OPCODE = 6
    BAD_LENGTH = 7


# Interface JSON type -> struct format. uint64 and int64 properties can't be reached over CAN.
FORMATS = {"float": "<f", "bool": "<?", "uint8": "<B", "uint16": "<H", "uint32": "<I", "int32": "<i"}


def pack(type_name, value):
    """A value as the 4 data bytes of a write: the property's bytes, zero-padded."""
    return struct.pack(FORMATS[type_name], value).ljust(4, b"\0")


def unpack(type_name, data):
    fmt = FORMATS[type_name]
    return struct.unpack(fmt, bytes(data[:struct.calcsize(fmt)]))[0]


def request(op, endpoint_id, data=bytes(4)):
    if not 0 <= endpoint_id <= 0xFFFF or len(data) != 4:
        raise ValueError(f"bad request: endpoint {endpoint_id}, {len(data)} data bytes")
    return bytes([op]) + struct.pack("<H", endpoint_id) + b"\0" + bytes(data)


def read_request(endpoint_id):
    return request(Op.READ, endpoint_id)


def write_request(endpoint_id, type_name, value):
    return request(Op.WRITE, endpoint_id, pack(type_name, value))


def call_request(endpoint_id):
    return request(Op.CALL, endpoint_id)


def read_buffer_request(endpoint_id, offset):
    return request(Op.READ_BUFFER, endpoint_id, struct.pack("<I", offset))


@dataclass(frozen=True)
class Reply:
    op: int  # the request's opcode (an Op, unless the board answered STATUS_BAD_OPCODE)
    endpoint_id: int
    status: Status
    data: bytes  # 4 bytes: the value (unpack() it by type) or buffer data; zeros on an error


def decode_reply(frame):
    frame = bytes(frame)
    if len(frame) != 8 or not frame[0] & REPLY_FLAG:
        raise ValueError(f"not an endpoint reply: {frame.hex()}")
    return Reply(frame[0] & ~REPLY_FLAG & 0xFF, struct.unpack_from("<H", frame, 1)[0], Status(frame[3]), frame[4:])


@dataclass(frozen=True)
class Endpoint:
    id: int
    type: str    # "function" or an interface JSON scalar type ("float", "uint32", ...)
    access: str  # "r", "rw", or "" for a function


def endpoints(interface):
    """Dotted name -> Endpoint for the interface JSON (a list of members, as the board serves it).

    Function arguments are named after their function: capture.add_channel.endpoint_id.
    """
    out = {}

    def walk(members, prefix):
        for m in members:
            name = prefix + m["name"]
            if m["type"] == "object":
                walk(m["members"], name + ".")
            elif m["type"] == "function":
                out[name] = Endpoint(m["id"], "function", "")
                walk(m.get("inputs", []) + m.get("outputs", []), name + ".")
            elif m["type"] != "json":
                out[name] = Endpoint(m["id"], m["type"], m["access"])

    walk(interface, "")
    return out
