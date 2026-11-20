#pragma once
// XDRIVE: bus current soft limits (motor.config.I_bus_soft_min/max) on the d/q current setpoints.
//
// With steady-state voltages the electrical power a PMSM draws from the bus is
//   P = 1.5 * (R * (id^2 + iq^2) + e * iq),   e = back-EMF amplitude = phase_vel * flux linkage
// (the inductive cross terms cancel), and the bus current is P / vbus. apply() keeps
// I_bus_soft_min * vbus <= P <= I_bus_soft_max * vbus (limits taken as soft_min <= 0 <= soft_max):
//   - Regen side (braking, e * iq < 0): first add d-axis current, which burns the excess as copper
//     loss without changing torque. Only when the current limit leaves no room does braking iq
//     shrink, to iq_b, the most braking that full current (id^2 + iq^2 = ilim^2) can absorb:
//     R * ilim^2 + e * iq_b = soft_min * vbus / 1.5. So a motor can brake with no regen at all, as
//     hard as its own windings can dissipate.
//   - Draw side: P is convex in iq, so P <= soft_max * vbus holds between two roots; iq is clamped
//     to them (to the minimum-power point when the d-axis loss alone breaks the limit).
// iq_min/iq_max are the resulting bounds on iq; the controller uses them (one period late) to clamp
// its torque and stop its velocity integrator from winding up.
//
// Pure function, no firmware dependencies: the host tests compile this header.

#include <algorithm>
#include <cmath>

namespace bus_limit {

struct Output {
    float id;
    float iq;
    float iq_min;
    float iq_max;
};

// iq: requested torque current (already within the current limit together with id).
// id: d-axis current already requested (flux braking; <= 0). ilim: current limit (2-norm).
inline Output apply(float iq, float id, float ilim, float R, float e, float vbus, float soft_min, float soft_max) {
    R = std::max(R, 1e-6f);
    const float p_min = std::min(soft_min, 0.0f) * vbus / 1.5f;  // in units of R * I^2 + e * I
    const float p_max = std::max(soft_max, 0.0f) * vbus / 1.5f;
    Output o{id, iq, -INFINITY, INFINITY};

    if (std::isfinite(p_min) && e != 0.0f) {
        const float iq_b = (p_min - R * ilim * ilim) / e;  // between 0 and the braking direction
        if (e > 0.0f) {
            o.iq_min = iq_b;
        } else {
            o.iq_max = iq_b;
        }
        o.iq = std::clamp(o.iq, o.iq_min, o.iq_max);
        // id^2 that lifts P to the limit. It fits the current limit: need + iq^2 = (p_min - e * iq) / R,
        // which is at most ilim^2 for iq between 0 and iq_b.
        const float need = (p_min - e * o.iq) / R - o.iq * o.iq;
        if (need > id * id) {
            o.id = -std::sqrt(need);
        }
    }

    if (std::isfinite(p_max)) {
        const float disc = e * e - 4.0f * R * (R * o.id * o.id - p_max);
        const float r = disc > 0.0f ? std::sqrt(disc) : 0.0f;
        o.iq_min = std::max(o.iq_min, (-e - r) / (2.0f * R));
        o.iq_max = std::min(o.iq_max, (-e + r) / (2.0f * R));
        o.iq = std::clamp(o.iq, o.iq_min, std::max(o.iq_min, o.iq_max));
    }
    return o;
}

}  // namespace bus_limit
