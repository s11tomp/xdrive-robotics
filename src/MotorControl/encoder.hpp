#ifndef __ENCODER_HPP
#define __ENCODER_HPP

class Encoder;

#include <board.h> // needed for arm_math.h
#include <Drivers/STM32/stm32_spi_arbiter.hpp>
#include "utils.hpp"
#include <autogen/interfaces.hpp>
#include "component.hpp"


class Encoder : public ODriveIntf::EncoderIntf {
public:
    static constexpr uint32_t MODE_FLAG_ABS = 0x100;
    static constexpr std::array<float, 6> hall_edge_defaults = 
        {0.0f, 1.0f, 2.0f, 3.0f, 4.0f, 5.0f};

    struct Config_t {
        Mode mode = MODE_INCREMENTAL;
        float calib_range = 0.02f; // Accuracy required to pass encoder cpr check
        float calib_scan_distance = 16.0f * M_PI; // rad electrical
        float calib_scan_omega = 4.0f * M_PI; // rad/s electrical
        float bandwidth = 1000.0f;
        int32_t phase_offset = 0;        // Offset between encoder count and rotor electrical phase
        float phase_offset_float = 0.0f; // Sub-count phase alignment offset
        int32_t cpr = (2048 * 4);   // Default resolution of CUI-AMT102 encoder,
        float index_offset = 0.0f;
        bool use_index = false;
        bool pre_calibrated = false; // If true, this means the offset stored in
                                    // configuration is valid and does not need
                                    // be determined by run_offset_calibration.
                                    // In this case the encoder will enter ready
                                    // state as soon as the index is found.
        int32_t direction = 0; // direction with respect to motor
        bool use_index_offset = true;
        bool enable_phase_interpolation = true; // Use velocity to interpolate inside the count state
        bool find_idx_on_lockin_only = false; // Only be sensitive during lockin scan constant vel state
        bool ignore_illegal_hall_state = false; // dont error on bad states like 000 or 111
        uint8_t hall_polarity = 0;
        bool hall_polarity_calibrated = false;
        std::array<float, 6> hall_edge_phcnt = hall_edge_defaults;
        uint16_t abs_spi_cs_gpio_pin = 1;
        uint16_t sincos_gpio_pin_sin = 3;
        uint16_t sincos_gpio_pin_cos = 4;
        // XDRIVE: SPI absolute encoder integrity.
        uint16_t abs_spi_max_jump = 1024;       // [counts] drop a sample further than this from the last good one (0 = off).
                                                // 1024 counts in one 125 us sample = 180 turn/s for a 14-bit encoder.
        bool abs_spi_reject_error_flag = false; // drop AMS frames with the error flag (bit 14) set. Off by default:
                                                // the flag is sticky until the chip's ERRFL register is read.
        bool abs_spi_check_parity = false;      // drop AMS frames with odd parity. Valid for an AS5047P (bit 15 =
                                                // even parity); an AS5047U has no parity bit, so off by default.
        // XDRIVE: per-angle correction of an absolute encoder.
        bool correction_enabled = false;              // add correction_table to the raw absolute position
        std::array<float, 256> correction_table = {}; // [counts] correction at the centre of each 1/256-turn bin
        float correction_scan_turns = 1.0f;           // mechanical turns each way in ENCODER_CORRECTION_CALIBRATION
        uint8_t correction_max_harmonic = 12;         // keep harmonics 1..N per turn of the measured error (0 = raw bins).
                                                      // Higher orders are cogging pulling the rotor off the field during
                                                      // the open-loop sweep (36x/42x on a 36N42P motor), not encoder error.


        // custom setters
        Encoder* parent = nullptr;
        void set_use_index(bool value) { use_index = value; parent->set_idx_subscribe(); }
        void set_find_idx_on_lockin_only(bool value) { find_idx_on_lockin_only = value; parent->set_idx_subscribe(); }
        void set_abs_spi_cs_gpio_pin(uint16_t value) { abs_spi_cs_gpio_pin = value; parent->abs_spi_cs_pin_init(); }
        void set_pre_calibrated(bool value) { pre_calibrated = value; parent->check_pre_calibrated(); }
        void set_bandwidth(float value) { bandwidth = value; parent->update_pll_gains(); }
    };

    Encoder(TIM_HandleTypeDef* timer, Stm32Gpio index_gpio,
            Stm32Gpio hallA_gpio, Stm32Gpio hallB_gpio, Stm32Gpio hallC_gpio,
            Stm32SpiArbiter* spi_arbiter);
    
    bool apply_config(ODriveIntf::MotorIntf::MotorType motor_type);
    void setup();
    void set_error(Error error);
    bool do_checks();

    void enc_index_cb();
    void set_idx_subscribe(bool override_enable = false);
    void update_pll_gains();
    void check_pre_calibrated();

    void set_linear_count(int32_t count);
    void set_circular_count(int32_t count, bool update_offset);
    bool calib_enc_offset(float voltage_magnitude);

    bool run_index_search();
    bool run_direction_find();
    bool run_hall_polarity_calibration();
    bool run_hall_phase_calibration();
    bool run_offset_calibration();
    void sample_now();
    bool read_sampled_gpio(Stm32Gpio gpio);
    void decode_hall_samples();
    int32_t hall_model(float internal_pos);
    bool update();

    TIM_HandleTypeDef* timer_;
    Stm32Gpio index_gpio_;
    Stm32Gpio hallA_gpio_;
    Stm32Gpio hallB_gpio_;
    Stm32Gpio hallC_gpio_;
    Stm32SpiArbiter* spi_arbiter_;
    Axis* axis_ = nullptr; // set by Axis constructor

    Config_t config_;

    Error error_ = ERROR_NONE;
    bool index_found_ = false;
    bool is_ready_ = false;
    int32_t shadow_count_ = 0;
    int32_t count_in_cpr_ = 0;
    float interpolation_ = 0.0f;
    OutputPort<float> phase_ = 0.0f;     // [rad]
    OutputPort<float> phase_vel_ = 0.0f; // [rad/s]
    float pos_estimate_counts_ = 0.0f;  // [count]
    float pos_cpr_counts_ = 0.0f;  // [count]
    float delta_pos_cpr_counts_ = 0.0f;  // [count] phase detector result for debug
    float vel_estimate_counts_ = 0.0f;  // [count/s]
    float pll_kp_ = 0.0f;   // [count/s / count]
    float pll_ki_ = 0.0f;   // [(count/s^2) / count]
    float calib_scan_response_ = 0.0f; // debug report from offset calib
    int32_t pos_abs_ = 0;
    float spi_error_rate_ = 0.0f;
    // XDRIVE: SPI absolute encoder diagnostics (counted in abs_spi_cb).
    uint32_t spi_frame_count_ = 0;          // frames received
    uint32_t spi_error_flag_count_ = 0;     // AMS frames with bit 14 (error flag) set
    uint32_t spi_warning_flag_count_ = 0;   // AMS frames with bit 15 set (AS5047U: warning; AS5047P: parity)
    uint32_t spi_jump_count_ = 0;           // samples dropped by config.abs_spi_max_jump
    uint32_t spi_parity_error_count_ = 0;   // AMS frames with odd parity (counted whether or not they're dropped)
    uint32_t abs_spi_good_frames_ = 0;      // accepted samples; the jump filter waits for 16 (boot garbage)
    uint16_t spi_last_frame_ = 0;           // last raw AMS frame
    uint8_t abs_spi_jumps_in_row_ = 0;
    bool abs_spi_have_last_ = false;
    // XDRIVE: encoder correction table.
    int32_t pos_abs_raw_ = 0;            // last good raw absolute position, before correction
    bool correction_active_ = true;      // cleared while the correction calibration runs
    float correction_rms_ = 0.0f;        // [counts] rms of the error the last correction calibration measured
    float correction_peak_ = 0.0f;       // [counts] largest |error| it measured
    uint32_t correction_bins_ = 0;       // bins with samples in both directions (256 = full coverage)
    float correction_at(int32_t raw) const;
    bool run_correction_calibration();
    float get_correction(uint32_t index) { return index < 256 ? config_.correction_table[index] : 0.0f; }
    void set_correction(uint32_t index, float val) { if (index < 256) config_.correction_table[index] = val; }

    OutputPort<float> pos_estimate_ = 0.0f; // [turn]
    OutputPort<float> vel_estimate_ = 0.0f; // [turn/s]
    OutputPort<float> pos_circular_ = 0.0f; // [turn]

    bool pos_estimate_valid_ = false;
    bool vel_estimate_valid_ = false;

    int16_t tim_cnt_sample_ = 0; // 
    static const constexpr GPIO_TypeDef* ports_to_sample[] = { GPIOA, GPIOB, GPIOC };
    uint16_t port_samples_[sizeof(ports_to_sample) / sizeof(ports_to_sample[0])];
    // Updated by low_level pwm_adc_cb
    uint8_t hall_state_ = 0x0; // bit[0] = HallA, .., bit[2] = HallC
    std::optional<uint8_t> last_hall_cnt_ = std::nullopt; // Used to find hall edges for calibration
    bool calibrate_hall_phase_ = false;
    bool sample_hall_states_ = false;
    bool sample_hall_phase_ = false;
    std::array<int, 8> states_seen_count_; // for hall polarity calibration
    std::array<int, 6> hall_phase_calib_seen_count_;

    float sincos_sample_s_ = 0.0f;
    float sincos_sample_c_ = 0.0f;

    bool abs_spi_start_transaction();
    void abs_spi_cb(bool success);
    void abs_spi_cs_pin_init();
    bool abs_spi_pos_updated_ = false;
    Mode mode_ = MODE_INCREMENTAL;
    Stm32Gpio abs_spi_cs_gpio_;
    uint32_t abs_spi_cr1;
    uint32_t abs_spi_cr2;
    uint16_t abs_spi_dma_tx_[1] = {0xFFFF};
    uint16_t abs_spi_dma_rx_[1];
    Stm32SpiArbiter::SpiTask spi_task_;

    constexpr float getCoggingRatio(){
        return 1.0f / 3600.0f;
    }

};

#endif // __ENCODER_HPP
