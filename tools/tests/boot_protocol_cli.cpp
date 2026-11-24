// Test driver for the bootloader's boot_protocol.hpp, used by test_boot_frame.py.
//
// Usage: boot_protocol_cli <image.bin | -> <node id> <requested 0|1>
// The fake flash covers the application sectors and starts erased (0xFF), then holds the image at
// APP_START if one is given; programming only clears bits, as on real flash. The board's serial
// number is 0x0123456789AB.
//
// Each stdin line is one received frame, "<id hex> <data hex>" ("-" for no data), or a directive:
//   !fail_erase    the next erase fails
//   !fail_program  the next program fails
// For each frame it prints the answer "<id hex> <data hex>", or "-" for none, followed by " start"
// when the answer allows the application to start. Directives print nothing.
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <iostream>

#include "bootloader/boot_protocol.hpp"

using namespace boot_protocol;

struct FakeFlash {
    std::vector<uint8_t> mem = std::vector<uint8_t>(APP_SIZE, 0xFF);
    bool fail_erase = false;
    bool fail_program = false;
    int erases = 0;

    bool erase(uint8_t sector) {
        if (fail_erase) {
            fail_erase = false;
            return false;
        }
        for (const Sector& s : APP_SECTORS) {
            if (s.number == sector) {
                std::memset(mem.data() + (s.start - APP_START), 0xFF, s.size);
                ++erases;
                return true;
            }
        }
        return false;
    }

    bool program(uint32_t addr, const uint8_t* data, size_t len) {
        if (fail_program) {
            fail_program = false;
            return false;
        }
        if (addr < APP_START || addr % 4 || len % 4 || addr - APP_START + len > APP_SIZE) {
            return false;
        }
        for (size_t i = 0; i < len; ++i) {
            mem[addr - APP_START + i] &= data[i];
        }
        return true;
    }

    const uint8_t* read(uint32_t addr) { return mem.data() + (addr - APP_START); }
};

static std::vector<uint8_t> unhex(const std::string& s) {
    std::vector<uint8_t> out;
    if (s == "-") {
        return out;
    }
    for (size_t i = 0; i + 1 < s.size(); i += 2) {
        out.push_back(uint8_t(std::stoul(s.substr(i, 2), nullptr, 16)));
    }
    return out;
}

int main(int argc, char** argv) {
    if (argc != 4) {
        std::fprintf(stderr, "usage: boot_protocol_cli <image.bin | -> <node id> <requested 0|1>\n");
        return 2;
    }
    static FakeFlash flash;
    if (std::string(argv[1]) != "-") {
        FILE* f = std::fopen(argv[1], "rb");
        if (!f) {
            return 2;
        }
        size_t n = std::fread(flash.mem.data(), 1, APP_SIZE, f);
        std::fclose(f);
        (void)n;
    }
    static Session<FakeFlash> session(flash, 0x0123456789ABull, uint8_t(std::stoul(argv[2])), argv[3][0] == '1');
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line == "!fail_erase") {
            flash.fail_erase = true;
            continue;
        }
        if (line == "!fail_program") {
            flash.fail_program = true;
            continue;
        }
        size_t sp = line.find(' ');
        Frame in{};
        in.id = uint32_t(std::stoul(line.substr(0, sp), nullptr, 16));
        std::vector<uint8_t> data = unhex(line.substr(sp + 1));
        in.len = uint8_t(data.size());
        std::memcpy(in.data, data.data(), data.size());
        Frame out{};
        Session<FakeFlash>::Action action;
        if (session.handle(in, out, action)) {
            std::printf("%08x ", unsigned(out.id));
            for (int i = 0; i < out.len; ++i) {
                std::printf("%02x", out.data[i]);
            }
            std::printf("%s\n", action == Session<FakeFlash>::ACTION_START_APP ? " start" : "");
        } else {
            std::printf("-\n");
        }
    }
    return 0;
}
