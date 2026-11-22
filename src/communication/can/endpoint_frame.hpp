#pragma once
// XDRIVE: CANSimple endpoint access (MSG_ENDPOINT): read or write any property, call any function,
// or read an offset-addressed buffer (the interface JSON, the capture readout), by fibre endpoint
// ID. The IDs and types are the ones in the board's interface JSON, the same ones USB uses.
//
// Request (host to board), 8 bytes, little-endian:
//   byte 0     opcode (Opcode)
//   bytes 1-2  endpoint ID, uint16
//   byte 3     0
//   bytes 4-7  OP_WRITE: the new value, the property's bytes zero-padded to 4
//              OP_READ_BUFFER: byte offset, uint32 (endpoint 0: 0xFFFFFFFF reads the JSON version ID)
//              otherwise 0
// Reply (board to host), same arbitration ID, 8 bytes:
//   byte 0     the request's opcode | REPLY_FLAG
//   bytes 1-2  endpoint ID, echoed
//   byte 3     status (Status)
//   bytes 4-7  OP_READ, OP_WRITE: the property's value after the request, zero-padded to 4
//              OP_READ_BUFFER: the 4 bytes at the offset, zeros past the buffer's end
//              otherwise, and on any error: 0
//
// A function's inputs and outputs are endpoints of their own: write the inputs, call the function,
// then read the outputs. A function that reboots the board (save_configuration, reboot) sends no
// reply. Properties wider than 4 bytes (uint64, int64) are refused with STATUS_UNSUPPORTED_TYPE.
//
// Pure logic, no firmware dependencies: tools/tests/ compiles this header on the host with a fake
// endpoint table. The firmware's table is the Backend in can_simple.cpp.

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace endpoint_frame {

enum Opcode : uint8_t {
    OP_READ = 1,
    OP_WRITE = 2,
    OP_CALL = 3,
    OP_READ_BUFFER = 4,
};

constexpr uint8_t REPLY_FLAG = 0x80;

enum Status : uint8_t {
    STATUS_OK = 0,
    STATUS_UNKNOWN_ENDPOINT = 1,
    STATUS_WRONG_KIND = 2,        // read/write of a function, call of a property, write of a read-only property
    STATUS_UNSUPPORTED_TYPE = 3,  // property wider than 4 bytes
    STATUS_BAD_VALUE = 4,         // write with non-zero bytes past the property's size
    STATUS_FAILED = 5,            // the endpoint handler refused the request
    STATUS_BAD_OPCODE = 6,
    STATUS_BAD_LENGTH = 7,        // request shorter or longer than 8 bytes
};

enum Kind : uint8_t {
    KIND_NONE,
    KIND_READ_ONLY,
    KIND_READ_WRITE,
    KIND_FUNCTION,
    KIND_BUFFER,  // read with OP_READ_BUFFER only
};

// Backend contract (a template parameter, so the host test and the firmware share this logic):
//   Kind kind(uint16_t id);
//   size_t read(uint16_t id, uint8_t out[8]);             property bytes written, 0 on failure
//   bool write(uint16_t id, const uint8_t* value, size_t n);
//   bool call(uint16_t id);
//   bool read_buffer(uint16_t id, uint32_t offset, uint8_t out[4]);  fills up to 4 bytes, rest stays 0
template <class Backend>
inline void handle(const uint8_t* req, size_t len, uint8_t rep[8], Backend& b) {
    std::memset(rep, 0, 8);
    if (len != 8) {
        rep[3] = STATUS_BAD_LENGTH;
        return;
    }
    const uint8_t op = req[0];
    const uint16_t id = uint16_t(req[1] | (req[2] << 8));
    rep[0] = uint8_t(op | REPLY_FLAG);
    rep[1] = req[1];
    rep[2] = req[2];

    const Kind kind = b.kind(id);
    uint8_t status = STATUS_OK;
    uint8_t value[8] = {};
    size_t n = 0;
    if (op < OP_READ || op > OP_READ_BUFFER) {
        status = STATUS_BAD_OPCODE;
    } else if (kind == KIND_NONE) {
        status = STATUS_UNKNOWN_ENDPOINT;
    } else if (op == OP_CALL) {
        status = kind != KIND_FUNCTION ? STATUS_WRONG_KIND : b.call(id) ? STATUS_OK : STATUS_FAILED;
    } else if (op == OP_READ_BUFFER) {
        const uint32_t offset = uint32_t(req[4]) | (uint32_t(req[5]) << 8) | (uint32_t(req[6]) << 16)
                                | (uint32_t(req[7]) << 24);
        status = kind != KIND_BUFFER ? STATUS_WRONG_KIND
                 : b.read_buffer(id, offset, value) ? STATUS_OK
                                                    : STATUS_FAILED;
        n = 4;
    } else if (kind != KIND_READ_ONLY && kind != KIND_READ_WRITE) {
        status = STATUS_WRONG_KIND;
    } else if (op == OP_WRITE && kind != KIND_READ_WRITE) {
        status = STATUS_WRONG_KIND;
    } else if ((n = b.read(id, value)) == 0) {
        status = STATUS_FAILED;
    } else if (n > 4) {
        status = STATUS_UNSUPPORTED_TYPE;
    } else if (op == OP_WRITE) {
        for (size_t i = 4 + n; i < 8; ++i) {
            if (req[i]) {
                status = STATUS_BAD_VALUE;
            }
        }
        if (status == STATUS_OK) {
            std::memset(value, 0, sizeof(value));
            if (!b.write(id, req + 4, n) || b.read(id, value) != n) {
                status = STATUS_FAILED;
            }
        }
    }
    rep[3] = status;
    if (status == STATUS_OK) {
        std::memcpy(rep + 4, value, n);
    }
}

}  // namespace endpoint_frame
