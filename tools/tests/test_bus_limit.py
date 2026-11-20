"""The firmware's bus current soft limits (bus_limit.hpp, compiled with clang++) against their contract.

P(id, iq) = 1.5 * (R * (id^2 + iq^2) + e * iq) is the predicted bus power. For random operating points the
output must: stay within the current limit; keep P >= soft_min * vbus wherever full current can absorb the
regen; keep P <= soft_max * vbus whenever iq = 0 can; leave a request that already meets both limits
unchanged; only add d-axis current (never remove flux braking) and only on the regen side; give up braking
torque only when the current limit forces it; and on the draw side return the largest allowed iq, which a
0.005 A grid search confirms. Run from the repo root: python -m pytest -q tools/tests
"""
import math
import pathlib
import random
import subprocess

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent
FIRMWARE = HERE.parents[1] / "src"
STEP, SPAN = 0.005, 250.0
TOL = 1e-3


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    exe = tmp_path_factory.mktemp("cli") / "bus_limit_cli"
    subprocess.run(["clang++", "-std=c++17", "-O1", "-I", str(FIRMWARE), str(HERE / "bus_limit_cli.cpp"),
                    "-o", str(exe)], check=True)
    return exe


def run(cli, cases):
    text = "\n".join(" ".join(repr(float(x)) for x in c) for c in cases) + "\n"
    out = subprocess.run([str(cli)], input=text, capture_output=True, text=True, check=True).stdout.split("\n")
    return [tuple(float(x) for x in line.split()) for line in out[:len(cases)]]


def power(id_, iq, R, e):
    return 1.5 * (R * (id_ ** 2 + iq ** 2) + e * iq)


def random_cases(seed, n):
    rnd = random.Random(seed)
    cases = []
    for _ in range(n):
        ilim = rnd.uniform(5, 20)
        id_ = -rnd.choice([0.0, rnd.uniform(0, 0.7 * ilim)])
        iq_room = math.sqrt(ilim ** 2 - id_ ** 2)
        cases.append((rnd.uniform(-iq_room, iq_room), id_, ilim, rnd.uniform(0.04, 0.5), rnd.uniform(-8, 8),
                      rnd.uniform(20, 30), rnd.choice([-math.inf, rnd.uniform(-5, 0.5)]),
                      rnd.choice([math.inf, rnd.uniform(-0.5, 20)])))
    return cases


def test_contract(cli):
    cases = random_cases(1, 3000)
    for c, (id_o, iq_o, iq_min, iq_max) in zip(cases, run(cli, cases)):
        iq, id_, ilim, R, e, vbus, smin, smax = c
        p_min, p_max = min(smin, 0) * vbus, max(smax, 0) * vbus
        tol = TOL * max([1.0] + [abs(x) for x in (p_min, p_max) if math.isfinite(x)])
        p_out = power(id_o, iq_o, R, e)
        assert id_o ** 2 + iq_o ** 2 <= ilim ** 2 * (1 + 1e-5), c
        assert id_o <= id_ + 1e-6, c                          # d-axis current only ever added
        assert iq_min - 1e-4 <= iq_o <= max(iq_min, iq_max) + 1e-4, c
        if p_min <= power(id_, iq, R, e) <= p_max:
            assert (id_o, iq_o) == pytest.approx((id_, iq), abs=1e-5), c   # nothing to do
            continue
        if id_o < id_ - 1e-6:
            assert e * iq_o < 0, c                            # burning happens only while braking
        if power(id_, 0.0, R, e) <= p_max and p_min > -math.inf:
            # Regen side: P reaches the limit unless full current is used, and braking shrinks only then.
            full = math.isclose(id_o ** 2 + iq_o ** 2, ilim ** 2, rel_tol=1e-4)
            assert p_out >= p_min - tol or full, c
            if not full and e * iq < 0 and power(id_, iq, R, e) < p_min:
                assert iq_o == pytest.approx(iq, abs=1e-4), c
        if power(id_o, 0.0, R, e) <= p_max:
            assert p_out <= p_max + tol, c


def test_draw_side_is_tight(cli):
    """With no regen limit, iq is the request clamped to the grid interval around 0 where P <= p_max."""
    cases = [c[:6] + (-math.inf, c[7]) for c in random_cases(2, 1500) if math.isfinite(c[7])]
    for c, (id_o, iq_o, _, _) in zip(cases, run(cli, cases)):
        iq, id_, ilim, R, e, vbus, _, smax = c
        p_max = max(smax, 0) * vbus
        n = int(SPAN / STEP)
        grid = np.arange(-n, n + 1) * STEP
        ok = power(id_, grid, R, e) <= p_max + 1e-9
        assert id_o == pytest.approx(id_, abs=1e-5)
        if not ok.any():
            assert iq_o == pytest.approx(-e / (2 * R), abs=1e-3), c
            continue
        assert ok[n] or power(id_, 0.0, R, e) > p_max, c
        if ok[n]:
            hi = n + np.argmin(ok[n:]) - 1 if not ok[n:].all() else None
            lo = n - np.argmin(ok[n::-1]) + 1 if not ok[n::-1].all() else None
            want = min(max(iq, grid[lo] if lo is not None else -math.inf), grid[hi] if hi is not None else math.inf)
            assert iq_o == pytest.approx(want, abs=STEP + 1e-3 * abs(want)), c


def test_examples(cli):
    R, e, ilim = 0.056, 4.5, 15.0  # the 10018 at 10 turn/s: back-EMF amplitude 4.5 V
    cases = [
        (-2.0, 0.0, ilim, R, e, 24.0, -math.inf, math.inf),  # no limits: unchanged
        (-2.0, 0.0, ilim, R, e, 24.0, 0.0, math.inf),        # no regen: 2 A of braking paid for with Id
        (-10.0, 0.0, ilim, R, e, 24.0, 0.0, math.inf),       # more than full current can burn
        (10.0, 0.0, ilim, R, e, 24.0, -math.inf, 0.3),       # 0.3 A draw cap
    ]
    out = run(cli, cases)
    assert out[0] == (0.0, -2.0, -math.inf, math.inf)
    id_, iq, _, _ = out[1]
    assert iq == -2.0 and R * (id_ ** 2 + 4) == pytest.approx(e * 2, rel=1e-4)  # P = 0
    id_, iq, iq_min, _ = out[2]
    assert iq == pytest.approx(-R * ilim ** 2 / e, rel=1e-4) == iq_min           # iq_b = -2.8 A
    assert id_ ** 2 + iq ** 2 == pytest.approx(ilim ** 2, rel=1e-4)
    assert out[3][1] == pytest.approx(24.0 * 0.3 / (1.5 * e), rel=0.02)
