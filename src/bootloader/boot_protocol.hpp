#pragma once
// The CAN bootloader's protocol: frame IDs, commands, the application image header, CRC-32, and the
// command handler, which runs against a flash backend.
//
// Pure logic, no firmware dependencies: tools/tests/ compiles this header on the host with a fake
// flash (boot_protocol_cli.cpp) and checks the host codec tools/xdrive/boot_frame.py against it. The
// bootloader (bootloader/main.cpp) supplies the real flash. Design: docs/bootloader.md.
//
// Frames use 29-bit IDs, which CANSimple (11-bit IDs) never sends:
//   bits 25-28  TAG (0xB)
//   bit  24     1 from a board, 0 from the host
//   bits 20-23  the command
//   bits 0-19   the low 20 bits of the board's serial number; BROADCAST (all ones) from the host
//               reaches every board in the bootloader (discover only)
//
// Commands (host -> board; the board answers with the same command, from-board bit set, byte 0 the
// status unless noted):
//   DISCOVER     (broadcast or addressed) answer: serial number (6 bytes, little-endian), node ID
//                (0xFF: unknown), flags (bit 0 the image is valid, bit 1 entered on the
//                application's request, bits 4-7 PROTOCOL_VERSION). No status byte.
//   ERASE        u32 length: erases the application sectors that [APP_START, APP_START + length)
//                touches, the header's sector first
//   BLOCK_START  u32 offset, u32 length: opens a block of `length` bytes at APP_START + offset
//                (offset and length multiples of 4, length 4..BLOCK_MAX); no answer
//   DATA         1-8 bytes appended to the open block; no answer
//   BLOCK_END    u32 CRC-32 of the block: programs and reads back the block if the CRC, the length
//                and the range check out; answer: status, then the block's u32 offset
//   VERIFY       answer: status (OK or NO_VALID_IMAGE), flags as in DISCOVER, u32 image length
//   START_APP    answer: status; on OK the caller starts the application
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace boot_protocol {

constexpr uint32_t TAG = 0xB;
constexpr uint32_t SERIAL_MASK = 0xFFFFF;
constexpr uint32_t BROADCAST = SERIAL_MASK;
constexpr uint8_t PROTOCOL_VERSION = 1;
constexpr uint8_t NODE_UNKNOWN = 0xFF;

enum Cmd : uint8_t {
    CMD_DISCOVER = 0,
    CMD_ERASE = 1,
    CMD_BLOCK_START = 2,
    CMD_DATA = 3,
    CMD_BLOCK_END = 4,
    CMD_VERIFY = 5,
    CMD_START_APP = 6,
};

enum Status : uint8_t {
    STATUS_OK = 0,
    STATUS_BAD_COMMAND = 1,     // unknown command, or a frame too short for its command
    STATUS_BAD_LENGTH = 2,      // a block's data doesn't add up to its length, or a bad length
    STATUS_OUT_OF_RANGE = 3,    // outside the application sectors, or misaligned
    STATUS_BAD_CRC = 4,
    STATUS_FLASH_ERROR = 5,     // erase or program failed, or the read-back differs
    STATUS_NO_VALID_IMAGE = 6,
    STATUS_NO_BLOCK = 7,        // BLOCK_END without BLOCK_START
};

enum Flags : uint8_t {
    FLAG_IMAGE_VALID = 1 << 0,
    FLAG_REQUESTED = 1 << 1,
};

// Flash layout (STM32F405): the bootloader in sectors 0-1, the application in sectors 2-9, the
// config (NVM) in sectors 10-11, which the bootloader never touches.
constexpr uint32_t BOOT_START = 0x08000000;
constexpr uint32_t APP_START = 0x08008000;
constexpr uint32_t APP_END = 0x080C0000;
constexpr uint32_t APP_SIZE = APP_END - APP_START;
constexpr size_t BLOCK_MAX = 1024;

struct Sector {
    uint8_t number;
    uint32_t start;
    uint32_t size;
};
constexpr Sector APP_SECTORS[] = {
    {2, 0x08008000, 0x4000}, {3, 0x0800C000, 0x4000}, {4, 0x08010000, 0x10000}, {5, 0x08020000, 0x20000},
    {6, 0x08040000, 0x20000}, {7, 0x08060000, 0x20000}, {8, 0x08080000, 0x20000}, {9, 0x080A0000, 0x20000},
};

// The application's image header, at APP_START + HEADER_OFFSET (after its 98-entry vector table).
// The build writes `length` and `crc`: CRC-32 of [APP_START, APP_START + length) with the crc field
// taken as zero.
constexpr uint32_t HEADER_OFFSET = 0x200;
constexpr uint32_t IMAGE_MAGIC = 0x4D494458;  // "XDIM"
constexpr uint32_t HEADER_VERSION = 1;
constexpr uint32_t HW_XDRIVE_MINI = 0x00030656;  // ODrive v3.6, 56 V variant: what the Mini reports
struct ImageHeader {
    uint32_t magic;
    uint32_t header_version;
    uint32_t length;
    uint32_t crc;
    uint32_t hw;
    uint8_t fw_version[4];  // major, minor, revision, unreleased
    uint32_t reserved[2];
};
static_assert(sizeof(ImageHeader) == 32, "the image header is 32 bytes");
constexpr uint32_t HEADER_CRC_OFFSET = HEADER_OFFSET + offsetof(ImageHeader, crc);

// The bootloader's own marker, at BOOT_START + HEADER_OFFSET: the flash tools check it before writing
// an application linked at APP_START.
constexpr uint32_t BOOTLOADER_MAGIC = 0x4C544258;  // "XBTL"

// CRC-32 as zlib computes it (reflected 0xEDB88320, init and final xor 0xFFFFFFFF), table-driven: about
// 18 ms for a 322 KB image at 168 MHz. `crc` continues from a previous call's result.
struct Crc32Table {
    uint32_t entry[256];
};

constexpr Crc32Table make_crc32_table() {
    Crc32Table table{};
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t c = i;
        for (int k = 0; k < 8; ++k) {
            c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
        }
        table.entry[i] = c;
    }
    return table;
}

inline constexpr Crc32Table CRC32_TABLE = make_crc32_table();

inline uint32_t crc32(const uint8_t* data, size_t len, uint32_t crc = 0) {
    crc = ~crc;
    for (size_t i = 0; i < len; ++i) {
        crc = CRC32_TABLE.entry[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    }
    return ~crc;
}

constexpr uint32_t make_id(bool from_board, uint8_t cmd, uint32_t serial20) {
    return (TAG << 25) | (uint32_t(from_board) << 24) | (uint32_t(cmd & 0xF) << 20) | (serial20 & SERIAL_MASK);
}

struct Id {
    bool ours;  // the TAG matches
    bool from_board;
    uint8_t cmd;
    uint32_t serial20;
};

inline Id parse_id(uint32_t id) {
    return {((id >> 25) & 0xF) == TAG, ((id >> 24) & 1) != 0, uint8_t((id >> 20) & 0xF), id & SERIAL_MASK};
}

struct Frame {
    uint32_t id;  // 29-bit extended ID
    uint8_t len;
    uint8_t data[8];
};

inline uint32_t get_u32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}

inline void put_u32(uint8_t* p, uint32_t v) {
    p[0] = uint8_t(v);
    p[1] = uint8_t(v >> 8);
    p[2] = uint8_t(v >> 16);
    p[3] = uint8_t(v >> 24);
}

// Backend: the flash. The bootloader's drives the flash interface; the host test's is an array that
// behaves like flash (programming only clears bits).
//   bool erase(uint8_t sector)                                  sector number from APP_SECTORS
//   bool program(uint32_t addr, const uint8_t* data, size_t len)   addr and len multiples of 4
//   const uint8_t* read(uint32_t addr)                           APP_START <= addr < APP_END
template <class Backend>
bool image_valid(Backend& flash, ImageHeader* out = nullptr) {
    ImageHeader h;
    std::memcpy(&h, flash.read(APP_START + HEADER_OFFSET), sizeof(h));
    if (out) {
        *out = h;
    }
    if (h.magic != IMAGE_MAGIC || h.header_version != HEADER_VERSION || h.hw != HW_XDRIVE_MINI
            || h.length < HEADER_OFFSET + sizeof(ImageHeader) || h.length > APP_SIZE) {
        return false;
    }
    static const uint8_t zero[4] = {0, 0, 0, 0};
    uint32_t crc = crc32(flash.read(APP_START), HEADER_CRC_OFFSET);
    crc = crc32(zero, 4, crc);
    crc = crc32(flash.read(APP_START + HEADER_CRC_OFFSET + 4), h.length - HEADER_CRC_OFFSET - 4, crc);
    return crc == h.crc;
}

template <class Backend>
class Session {
public:
    // serial: the board's 48-bit serial number; node_id: NODE_UNKNOWN when the application didn't
    // pass it on; requested: entered on the application's request.
    Session(Backend& flash, uint64_t serial, uint8_t node_id, bool requested)
        : flash_(flash), serial_(serial), node_id_(node_id), requested_(requested), valid_(image_valid(flash)) {}

    enum Action { ACTION_NONE, ACTION_START_APP };

    // Handles one received frame. Returns true and fills `reply` when the board answers. `action`
    // becomes ACTION_START_APP once a START_APP succeeded; the caller sends the reply first.
    bool handle(const Frame& in, Frame& reply, Action& action) {
        action = ACTION_NONE;
        Id id = parse_id(in.id);
        uint32_t own = uint32_t(serial_) & SERIAL_MASK;
        if (!id.ours || id.from_board) {
            return false;
        }
        if (id.serial20 != own && !(id.serial20 == BROADCAST && id.cmd == CMD_DISCOVER)) {
            return false;
        }
        reply.id = make_id(true, id.cmd, own);
        std::memset(reply.data, 0, sizeof(reply.data));
        reply.len = 1;
        switch (id.cmd) {
            case CMD_DISCOVER:
                for (int i = 0; i < 6; ++i) {
                    reply.data[i] = uint8_t(serial_ >> (8 * i));
                }
                reply.data[6] = node_id_;
                reply.data[7] = flags();
                reply.len = 8;
                return true;
            case CMD_ERASE:
                if (in.len < 4) {
                    return status(reply, STATUS_BAD_COMMAND);
                }
                block_open_ = false;
                valid_ = false;
                return status(reply, erase(get_u32(in.data)));
            case CMD_BLOCK_START: {
                block_open_ = true;
                block_fill_ = 0;
                block_error_ = STATUS_OK;
                if (in.len < 8) {
                    block_error_ = STATUS_BAD_COMMAND;
                    return false;
                }
                block_offset_ = get_u32(in.data);
                block_len_ = get_u32(in.data + 4);
                if (block_len_ == 0 || block_len_ > BLOCK_MAX || block_len_ % 4 || block_offset_ % 4) {
                    block_error_ = STATUS_BAD_LENGTH;
                } else if (block_offset_ > APP_SIZE || block_len_ > APP_SIZE - block_offset_) {
                    block_error_ = STATUS_OUT_OF_RANGE;
                }
                return false;
            }
            case CMD_DATA:
                if (block_open_ && block_error_ == STATUS_OK) {
                    if (block_fill_ + in.len > block_len_) {
                        block_error_ = STATUS_BAD_LENGTH;
                    } else {
                        std::memcpy(block_ + block_fill_, in.data, in.len);
                        block_fill_ += in.len;
                    }
                }
                return false;
            case CMD_BLOCK_END: {
                Status s = end_block(in);
                if (s == STATUS_OK) {
                    valid_ = false;  // VERIFY or START_APP checks the image again
                }
                put_u32(reply.data + 1, block_offset_);
                reply.len = 5;
                return status(reply, s);
            }
            case CMD_VERIFY: {
                ImageHeader h;
                valid_ = image_valid(flash_, &h);
                reply.data[1] = flags();
                put_u32(reply.data + 2, valid_ ? h.length : 0);
                reply.len = 6;
                return status(reply, valid_ ? STATUS_OK : STATUS_NO_VALID_IMAGE);
            }
            case CMD_START_APP:
                valid_ = image_valid(flash_);
                if (!valid_) {
                    return status(reply, STATUS_NO_VALID_IMAGE);
                }
                action = ACTION_START_APP;
                return status(reply, STATUS_OK);
            default:
                return status(reply, STATUS_BAD_COMMAND);
        }
    }

    // From the image check at the start and after VERIFY or START_APP; an erase or a programmed
    // block clears FLAG_IMAGE_VALID until the next check.
    uint8_t flags() const {
        return uint8_t((valid_ ? FLAG_IMAGE_VALID : 0) | (requested_ ? FLAG_REQUESTED : 0)
                       | (PROTOCOL_VERSION << 4));
    }

private:
    static bool status(Frame& reply, Status s) {
        reply.data[0] = s;
        return true;
    }

    Status erase(uint32_t length) {
        if (length == 0 || length > APP_SIZE) {
            return STATUS_OUT_OF_RANGE;
        }
        for (const Sector& s : APP_SECTORS) {
            if (s.start >= APP_START + length) {
                break;
            }
            if (!flash_.erase(s.number)) {
                return STATUS_FLASH_ERROR;
            }
        }
        return STATUS_OK;
    }

    Status end_block(const Frame& in) {
        if (!block_open_) {
            return STATUS_NO_BLOCK;
        }
        block_open_ = false;
        if (in.len < 4) {
            return STATUS_BAD_COMMAND;
        }
        if (block_error_ != STATUS_OK) {
            return block_error_;
        }
        if (block_fill_ != block_len_) {
            return STATUS_BAD_LENGTH;
        }
        if (crc32(block_, block_len_) != get_u32(in.data)) {
            return STATUS_BAD_CRC;
        }
        uint32_t addr = APP_START + block_offset_;
        if (!flash_.program(addr, block_, block_len_) || std::memcmp(flash_.read(addr), block_, block_len_) != 0) {
            return STATUS_FLASH_ERROR;
        }
        return STATUS_OK;
    }

    Backend& flash_;
    uint64_t serial_;
    uint8_t node_id_;
    bool requested_;
    bool valid_;
    bool block_open_ = false;
    uint32_t block_offset_ = 0;
    uint32_t block_len_ = 0;
    uint32_t block_fill_ = 0;
    Status block_error_ = STATUS_OK;
    uint8_t block_[BLOCK_MAX];
};

}  // namespace boot_protocol
