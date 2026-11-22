// Test driver for the firmware's endpoint_frame.hpp, used by test_endpoint_frame.py.
// Runs each stdin line "<request hex>" (any length, so bad lengths can be tested) through
// endpoint_frame::handle against a fake endpoint table, and prints "<reply hex> <calls>", where
// <calls> counts successful calls of function 14 so far. The table keeps its state across lines.
//
// Fake table:
//   0       buffer: the JSON {"a":1}; offset 0xFFFFFFFF reads the version ID 0x12345678
//   10      float rw (1.5)          11  uint8 r (7)       12  bool rw (false)
//   13      uint64 r                14  function          15  function that fails
//   16      uint16 rw, clamps writes to 1000              17  int32 rw whose writes fail
//   0x7F00  buffer whose reads fail (a capture that isn't done)
#include <cstdio>
#include <cstring>

#include "communication/can/endpoint_frame.hpp"

using namespace endpoint_frame;

struct Fake {
    float f10 = 1.5f;
    uint8_t u11 = 7;
    bool b12 = false;
    uint64_t u13 = 0x0102030405060708ull;
    uint16_t u16 = 0;
    int32_t i17 = -5;
    int calls = 0;

    Kind kind(uint16_t id) {
        switch (id) {
            case 0: case 0x7F00: return KIND_BUFFER;
            case 10: case 12: case 16: case 17: return KIND_READ_WRITE;
            case 11: case 13: return KIND_READ_ONLY;
            case 14: case 15: return KIND_FUNCTION;
            default: return KIND_NONE;
        }
    }

    template <class T>
    static size_t put(const T& v, uint8_t out[8]) {
        std::memcpy(out, &v, sizeof(v));
        return sizeof(v);
    }

    size_t read(uint16_t id, uint8_t out[8]) {
        switch (id) {
            case 10: return put(f10, out);
            case 11: return put(u11, out);
            case 12: return put(b12, out);
            case 13: return put(u13, out);
            case 16: return put(u16, out);
            case 17: return put(i17, out);
            default: return 0;
        }
    }

    bool write(uint16_t id, const uint8_t* v, size_t n) {
        switch (id) {
            case 10: std::memcpy(&f10, v, n); return n == 4;
            case 12: b12 = v[0] != 0; return n == 1;
            case 16: {
                uint16_t x;
                std::memcpy(&x, v, sizeof(x));
                u16 = x > 1000 ? 1000 : x;
                return n == 2;
            }
            default: return false;
        }
    }

    bool call(uint16_t id) {
        if (id == 14) {
            calls++;
            return true;
        }
        return false;
    }

    bool read_buffer(uint16_t id, uint32_t offset, uint8_t out[4]) {
        static const char json[] = "{\"a\":1}";
        if (id != 0) {
            return false;
        }
        if (offset == 0xFFFFFFFFu) {
            const uint32_t version = 0x12345678;
            std::memcpy(out, &version, 4);
            return true;
        }
        for (size_t i = 0; i < 4 && offset + i < sizeof(json) - 1; ++i) {
            out[i] = uint8_t(json[offset + i]);
        }
        return true;
    }
};

int main() {
    Fake fake;
    char line[256];
    while (std::fgets(line, sizeof(line), stdin)) {
        uint8_t req[32] = {};
        size_t len = 0;
        unsigned byte;
        for (const char* p = line; len < sizeof(req) && std::sscanf(p, "%2x", &byte) == 1; p += 2) {
            req[len++] = uint8_t(byte);
        }
        uint8_t rep[8];
        handle(req, len, rep, fake);
        for (uint8_t x : rep) {
            std::printf("%02x", x);
        }
        std::printf(" %d\n", fake.calls);
        std::fflush(stdout);
    }
    return 0;
}
