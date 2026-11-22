# Testing

The firmware is tested on a bench stand, a DJI 10018 with an unloaded rotor on a Mini at 24 V, with the tools in `tools/`. Each test logs every sample to `logs/` and prints PASS or FAIL per check. Tests that move the motor use RAM-only settings, restore them and end with the axis IDLE. This page lists the tests, what they check, and how to run them on another board or motor.

## Host tests

`make test` (needs `clang++`; CI runs it on every push) runs two suites:

- the firmware's unit tests (`src/tests/`, built for the host with doctest): the trapezoidal trajectory planner, CAN signal packing, the timers and angle wrapping;
- the host tools' tests (`tools/tests/`), below.

The host tools' tests check:

- the CAN impedance and endpoint-access frames: the host codecs (`xdrive/impedance_frame.py`, `xdrive/endpoint_frame.py`) against the firmware's headers (`impedance_frame.hpp`, `endpoint_frame.hpp`), compiled on the host;
- the host library (`xdrive`): its generated names against the interface JSON, `Board` against a fake endpoint table, the USB link against a fake device, and the CAN bus against fake boards on python-can's virtual bus;
- the CAN database (`docs/cansimple.dbc`): the impedance command and a float message encode and decode as the host codec does;
- the bus current soft limits (`bus_limit.hpp`) against their contract, on 3,000 random operating points plus a grid;
- the host tools' sources: every tool compiles under the repo env's Python, and every property path a tool names as a string exists in the generated `xdrive.props`;
- the release notes extraction from `CHANGELOG.md`.

## Bench tests

| Tool | Motion | Checks | What it checks | Test stand |
|---|---|---|---|---|
| `safety_test.py` | Moves, about 1 min | 24 | Watchdog disarm and decelerate-and-hold (with and without a torque cap); soft limits in trap, velocity and torque control, and entering closed loop outside them; position and velocity following errors | 24/24 |
| `impedance_test.py` | Moves, about 25 s | 10 | Stiffness T/kp at kp 20 and 80; a setpoint step; a trap move; damping only; the watchdog hold from impedance control | 10/10 |
| `regen_test.py` | Moves, about 35 s, hard stops | 6 | Brake resistor duty; flux braking's d-axis current and its copper loss; flux braking and `I_bus_soft_min` against a hard stop; `I_bus_soft_max` against the draw while accelerating | 6/6 |
| `capture_test.py` | None | 14 | Capture's sample clock, data types, triggers, rejections and cost per control period | 14/14 |
| `regress.py` | Moves, about 1 min | Every metric against a baseline | Config, hold noise, moves of 1, 3 and 10 turns (tracking, settling, 4x ripple), disturbance rejection | No regressions |
| `profile_loop.py` | Holds | Report | Time of each task in one control period, and stack headroom | 73 µs busy of 125 µs |
| `spike_hunt.py` | Holds, small moves | Report | One-period glitches in the measured current, over USB and with the firmware's counter | See below |

**Rotor angle matters for comparisons.** Cogging (about 0.09 Nm on the 10018) makes hold noise, disturbance deflection and small-torque stiffness depend on where the rotor rests. `regress.py --hold-at F` turns the rotor to fractional turn F (with `move_to.py`) before the hold and disturbance steps, and a baseline records the angle it was taken at, so later runs use the same one.

**Current glitches** (`spike_hunt.py`): the measured current shows occasional one-period jumps of 0.2 to 2 A, from 0 to 16 per second on the test stand, varying with rotor angle and from run to run. Most are a jump in both measured phases followed by an opposite jump one period later; their cause, and whether they matter to a joint, are open.

## Validating a board or motor

1. Configure and calibrate it ([Getting started](getting-started.md)).
2. `python tools/dump_board.py --compare <your settings>.json`: 0 differences and no errors.
3. No motion: `python tools/capture_test.py`.
4. Motor moves: `python tools/safety_test.py`, then `impedance_test.py` and `regen_test.py`. Keep the rotor free of any load; the tests assume an unloaded rotor (regen's limits and the stiffness checks depend on it).
5. Motor moves: `python tools/regress.py --tag first --compare <your settings>.json --save-baseline --hold-at 0.5` saves a baseline for this board (`configs/regress-baseline_<serial>.json`).
6. After a firmware or setting change: `python tools/regress.py --tag <change> --compare <your settings>.json` compares every metric with the baseline and flags anything worse than its tolerance.

`move_test.py`, `hold_ab.py` and `disturb_test.py` are the building blocks: logged trap moves, hold-noise comparisons between setting variants, and torque steps against a hold. `analyze_settle.py`, `analyze_ripple.py` and `analyze_encoder.py` work offline on their logs.
