#ifndef __CAPTURE_HPP
#define __CAPTURE_HPP

// XDRIVE: configurable high-rate capture.
//
// Every `decimation` control periods (8 kHz), update() reads up to kMaxChannels properties, chosen
// by fibre endpoint ID, into a RAM ring buffer. A trigger (one channel crossing a level, a call to
// trigger(), or immediately on start()) is followed by `post_trigger` more samples, after which the
// capture is DONE and the host reads the buffer with a bulk read of endpoint kReadoutEndpoint
// (fibre's remote_endpoint_read_buffer, the same chunked read that fetches the interface JSON).
//
// Readout layout: n_samples frames, oldest first; each frame is n_channels little-endian 32-bit
// words in channel order. Each word holds the property's raw bytes zero-padded to 32 bits, so the
// host decodes it by the property's type in the interface JSON. The trigger sample is frame
// trigger_index.
//
// Concurrency: update() runs in the control-loop interrupt; everything else runs in the
// communication threads. The channel list and the buffer change only while the capture is not
// recording, and the readout serves data only when DONE.

#include <autogen/interfaces.hpp>
#include <fibre/../../protocol.hpp>

class Capture : public ODriveIntf::CaptureIntf {
public:
    static constexpr size_t kWords = 8192;  // 32 KiB
    static constexpr size_t kMaxChannels = 8;
    static constexpr uint16_t kReadoutEndpoint = fibre::kRawEndpointBase;

    bool add_channel(uint32_t endpoint_id) override;
    void clear_channels() override;
    bool start() override;
    void trigger() override;

    void update();  // control loop, once per period
    bool read(fibre::cbufptr_t* input_buffer, fibre::bufptr_t* output_buffer);  // bulk readout

    // Settings (RAM only)
    uint32_t decimation_ = 1;
    CaptureTrigger trigger_mode_ = CAPTURE_TRIGGER_IMMEDIATE;
    uint32_t trigger_channel_ = 0;
    float trigger_level_ = 0.0f;
    uint32_t post_trigger_ = kWords;  // clamped to capacity - 1 by start()

    // Status
    CaptureState state_ = CAPTURE_STATE_IDLE;
    uint32_t n_channels_ = 0;
    uint32_t capacity_ = 0;  // frames per capture: kWords / n_channels
    uint32_t n_samples_ = 0;
    uint32_t trigger_index_ = 0;
    const uint16_t readout_endpoint_ = kReadoutEndpoint;

private:
    enum Kind : uint8_t { KIND_FLOAT, KIND_UNSIGNED, KIND_SIGNED };
    float as_float(uint32_t raw, size_t channel) const;

    uint16_t ids_[kMaxChannels] = {};
    Kind kinds_[kMaxChannels] = {};
    uint32_t buf_[kWords] = {};
    uint32_t write_ = 0;  // next frame to write
    uint32_t decim_count_ = 0;
    uint32_t remaining_ = 0;  // samples still to record after the trigger
    float prev_ = 0.0f;
    volatile bool trigger_requested_ = false;
};

#endif  // __CAPTURE_HPP
