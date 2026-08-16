"""M33b - Dilithium rounding / hint primitives silicon gate for FIPS 204 ML-DSA
(Post-Quantum Cryptography).

Six modes cover the coefficient-wise operations called by ML-DSA KeyGen
(Power2Round), Sign (Decompose, MakeHint, CheckNormBound), and Verify (UseHint).
SampleInBall is intentionally handled by the host composer (M33d/e) rather
than on-tile - its inner loop is a sequential rejection sampler over SHAKE256
output, not a data-parallel op.

Reference: dilithium-py v1.4.0 (mirror of pq-crystals ref-C).

Run on laptop:
    python tests\\m33_mldsa\\test_dilithium_sampler_m33b.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

try:
    from dilithium_py.polynomials.polynomials import PolynomialRing
    from dilithium_py.utilities.utils import (
        check_norm_bound,
        decompose,
        make_hint,
        reduce_mod_pm,
        use_hint,
    )
except ImportError as exc:  # pragma: no cover
    print(f"ERROR: dilithium-py is required (pip install dilithium-py). {exc}")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Constants.
# ---------------------------------------------------------------------------
Q = 8380417
N = 256
D_BITS = 13
POW2D = 1 << D_BITS

# gamma_2 per param set, and corresponding alpha = 2 * gamma_2.
GAMMA2_44 = (Q - 1) // 88          # 95232
ALPHA_44 = 2 * GAMMA2_44           # 190464
GAMMA2_65 = (Q - 1) // 32          # 261888
ALPHA_65 = 2 * GAMMA2_65           # 523776


# ---------------------------------------------------------------------------
# Silicon dispatch. Prefer NPU runner, fall back to Python transliteration.
# ---------------------------------------------------------------------------
def _try_import_silicon():
    for mod, fn in (
        ("phoenix_sdr_dsp.silicon.m33b_runner", "run_m33b"),
        ("tests.m33_mldsa.m33b_runner", "run_m33b"),
    ):
        try:
            m = __import__(mod, fromlist=[fn])
            f = getattr(m, fn, None)
            if callable(f):
                return f, mod
        except Exception as _e:  # noqa: BLE001
            _ = _e
            continue
    return None, "no silicon runner import path"


_silicon_dispatch, _silicon_backend = _try_import_silicon()


def _ref_dispatch(mode, param, in_a, in_b):
    """Bit-exact Python transliteration of dilithium_sampler_kernel.cc."""
    def canon(r):
        return r % Q

    def reduce_pm(r, n):
        rr = r % n
        return rr - n if rr > (n >> 1) else rr

    def power2round(r):
        rp = canon(r)
        r0 = rp & (POW2D - 1)
        if r0 > (POW2D >> 1):
            r0 -= POW2D
        return (rp - r0) >> D_BITS, r0

    def decompose_c(r, alpha):
        rp = canon(r)
        half = alpha >> 1
        r0 = rp % alpha
        if r0 > half:
            r0 -= alpha
        if rp - r0 == Q - 1:
            return 0, r0 - 1
        return (rp - r0) // alpha, r0

    def high_bits_c(r, alpha):
        return decompose_c(r, alpha)[0]

    def use_hint_c(h, r, alpha):
        m = (Q - 1) // alpha
        r1, r0 = decompose_c(r, alpha)
        if h != 0:
            if r0 > 0:
                return (r1 + 1) % m
            return (r1 - 1 + m) % m
        return r1

    if mode == 0:  # POWER2ROUND
        c, d = [], []
        for r in in_a:
            r1, r0 = power2round(r)
            c.append(r1)
            d.append(r0)
        return c, d
    if mode == 1:  # DECOMPOSE
        alpha = param
        c, d = [], []
        for r in in_a:
            r1, r0 = decompose_c(r, alpha)
            c.append(r1)
            d.append(r0)
        return c, d
    if mode == 2:  # MAKEHINT
        alpha = param
        c = []
        for z, r in zip(in_a, in_b):
            hb_r = high_bits_c(r, alpha)
            hb_rz = high_bits_c(r + z, alpha)
            c.append(1 if hb_r != hb_rz else 0)
        return c, [0] * N
    if mode == 3:  # USEHINT
        alpha = param
        c = []
        for h, r in zip(in_a, in_b):
            c.append(use_hint_c(h, r, alpha))
        return c, [0] * N
    if mode == 4:  # CHECKNORM
        bound = param
        all_ok = 1
        for r in in_a:
            rc = reduce_pm(r % Q, Q)
            mag = -rc if rc < 0 else rc
            if mag >= bound:
                all_ok = 0
        c = [0] * N
        c[0] = all_ok
        return c, [0] * N
    if mode == 5:  # REDUCE_PM
        c = [reduce_pm(r % Q, Q) for r in in_a]
        return c, [0] * N
    raise ValueError(mode)


def dispatch(mode, param, in_a, in_b=None):
    in_b = in_b or [0] * N
    if _silicon_dispatch is not None:
        return _silicon_dispatch(mode, param, list(in_a), list(in_b))
    return _ref_dispatch(mode, param, in_a, in_b)


# ---------------------------------------------------------------------------
# Gates.
# ---------------------------------------------------------------------------
_parent = PolynomialRing()


def _rand_poly(rng):
    return [rng.randrange(Q) for _ in range(N)]


def gate_power2round(n_trials=100, seed=20260901):
    rng = random.Random(seed)
    fails = 0
    for _ in range(n_trials):
        p = _rand_poly(rng)
        r1_got, r0_got = dispatch(0, 0, p)
        p_poly = _parent(list(p))
        r1_ref_poly, r0_ref_poly = p_poly.power_2_round(D_BITS)
        r1_ref = [x % (1 << 11) if False else x for x in r1_ref_poly.coeffs]  # keep as-is
        r0_ref = list(r0_ref_poly.coeffs)
        r1_ref = list(r1_ref_poly.coeffs)
        if r1_got == r1_ref and r0_got == r0_ref:
            continue
        fails += 1
        if fails <= 2:
            for i, (a, b, ra, rb) in enumerate(zip(r1_got, r0_got, r1_ref, r0_ref)):
                if a != ra or b != rb:
                    print(f"  P2R diff idx {i}: got r1={a} r0={b}, ref r1={ra} r0={rb}")
                    break
    return n_trials - fails, n_trials


def gate_decompose(alpha, n_trials=50, seed=20260902):
    rng = random.Random(seed + alpha)
    fails = 0
    for _ in range(n_trials):
        p = _rand_poly(rng)
        r1_got, r0_got = dispatch(1, alpha, p)
        r1_ref, r0_ref = [], []
        for r in p:
            r1, r0 = decompose(r, alpha, Q)
            r1_ref.append(r1)
            r0_ref.append(r0)
        if r1_got == r1_ref and r0_got == r0_ref:
            continue
        fails += 1
    return n_trials - fails, n_trials


def gate_makehint(alpha, n_trials=50, seed=20260903):
    rng = random.Random(seed + alpha)
    fails = 0
    for _ in range(n_trials):
        # z stays "small" like in real signing (bounded by gamma_2)
        z = [rng.randrange(-(alpha // 2), alpha // 2 + 1) for _ in range(N)]
        r = _rand_poly(rng)
        h_got, _ = dispatch(2, alpha, z, r)
        h_ref = [make_hint(z[i], r[i], alpha, Q) for i in range(N)]
        if h_got == h_ref:
            continue
        fails += 1
        if fails <= 2:
            for i, (a, b) in enumerate(zip(h_got, h_ref)):
                if a != b:
                    print(f"  MH diff idx {i}: got {a}, ref {b}, z={z[i]}, r={r[i]}")
                    break
    return n_trials - fails, n_trials


def gate_usehint(alpha, n_trials=50, seed=20260904):
    rng = random.Random(seed + alpha)
    fails = 0
    for _ in range(n_trials):
        r = _rand_poly(rng)
        z = [rng.randrange(-(alpha // 2), alpha // 2 + 1) for _ in range(N)]
        # produce hints using reference make_hint
        h = [make_hint(z[i], r[i], alpha, Q) for i in range(N)]
        got, _ = dispatch(3, alpha, h, r)
        ref = [use_hint(h[i], r[i], alpha, Q) for i in range(N)]
        if got == ref:
            continue
        fails += 1
    return n_trials - fails, n_trials


def gate_checknorm(n_trials=200, seed=20260905):
    rng = random.Random(seed)
    fails = 0
    bounds = [1 << 15, 1 << 17, 1 << 19, GAMMA2_44 - 78, GAMMA2_65 - 196]
    for _ in range(n_trials):
        b = rng.choice(bounds)
        # Mix polys whose coeffs are near the bound to stress the predicate.
        p = [rng.randrange(-(b + 1000), b + 1000) % Q for _ in range(N)]
        got, _ = dispatch(4, b, p)
        # check_norm_bound returns True if bound-exceeded (i.e. reject),
        # so overall predicate is: any coeff has |c| >= b.
        any_bad = any(check_norm_bound(c, b, Q) for c in p)
        expected = 0 if any_bad else 1
        if got[0] == expected:
            continue
        fails += 1
        if fails <= 2:
            print(f"  CN diff: got {got[0]}, expected {expected}, any_bad={any_bad}, b={b}")
    return n_trials - fails, n_trials


def gate_reduce_pm(n_trials=100, seed=20260906):
    rng = random.Random(seed)
    fails = 0
    for _ in range(n_trials):
        p = [rng.randrange(-4 * Q, 4 * Q) for _ in range(N)]
        got, _ = dispatch(5, 0, p)
        ref = [reduce_mod_pm(c % Q, Q) for c in p]
        if got == ref:
            continue
        fails += 1
    return n_trials - fails, n_trials


def main() -> int:
    print("=" * 72)
    print("M33b - Dilithium rounding / hint primitives silicon gate")
    print(f"  Q = {Q}, N = {N}, D_BITS = {D_BITS}")
    print(f"  backend: {_silicon_backend}")
    print("=" * 72)
    results = [
        ("MODE_POWER2ROUND      ", *gate_power2round()),
        (f"MODE_DECOMPOSE a={ALPHA_44}", *gate_decompose(ALPHA_44)),
        (f"MODE_DECOMPOSE a={ALPHA_65}", *gate_decompose(ALPHA_65)),
        (f"MODE_MAKEHINT  a={ALPHA_44}", *gate_makehint(ALPHA_44)),
        (f"MODE_MAKEHINT  a={ALPHA_65}", *gate_makehint(ALPHA_65)),
        (f"MODE_USEHINT   a={ALPHA_44}", *gate_usehint(ALPHA_44)),
        (f"MODE_USEHINT   a={ALPHA_65}", *gate_usehint(ALPHA_65)),
        ("MODE_CHECKNORM        ", *gate_checknorm()),
        ("MODE_REDUCE_PM        ", *gate_reduce_pm()),
    ]
    total_ok = total = 0
    all_ok = True
    for name, ok, n in results:
        status = "PASS" if ok == n else "FAIL"
        print(f"  {name:<28}  {ok:>4}/{n:<4}  {status}")
        total_ok += ok
        total += n
        if ok != n:
            all_ok = False
    print("-" * 72)
    print(f"  TOTAL{'':<24}  {total_ok:>4}/{total:<4}  {'PASS' if all_ok else 'FAIL'}")
    print("=" * 72)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
