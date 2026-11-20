#include "odrive_main.h"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace {

// Reads a property through the generated endpoint table: an empty input makes a read-write
// property's exchange a plain read. The empty input must have a non-null end: fibre's
// SimpleSerializer treats a null end as unbounded and would decode (and write back) whatever sits
// at address 0. Only called with IDs that add_channel() checked are properties: for a function's
// ID, endpoint_handler runs the function.
uint32_t read_raw(uint16_t id, size_t* n_bytes = nullptr) {
    uint8_t bytes[4] = {};
    fibre::cbufptr_t in{bytes, size_t(0)};
    fibre::bufptr_t out{bytes, sizeof(bytes)};
    fibre::endpoint_handler(id, &in, &out);
    if (n_bytes) {
        *n_bytes = sizeof(bytes) - out.size();
    }
    return uint32_t(bytes[0]) | (uint32_t(bytes[1]) << 8) | (uint32_t(bytes[2]) << 16) | (uint32_t(bytes[3]) << 24);
}

struct TypeEntry {
    const char* name;
    uint8_t kind;  // Capture::Kind
    uint8_t size;
};

}  // namespace

bool Capture::add_channel(uint32_t endpoint_id) {
    if (n_channels_ >= kMaxChannels || state_ == CAPTURE_STATE_ARMED || state_ == CAPTURE_STATE_TRIGGERED
        || endpoint_id == 0 || endpoint_id >= fibre::kRawEndpointBase) {
        return false;
    }
    // The interface JSON lists every endpoint as {"name":..,"id":<id>,"type":"<type>",..}; functions
    // have type "function", so only the scalar types below are accepted.
    static const TypeEntry kTypes[] = {
        {"float", KIND_FLOAT, 4},  {"bool", KIND_UNSIGNED, 1},   {"uint8", KIND_UNSIGNED, 1},
        {"uint16", KIND_UNSIGNED, 2}, {"uint32", KIND_UNSIGNED, 4}, {"int32", KIND_SIGNED, 4},
    };
    char key[32];
    snprintf(key, sizeof(key), "\"id\":%lu,\"type\":\"", (unsigned long)endpoint_id);
    const char* hit = strstr(reinterpret_cast<const char*>(fibre::embedded_json), key);
    if (!hit) {
        return false;
    }
    const char* type = hit + strlen(key);
    const TypeEntry* entry = nullptr;
    for (const TypeEntry& t : kTypes) {
        size_t n = strlen(t.name);
        if (!strncmp(type, t.name, n) && type[n] == '"') {
            entry = &t;
        }
    }
    size_t n_bytes = 0;
    if (!entry || (read_raw(uint16_t(endpoint_id), &n_bytes), n_bytes != entry->size)) {
        return false;
    }
    ids_[n_channels_] = uint16_t(endpoint_id);
    kinds_[n_channels_] = Kind(entry->kind);
    n_channels_++;
    capacity_ = kWords / n_channels_;
    n_samples_ = 0;
    state_ = CAPTURE_STATE_IDLE;
    return true;
}

void Capture::clear_channels() {
    CRITICAL_SECTION() {
        n_channels_ = 0;
        capacity_ = 0;
        n_samples_ = 0;
        state_ = CAPTURE_STATE_IDLE;
    }
}

bool Capture::start() {
    const bool level = trigger_mode_ == CAPTURE_TRIGGER_RISING || trigger_mode_ == CAPTURE_TRIGGER_FALLING;
    if (n_channels_ == 0 || trigger_mode_ > CAPTURE_TRIGGER_MANUAL || (level && trigger_channel_ >= n_channels_)) {
        return false;
    }
    CRITICAL_SECTION() {
        post_trigger_ = std::min(post_trigger_, capacity_ - 1);
        write_ = 0;
        n_samples_ = 0;
        decim_count_ = 0;
        trigger_index_ = 0;
        prev_ = NAN;  // the first sample can't complete a crossing
        trigger_requested_ = false;
        state_ = CAPTURE_STATE_ARMED;
    }
    return true;
}

void Capture::trigger() {
    trigger_requested_ = true;
}

float Capture::as_float(uint32_t raw, size_t channel) const {
    switch (kinds_[channel]) {
        case KIND_FLOAT: {
            float f;
            memcpy(&f, &raw, sizeof(f));
            return f;
        }
        case KIND_SIGNED: return float(int32_t(raw));  // int32 is the only signed type accepted
        default: return float(raw);
    }
}

void Capture::update() {
    if (state_ != CAPTURE_STATE_ARMED && state_ != CAPTURE_STATE_TRIGGERED) {
        return;
    }
    if (++decim_count_ < decimation_) {
        return;
    }
    decim_count_ = 0;

    uint32_t* frame = &buf_[write_ * n_channels_];
    for (size_t i = 0; i < n_channels_; ++i) {
        frame[i] = read_raw(ids_[i]);
    }
    write_ = (write_ + 1 == capacity_) ? 0 : write_ + 1;
    if (n_samples_ < capacity_) {
        n_samples_++;
    }

    if (state_ == CAPTURE_STATE_ARMED) {
        bool fire = trigger_requested_ || trigger_mode_ == CAPTURE_TRIGGER_IMMEDIATE;
        // trigger_channel_ is checked again here: the host can change it while the capture is armed.
        if ((trigger_mode_ == CAPTURE_TRIGGER_RISING || trigger_mode_ == CAPTURE_TRIGGER_FALLING)
            && trigger_channel_ < n_channels_) {
            const float x = as_float(frame[trigger_channel_], trigger_channel_);
            fire |= trigger_mode_ == CAPTURE_TRIGGER_RISING ? (prev_ < trigger_level_ && x >= trigger_level_)
                                                             : (prev_ > trigger_level_ && x <= trigger_level_);
            prev_ = x;
        }
        if (!fire) {
            return;
        }
        state_ = CAPTURE_STATE_TRIGGERED;
        remaining_ = post_trigger_;
    } else {
        remaining_--;
    }
    if (remaining_ == 0) {
        trigger_index_ = n_samples_ - 1 - post_trigger_;
        state_ = CAPTURE_STATE_DONE;
    }
}

bool Capture::read(fibre::cbufptr_t* input_buffer, fibre::bufptr_t* output_buffer) {
    if (input_buffer->size() < 4) {
        return false;
    }
    const uint8_t* in = input_buffer->begin();
    size_t offset = size_t(in[0]) | (size_t(in[1]) << 8) | (size_t(in[2]) << 16) | (size_t(in[3]) << 24);
    if (state_ != CAPTURE_STATE_DONE) {
        return true;  // empty response: nothing to read
    }
    const size_t total = size_t(n_samples_) * n_channels_ * 4;
    const size_t oldest = n_samples_ < capacity_ ? 0 : write_;
    while (offset < total && output_buffer->size()) {
        const size_t word = offset / 4;
        size_t frame = oldest + word / n_channels_;
        if (frame >= capacity_) {
            frame -= capacity_;
        }
        *output_buffer->begin() = uint8_t(buf_[frame * n_channels_ + word % n_channels_] >> (8 * (offset % 4)));
        *output_buffer = output_buffer->skip(1);
        offset++;
    }
    return true;
}

bool fibre::raw_endpoint_handler(int idx, cbufptr_t* input_buffer, bufptr_t* output_buffer) {
    return idx == Capture::kReadoutEndpoint && odrv.capture_.read(input_buffer, output_buffer);
}
