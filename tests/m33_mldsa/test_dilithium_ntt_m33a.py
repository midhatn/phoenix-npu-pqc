"""M33a - Dilithium NTT / INTT / BASEMUL / REDUCE silicon gate for FIPS 204
ML-DSA (Post-Quantum Cryptography).

The kernel dispatches four modes on the Phoenix NPU (AIE2) via the M32b-style
runner. This test invokes each mode against reference outputs from
dilithium-py v1.4.0, with the Montgomery <-> plain-modular bridge applied in
host Python (matching the pattern established in M32e's SiliconBackend).

Reference implementation
    https://github.com/GiacomoPope/dilithium-py  (Python, tag v1.4.0)
    Mirrors pq-crystals/dilithium ref-C, https://github.com/pq-crystals/dilithium

FIPS 204 authoritative spec
    https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf

Run on laptop (PowerShell) from repo root:
    python tests\\m33_mldsa\\test_dilithium_ntt_m33a.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dilithium_py.polynomials.polynomials import PolynomialRing
except ImportError as exc:  # pragma: no cover - laptop must have it installed
    print(f"ERROR: dilithium-py is required (pip install dilithium-py). {exc}")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Dilithium constants (FIPS 204, Section 4). Verified against pq-crystals ref-C.
# ---------------------------------------------------------------------------
Q: int = 8380417
N: int = 256
R_POW: int = 32
R_MOD_Q: int = (1 << R_POW) % Q          # 4193792
R_INV_MOD_Q: int = pow(1 << R_POW, -1, Q)


# ---------------------------------------------------------------------------
# Silicon dispatch.  This is a silicon gate: it never converts an unavailable
# MLIR-AIE runtime into a Python-reference success.
# ---------------------------------------------------------------------------
def _try_import_silicon():
    """Return the native-only runner, or an honest unavailability diagnostic."""
    try:
        from phoenix_sdr_dsp.silicon import m33a_runner

        m33a_runner.require_hardware_runtime()
        return m33a_runner.run_m33a, "m33a:silicon"
    except Exception as exc:  # noqa: BLE001 - report all native setup failures
        return None, f"m33a:unavailable ({type(exc).__name__}: {exc})"


_silicon_dispatch, _silicon_backend = _try_import_silicon()


def _load_python_reference_kernel():
    """Bit-exact Python transliteration of dilithium_ntt_kernel.cc.

    This is the same code paths as the .cc kernel; it exists so the sandbox
    can gate the algorithm even without an attached NPU. On the laptop, the
    silicon dispatch (above) supersedes this.
    """
    QINV = 58728449  # Q * QINV = 1 mod 2^32

    # Zetas mont (bit-reversed, signed i32) - identical to kernel array.
    def _br(i, k=8):
        return int(bin(i & ((1 << k) - 1))[2:].zfill(k)[::-1], 2)

    _z_plain = [pow(1753, _br(i, 8), Q) for i in range(N)]

    def _ctr(x):
        x %= Q
        return x - Q if x > Q // 2 else x

    zetas_mont = [_ctr((z * (1 << 32)) % Q) for z in _z_plain]
    zetas_mont[0] = 0

    def _i32(x):
        x &= 0xFFFFFFFF
        return x - (1 << 32) if x >= (1 << 31) else x

    def _mont(a):
        t = _i32(a * QINV)
        return (a - t * Q) >> 32

    def ntt(coeffs):
        c = list(coeffs)
        k = 0
        length = 128
        while length > 0:
            start = 0
            while start < N:
                k += 1
                zeta = zetas_mont[k]
                j = start
                for j in range(start, start + length):
                    t = _mont(zeta * c[j + length])
                    c[j + length] = c[j] - t
                    c[j] = c[j] + t
                start = j + length + 1
            length >>= 1
        return c

    def invntt(coeffs):
        f_mont = 41978
        c = list(coeffs)
        k = 256
        length = 1
        while length < N:
            start = 0
            while start < N:
                k -= 1
                zeta = -zetas_mont[k]
                j = start
                for j in range(start, start + length):
                    t = c[j]
                    c[j] = t + c[j + length]
                    c[j + length] = t - c[j + length]
                    c[j + length] = _mont(zeta * c[j + length])
                start = j + length + 1
            length <<= 1
        return [_mont(f_mont * c[j]) for j in range(N)]

    def basemul(a, b):
        return [_mont(a[i] * b[i]) for i in range(N)]

    def reduce_mode(a):
        out = []
        for x in a:
            t = (x + (1 << 22)) >> 23
            out.append(x - t * Q)
        return out

    def dispatch(mode: int, in_a, in_b=None):
        if mode == 0:
            return ntt(in_a)
        if mode == 1:
            return invntt(in_a)
        if mode == 2:
            return basemul(in_a, in_b)
        if mode == 3:
            return reduce_mode(in_a)
        raise ValueError(mode)

    return dispatch


def dispatch(mode: int, in_a, in_b=None):
    """Dispatch only to M33a; absence of silicon is a test failure."""
    if _silicon_dispatch is None:
        raise RuntimeError(
            "M33a hardware runner is unavailable. This silicon gate does not "
            "fall back to the Python transliteration."
        )
    return _silicon_dispatch(
        mode, list(in_a), list(in_b) if in_b is not None else None
    )


# ---------------------------------------------------------------------------
# Composer bridge to reference plain-modular semantics.
# ---------------------------------------------------------------------------
def kernel_ntt_plain(coeffs):
    """Silicon NTT output already matches plain modular semantics."""
    return [x % Q for x in dispatch(0, coeffs)]


def kernel_intt_plain(ntt_coeffs):
    """Silicon INTT bakes in an implicit factor of R; strip it."""
    return [(x * R_INV_MOD_Q) % Q for x in dispatch(1, ntt_coeffs)]


def kernel_basemul_plain(a, b):
    """Silicon basemul returns (a*b*R^-1); post-scale by R to get plain product."""
    return [(x * R_MOD_Q) % Q for x in dispatch(2, a, b)]


def kernel_reduce(a):
    return dispatch(3, a)


# ---------------------------------------------------------------------------
# dilithium-py reference oracles.
# ---------------------------------------------------------------------------
_parent = PolynomialRing()


def ref_ntt(coeffs):
    return list(_parent(list(coeffs)).to_ntt().coeffs)


def ref_intt(ntt_coeffs):
    return list(_parent(list(ntt_coeffs), is_ntt=True).from_ntt().coeffs)


# ---------------------------------------------------------------------------
# Gates.
# ---------------------------------------------------------------------------
def _rand_poly(rng):
    return [rng.randrange(Q) for _ in range(N)]


def gate_ntt(n_trials=50, seed=20260816):
    rng = random.Random(seed)
    fails = 0
    for t in range(n_trials):
        p = _rand_poly(rng)
        got = kernel_ntt_plain(p)
        ref = [x % Q for x in ref_ntt(p)]
        if got != ref:
            fails += 1
            if fails <= 3:
                for i, (a, b) in enumerate(zip(got, ref)):
                    if a != b:
                        print(f"  NTT trial {t} idx {i}: got {a}, ref {b}")
                        break
    return n_trials - fails, n_trials


def gate_intt(n_trials=50, seed=20260817):
    rng = random.Random(seed)
    fails = 0
    for t in range(n_trials):
        p = _rand_poly(rng)
        p_ntt = ref_ntt(p)
        got = kernel_intt_plain(p_ntt)
        ref = [x % Q for x in ref_intt(p_ntt)]
        if got != ref:
            fails += 1
    return n_trials - fails, n_trials


def gate_basemul(n_trials=100, seed=20260818):
    rng = random.Random(seed)
    fails = 0
    for t in range(n_trials):
        a = _rand_poly(rng)
        b = _rand_poly(rng)
        got = kernel_basemul_plain(a, b)
        ref = [(a[i] * b[i]) % Q for i in range(N)]
        if got != ref:
            fails += 1
    return n_trials - fails, n_trials


def gate_reduce(n_trials=200, seed=20260819):
    rng = random.Random(seed)
    fails = 0
    for _ in range(n_trials):
        # Range chosen to exercise (-2q, 2q) which is the actual output range
        # of NTT butterflies (worst case).
        p = [rng.randrange(-2 * Q, 2 * Q) for _ in range(N)]
        got = kernel_reduce(p)
        for i, x in enumerate(got):
            if x % Q != p[i] % Q:
                fails += 1
                break
            if not (-6283009 < x < 6283009):
                fails += 1
                break
    return n_trials - fails, n_trials


def gate_polymul(n_trials=20, seed=20260820):
    """Full ntt-basemul-invntt round trip vs schoolbook negacyclic multiply."""
    rng = random.Random(seed)
    fails = 0
    for _ in range(n_trials):
        a = _rand_poly(rng)
        b = _rand_poly(rng)
        # Schoolbook reference
        prod = [0] * N
        for i in range(N):
            for j in range(N):
                k = (i + j) % N
                sgn = -1 if (i + j) >= N else 1
                prod[k] = (prod[k] + sgn * a[i] * b[j]) % Q
        a_ntt = kernel_ntt_plain(a)
        b_ntt = kernel_ntt_plain(b)
        # basemul on plain values requires no bridge if we use ref_ntt/intt,
        # but the silicon pipeline is: kernel_ntt (plain in/out), silicon_basemul
        # (returns *R^-1), kernel_invntt (returns *R). Net factor cancels.
        c_bm_r_inv = dispatch(2, a_ntt, b_ntt)     # implicit R^-1
        c_time = dispatch(1, c_bm_r_inv)           # implicit R (cancels)
        got = [x % Q for x in c_time]
        if got != prod:
            fails += 1
    return n_trials - fails, n_trials


# ---------------------------------------------------------------------------
# Runner.
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 72)
    print("M33a - Dilithium NTT/INTT/BASEMUL/REDUCE silicon gate")
    print(f"  Q = {Q}, N = {N}, R = 2^{R_POW}")
    print(f"Backend: {_silicon_backend}")
    print("=" * 72)
    if _silicon_dispatch is None:
        print("FAIL: native M33a MLIR-AIE/IRON runner is required; no reference fallback ran.")
        return 2

    results = [
        ("MODE_NTT      ", *gate_ntt()),
        ("MODE_INTT     ", *gate_intt()),
        ("MODE_BASEMUL  ", *gate_basemul()),
        ("MODE_REDUCE   ", *gate_reduce()),
        ("end-to-end mul", *gate_polymul()),
    ]
    total_pass = 0
    total = 0
    all_ok = True
    for name, ok, n in results:
        status = "PASS" if ok == n else "FAIL"
        print(f"  {name}  {ok:>4}/{n:<4}  {status}")
        total_pass += ok
        total += n
        if ok != n:
            all_ok = False
    print("-" * 72)
    print(f"  TOTAL         {total_pass:>4}/{total:<4}  {'PASS' if all_ok else 'FAIL'}")
    print("=" * 72)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
