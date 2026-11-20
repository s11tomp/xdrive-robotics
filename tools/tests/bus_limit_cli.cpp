// Test driver for the firmware's bus_limit.hpp, used by test_bus_limit.py.
// Reads lines "<iq> <id> <ilim> <R> <e> <vbus> <soft_min> <soft_max>" from stdin (inf/-inf allowed) and
// writes "<id> <iq> <iq_min> <iq_max>" from bus_limit::apply() for each.
#include <cstdio>

#include "MotorControl/bus_limit.hpp"

int main() {
    float iq, id, ilim, R, e, vbus, smin, smax;
    while (std::scanf("%f %f %f %f %f %f %f %f", &iq, &id, &ilim, &R, &e, &vbus, &smin, &smax) == 8) {
        const bus_limit::Output o = bus_limit::apply(iq, id, ilim, R, e, vbus, smin, smax);
        std::printf("%.9g %.9g %.9g %.9g\n", o.id, o.iq, o.iq_min, o.iq_max);
    }
    return 0;
}
