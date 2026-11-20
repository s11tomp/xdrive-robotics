#pragma once
// XDRIVE: fixed-point packing of the CANSimple impedance command (MSG_IMPEDANCE) and its reply.
//
// Command, 8 bytes, big-endian bit fields (the MIT-Cheetah actuator layout):
//   pos 16 bit | vel 12 | kp 12 | kd 12 | torque 12
// Reply, 8 bytes:
//   pos 16 bit | vel 12 | torque 12 | flags 8 | FET temperature 8 [°C] | bus voltage 8 [0.25 V]
//
// Signed fields are two's complement, scaled so that +range maps to 2^(bits-1) - 1 (zero is exact;
// the most negative raw value decodes to -range). Unsigned fields (kp, kd) map [0, max] to
// [0, 2^bits - 1]. Encoding saturates at the range. The ranges are per-axis config
// (`axis.config.can.impedance_*`) and must match on host and board.
//
// Pure functions, no firmware dependencies: xdrive/tools/tests/ compiles this header on the host.

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace impedance_frame {

struct Ranges {
    float pos;     // [turn]   +/-
    float vel;     // [turn/s] +/-
    float kp;      // [Nm/turn]       0..max
    float kd;      // [Nm/(turn/s)]   0..max
    float torque;  // [Nm]     +/-
};

struct Command {
    float pos, vel, kp, kd, torque;
};

enum Flags : uint8_t {
    FLAG_ARMED = 1 << 0,    // closed loop with the motor armed
    FLAG_ERROR = 1 << 1,    // any axis, motor, encoder or controller error
    FLAG_TIMEOUT = 1 << 2,  // watchdog decelerate-and-hold active (controller.timeout_active)
};

inline uint32_t to_signed(float x, float range, int bits) {
    const int32_t full = (1 << (bits - 1)) - 1;
    if (!(range > 0.0f) || std::isnan(x)) {
        return 0;
    }
    const float r = std::clamp(std::round(x / range * full), float(-full), float(full));
    return uint32_t(int32_t(r)) & ((1u << bits) - 1);
}

inline float from_signed(uint32_t raw, float range, int bits) {
    const int32_t full = (1 << (bits - 1)) - 1;
    const int32_t v = std::max(int32_t(raw << (32 - bits)) >> (32 - bits), -full);
    return float(v) * range / float(full);
}

inline uint32_t to_unsigned(float x, float max, int bits) {
    const uint32_t full = (1u << bits) - 1;
    if (!(max > 0.0f) || std::isnan(x)) {
        return 0;
    }
    return uint32_t(std::clamp(std::round(x / max * full), 0.0f, float(full)));
}

inline float from_unsigned(uint32_t raw, float max, int bits) {
    return float(raw) * max / float((1u << bits) - 1);
}

inline Command decode_command(const uint8_t b[8], const Ranges& r) {
    const uint32_t pos = (uint32_t(b[0]) << 8) | b[1];
    const uint32_t vel = (uint32_t(b[2]) << 4) | (b[3] >> 4);
    const uint32_t kp = (uint32_t(b[3] & 0x0f) << 8) | b[4];
    const uint32_t kd = (uint32_t(b[5]) << 4) | (b[6] >> 4);
    const uint32_t torque = (uint32_t(b[6] & 0x0f) << 8) | b[7];
    return {from_signed(pos, r.pos, 16), from_signed(vel, r.vel, 12), from_unsigned(kp, r.kp, 12),
            from_unsigned(kd, r.kd, 12), from_signed(torque, r.torque, 12)};
}

inline void encode_reply(uint8_t b[8], const Ranges& r, float pos, float vel, float torque, uint8_t flags,
                         float fet_temp, float vbus) {
    const uint32_t p = to_signed(pos, r.pos, 16);
    const uint32_t v = to_signed(vel, r.vel, 12);
    const uint32_t t = to_signed(torque, r.torque, 12);
    b[0] = uint8_t(p >> 8);
    b[1] = uint8_t(p);
    b[2] = uint8_t(v >> 4);
    b[3] = uint8_t(((v & 0x0f) << 4) | (t >> 8));
    b[4] = uint8_t(t);
    b[5] = flags;
    b[6] = uint8_t(to_unsigned(fet_temp, 255.0f, 8));
    b[7] = uint8_t(to_unsigned(vbus, 63.75f, 8));
}

}  // namespace impedance_frame
