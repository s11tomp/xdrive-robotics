// Test driver for the firmware's impedance_frame.hpp, used by test_impedance_frame.py.
// Reads lines from stdin and writes one result line per input line:
//   "cmd <16 hex chars> <pos range> <vel range> <kp max> <kd max> <torque range>"
//     -> "<pos> <vel> <kp> <kd> <torque>"  (decode_command)
//   "reply <pos range> <vel range> <kp max> <kd max> <torque range> <pos> <vel> <torque> <flags> <temp> <vbus>"
//     -> "<16 hex chars>"  (encode_reply)
#include <cstdio>
#include <cstring>

#include "communication/can/impedance_frame.hpp"

int main() {
    char line[512];
    while (std::fgets(line, sizeof(line), stdin)) {
        impedance_frame::Ranges r{};
        if (std::strncmp(line, "cmd ", 4) == 0) {
            unsigned long long raw = 0;
            std::sscanf(line + 4, "%llx %f %f %f %f %f", &raw, &r.pos, &r.vel, &r.kp, &r.kd, &r.torque);
            uint8_t b[8];
            for (int i = 0; i < 8; ++i) {
                b[i] = uint8_t(raw >> (56 - 8 * i));
            }
            const impedance_frame::Command c = impedance_frame::decode_command(b, r);
            std::printf("%.9g %.9g %.9g %.9g %.9g\n", c.pos, c.vel, c.kp, c.kd, c.torque);
        } else if (std::strncmp(line, "reply ", 6) == 0) {
            float pos, vel, torque, temp, vbus;
            unsigned flags;
            std::sscanf(line + 6, "%f %f %f %f %f %f %f %f %u %f %f", &r.pos, &r.vel, &r.kp, &r.kd, &r.torque,
                        &pos, &vel, &torque, &flags, &temp, &vbus);
            uint8_t b[8];
            impedance_frame::encode_reply(b, r, pos, vel, torque, uint8_t(flags), temp, vbus);
            for (uint8_t x : b) {
                std::printf("%02x", x);
            }
            std::printf("\n");
        }
        std::fflush(stdout);
    }
    return 0;
}
