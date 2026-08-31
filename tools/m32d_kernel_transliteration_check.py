"""M32d transliteration cross-check.

Runs the Python host reference in tests/m32_mlkem/test_kpke_m32d.py against a
completely independent second-source implementation of every primitive:

    Compress_d      : y = round((2^d / q) * x) mod 2^d               (FIPS 203 (4.7))
    Decompress_d    : x = round((q / 2^d) * y)                         (FIPS 203 (4.8))
    ByteEncode_d    : pack d-bit chunks of coefficients little-endian
    ByteDecode_d    : unpack d-bit chunks, mask to 2^d

The primary implementation uses the pq-crystals magic-constant fast paths
(the "d0 *= 80635; d0 >>= 28" style), which is what pq-crystals ships and
what our AIE2 kernel executes verbatim. The second source uses exact rational
rounding of (2^d / q) * x with Python integers -- no magic constants, no
overflow-window tricks. If any transliteration error crept into the primary,
the two paths disagree.

References:
  * FIPS 203, Section 4.2.1 https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
  * pq-crystals ref/poly.c   https://github.com/pq-crystals/kyber/blob/main/ref/poly.c
  * pq-crystals ref/polyvec.c https://github.com/pq-crystals/kyber/blob/main/ref/polyvec.c

Sandbox invocation:
    python tools/m32d_kernel_transliteration_check.py
"""

import sys
import types
from pathlib import Path

import numpy as np

KYBER_N = 256
KYBER_Q = 3329


class _CompileTimeStub:
    def __init__(self, *a, **kw):
        pass

    def __class_getitem__(cls, item):
        return cls

    def __call__(self, *a, **kw):
        return self


def _load_reference():
    """Stub the aie.* modules and load the primary reference (test_kpke_m32d)."""
    stub_modules = [
        "aie", "aie.iron", "aie.utils", "aie.utils.config",
        "aie.utils.hostruntime", "aie.utils.hostruntime.xrtruntime",
        "aie.utils.hostruntime.xrtruntime.tensor",
    ]
    stub_attrs = {
        "iron": type("iron", (), {"jit": lambda f: f,
                                  "get_current_device": lambda: None}),
        "CompileTime": _CompileTimeStub,
        "ExternalFunction": _CompileTimeStub,
        "In": _CompileTimeStub,
        "ObjectFifo": _CompileTimeStub,
        "Out": _CompileTimeStub,
        "Program": _CompileTimeStub,
        "Runtime": _CompileTimeStub,
        "Worker": _CompileTimeStub,
        "cxx_header_path": lambda: "",
        "XRTTensor": _CompileTimeStub,
    }
    for name in stub_modules:
        m = types.ModuleType(name)
        for k, v in stub_attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.m32_mlkem import test_kpke_m32d as t
    return t


ref = _load_reference()


# ------------------------------------------------------------------
# Second-source (independent) implementations.

def _round_half_up(num, den):
    """floor((num + den/2) / den) -- rounds ties up, matching Kyber's
    round-to-nearest, ties-away-from-zero for non-negative values.

    pq-crystals uses this convention throughout Compress/Decompress.
    """
    return (num + den // 2) // den


def indep_compress_d(x, d):
    """FIPS 203 (4.7): Compress_d(x) = round((2^d / q) * x) mod 2^d.

    x must be a non-negative canonical representative in [0, q-1].
    """
    v = _round_half_up((1 << d) * int(x), KYBER_Q)
    return v & ((1 << d) - 1)


def indep_decompress_d(y, d):
    """FIPS 203 (4.8): Decompress_d(y) = round((q / 2^d) * y)."""
    return _round_half_up(KYBER_Q * int(y), 1 << d)


def indep_canonical(v):
    """Map signed int16 to canonical [0, q-1]."""
    return int(v) % KYBER_Q


def indep_compress_d4_bytes(coeffs):
    """256 int16 -> 128 uint8, using indep_compress_d and byte packing."""
    codewords = np.array(
        [indep_compress_d(indep_canonical(int(c)), 4) for c in coeffs],
        dtype=np.uint16)
    out = np.zeros(128, dtype=np.uint8)
    for i in range(KYBER_N // 2):
        out[i] = (codewords[2 * i] | (codewords[2 * i + 1] << 4)) & 0xFF
    return out


def indep_decompress_d4_from_bytes(bytes128):
    """128 uint8 -> 256 int16 in [0, q-1]."""
    out = np.zeros(KYBER_N, dtype=np.int16)
    for i in range(KYBER_N // 2):
        a0 = int(bytes128[i])
        lo = a0 & 15
        hi = a0 >> 4
        out[2 * i + 0] = indep_decompress_d(lo, 4)
        out[2 * i + 1] = indep_decompress_d(hi, 4)
    return out


def indep_compress_d10_bytes(coeffs):
    """256 int16 -> 320 uint8, d=10, using indep_compress_d and byte packing."""
    codewords = np.array(
        [indep_compress_d(indep_canonical(int(c)), 10) for c in coeffs],
        dtype=np.uint16)
    out = np.zeros(320, dtype=np.uint8)
    r = 0
    for j in range(KYBER_N // 4):
        t0 = int(codewords[4 * j + 0])
        t1 = int(codewords[4 * j + 1])
        t2 = int(codewords[4 * j + 2])
        t3 = int(codewords[4 * j + 3])
        out[r + 0] = t0 & 0xFF
        out[r + 1] = ((t0 >> 8) | (t1 << 2)) & 0xFF
        out[r + 2] = ((t1 >> 6) | (t2 << 4)) & 0xFF
        out[r + 3] = ((t2 >> 4) | (t3 << 6)) & 0xFF
        out[r + 4] = (t3 >> 2) & 0xFF
        r += 5
    return out


def indep_decompress_d10_from_bytes(bytes320):
    out = np.zeros(KYBER_N, dtype=np.int16)
    a = 0
    for j in range(KYBER_N // 4):
        a0, a1, a2, a3, a4 = (int(bytes320[a + i]) for i in range(5))
        t0 = ((a0 >> 0) | (a1 << 8)) & 0x3FF
        t1 = ((a1 >> 2) | (a2 << 6)) & 0x3FF
        t2 = ((a2 >> 4) | (a3 << 4)) & 0x3FF
        t3 = ((a3 >> 6) | (a4 << 2)) & 0x3FF
        out[4 * j + 0] = indep_decompress_d(t0, 10)
        out[4 * j + 1] = indep_decompress_d(t1, 10)
        out[4 * j + 2] = indep_decompress_d(t2, 10)
        out[4 * j + 3] = indep_decompress_d(t3, 10)
        a += 5
    return out


def indep_tobytes_d12(coeffs):
    """Pure serialization: 12 bits per coefficient, little-endian pairs."""
    out = np.zeros(384, dtype=np.uint8)
    for i in range(KYBER_N // 2):
        t0 = indep_canonical(int(coeffs[2 * i + 0]))
        t1 = indep_canonical(int(coeffs[2 * i + 1]))
        out[3 * i + 0] = t0 & 0xFF
        out[3 * i + 1] = ((t0 >> 8) & 0x0F) | ((t1 & 0x0F) << 4)
        out[3 * i + 2] = (t1 >> 4) & 0xFF
    return out


def indep_frombytes_d12(bytes384):
    out = np.zeros(KYBER_N, dtype=np.int16)
    for i in range(KYBER_N // 2):
        b0, b1, b2 = int(bytes384[3 * i + 0]), int(bytes384[3 * i + 1]), int(bytes384[3 * i + 2])
        c0 = (b0 | ((b1 & 0x0F) << 8)) & 0xFFF
        c1 = ((b1 >> 4) | (b2 << 4)) & 0xFFF
        out[2 * i + 0] = c0
        out[2 * i + 1] = c1
    return out


def indep_frommsg(msg32):
    out = np.zeros(KYBER_N, dtype=np.int16)
    mask = (KYBER_Q + 1) // 2
    for i in range(32):
        mi = int(msg32[i])
        for j in range(8):
            out[8 * i + j] = ((mi >> j) & 1) * mask
    return out


def indep_tomsg(coeffs):
    """FIPS 203-consistent: bit_j = Compress_1(coeff_j) using exact rational rounding."""
    out = np.zeros(32, dtype=np.uint8)
    for i in range(32):
        mi = 0
        for j in range(8):
            c = indep_canonical(int(coeffs[8 * i + j]))
            b = indep_compress_d(c, 1)
            mi |= (b & 1) << j
        out[i] = mi
    return out


from dataclasses import dataclass

@dataclass(frozen=True)
class CheckResult:
    name: str
    selected: int
    executed: int
    passed: int
    failed: int


# ------------------------------------------------------------------
# Cross-checks

def _random_signed_poly(rng):
    v = rng.integers(0, KYBER_Q, size=KYBER_N).astype(np.int64)
    v = np.where(v > KYBER_Q // 2, v - KYBER_Q, v).astype(np.int16)
    return v


def check1_canonical() -> CheckResult:
    """(1) _canonical primary vs indep_canonical over full int16 range restricted
    to values the reference could ever encounter after ntt_inverse (broad window)."""
    selected = 2 * KYBER_Q
    executed = 0
    passed = 0
    failed = 0
    # Full canonical range test
    for v in range(-KYBER_Q, KYBER_Q):
        executed += 1
        prim = ref._canonical(v) & 0xFFFF
        indep = v % KYBER_Q
        if (prim % KYBER_Q) == indep:
            passed += 1
        else:
            failed += 1
    print(f"[cross] (1) _canonical primary vs bigint modular over [-q, q): {passed}/{executed} matched ({failed} failed)")
    return CheckResult("canonical", selected, executed, passed, failed)


def check2_compress_d4() -> CheckResult:
    """(2) primary ref_compress_d4/decompress_d4 vs independent implementation."""
    rng = np.random.default_rng(0xCC01)
    selected = 10
    executed = 0
    passed = 0
    failed = 0

    for k in range(5):
        executed += 1
        a = _random_signed_poly(rng)
        prim_bytes = ref.ref_compress_d4(a)
        indep_bytes = indep_compress_d4_bytes(a)
        if np.array_equal(prim_bytes, indep_bytes):
            passed += 1
        else:
            failed += 1

    # Decompress on random 128-byte streams
    for k in range(5):
        executed += 1
        y = rng.integers(0, 256, size=128, dtype=np.uint8)
        p1 = ref.ref_decompress_d4(y)
        p2 = indep_decompress_d4_from_bytes(y)
        if np.array_equal(p1, p2):
            passed += 1
        else:
            failed += 1

    print(f"[cross] (2) compress/decompress d=4 primary vs indep: {passed}/{executed} matched ({failed} failed)")
    return CheckResult("compress_d4", selected, executed, passed, failed)


def check3_compress_d10() -> CheckResult:
    """(3) primary ref_compress_d10/decompress_d10 vs independent."""
    rng = np.random.default_rng(0xCC02)
    selected = 10
    executed = 0
    passed = 0
    failed = 0

    for k in range(5):
        executed += 1
        a = _random_signed_poly(rng)
        p = ref.ref_compress_d10(a)
        i = indep_compress_d10_bytes(a)
        if np.array_equal(p, i):
            passed += 1
        else:
            failed += 1

    for k in range(5):
        executed += 1
        y = rng.integers(0, 256, size=320, dtype=np.uint8)
        p1 = ref.ref_decompress_d10(y)
        p2 = indep_decompress_d10_from_bytes(y)
        if np.array_equal(p1, p2):
            passed += 1
        else:
            failed += 1

    print(f"[cross] (3) compress/decompress d=10 primary vs indep: {passed}/{executed} matched ({failed} failed)")
    return CheckResult("compress_d10", selected, executed, passed, failed)


def check4_tobytes_d12() -> CheckResult:
    """(4) primary ref_tobytes_d12/frombytes_d12 vs independent serialization."""
    rng = np.random.default_rng(0xCC03)
    selected = 10
    executed = 0
    passed = 0
    failed = 0

    for k in range(5):
        executed += 1
        a = _random_signed_poly(rng)
        p1 = ref.ref_tobytes_d12(a)
        p2 = indep_tobytes_d12(a)
        if np.array_equal(p1, p2):
            passed += 1
        else:
            failed += 1

    for k in range(5):
        executed += 1
        y = rng.integers(0, 256, size=384, dtype=np.uint8)
        p1 = ref.ref_frombytes_d12(y)
        p2 = indep_frombytes_d12(y)
        if np.array_equal(p1, p2):
            passed += 1
        else:
            failed += 1

    print(f"[cross] (4) tobytes/frombytes d=12 primary vs indep: {passed}/{executed} matched ({failed} failed)")
    return CheckResult("tobytes_d12", selected, executed, passed, failed)


def check5_msg() -> CheckResult:
    """(5) primary ref_frommsg/tomsg vs independent."""
    rng = np.random.default_rng(0xCC04)
    selected = 10
    executed = 0
    passed = 0
    failed = 0

    for k in range(5):
        executed += 1
        m = rng.integers(0, 256, size=32, dtype=np.uint8)
        p1 = ref.ref_frommsg(m)
        p2 = indep_frommsg(m)
        if np.array_equal(p1, p2):
            passed += 1
        else:
            failed += 1

    # tomsg on random polys drawn to look like Kyber-decrypted values
    for k in range(5):
        executed += 1
        m = rng.integers(0, 256, size=32, dtype=np.uint8)
        p = indep_frommsg(m)
        noise = rng.integers(-100, 101, size=KYBER_N, dtype=np.int16)
        pp = ((p.astype(np.int32) + noise.astype(np.int32)) % KYBER_Q).astype(np.int16)
        p1 = ref.ref_tomsg(pp)
        p2 = indep_tomsg(pp)
        if np.array_equal(p1, p2):
            passed += 1
        else:
            failed += 1

    print(f"[cross] (5) frommsg/tomsg primary vs indep: {passed}/{executed} matched ({failed} failed)")
    return CheckResult("msg", selected, executed, passed, failed)


def check6_full_round_trips() -> CheckResult:
    """(6) End-to-end algebraic identities:
      Compress_d4(Decompress_d4(y))     == y  for uint4 lattice y
      Compress_d10(Decompress_d10(y))   == y  for uint10 lattice y
      frombytes_d12(tobytes_d12(a))     == canonical(a) mod 2^12
      tomsg(frommsg(m))                 == m
    Using the PRIMARY reference for both directions -- exercises the actual
    C-transliterated code path end-to-end."""
    rng = np.random.default_rng(0xCC05)
    selected = 20
    executed = 0
    passed = 0
    failed = 0

    # d=4 round-trip
    for _ in range(5):
        executed += 1
        y = rng.integers(0, 16, size=KYBER_N, dtype=np.uint8)
        packed = np.zeros(128, dtype=np.uint8)
        for i in range(KYBER_N // 2):
            packed[i] = (y[2 * i] | (y[2 * i + 1] << 4)) & 0xFF
        p = ref.ref_decompress_d4(packed)
        back = ref.ref_compress_d4(p)
        if np.array_equal(back, packed):
            passed += 1
        else:
            failed += 1

    # d=10
    for _ in range(5):
        executed += 1
        y = rng.integers(0, 1 << 10, size=KYBER_N, dtype=np.uint16)
        packed = np.zeros(320, dtype=np.uint8)
        r = 0
        for j in range(KYBER_N // 4):
            t0, t1, t2, t3 = int(y[4*j]), int(y[4*j+1]), int(y[4*j+2]), int(y[4*j+3])
            packed[r + 0] = t0 & 0xFF
            packed[r + 1] = ((t0 >> 8) | (t1 << 2)) & 0xFF
            packed[r + 2] = ((t1 >> 6) | (t2 << 4)) & 0xFF
            packed[r + 3] = ((t2 >> 4) | (t3 << 6)) & 0xFF
            packed[r + 4] = (t3 >> 2) & 0xFF
            r += 5
        p = ref.ref_decompress_d10(packed)
        back = ref.ref_compress_d10(p)
        if np.array_equal(back, packed):
            passed += 1
        else:
            failed += 1

    # d=12 lossless
    for _ in range(5):
        executed += 1
        a = _random_signed_poly(rng)
        packed = ref.ref_tobytes_d12(a)
        back = ref.ref_frombytes_d12(packed)
        exp = np.array([ref._canonical(int(x)) & 0xFFF for x in a], dtype=np.int16)
        if np.array_equal(back, exp):
            passed += 1
        else:
            failed += 1

    # message
    for _ in range(5):
        executed += 1
        m = rng.integers(0, 256, size=32, dtype=np.uint8)
        p = ref.ref_frommsg(m)
        back = ref.ref_tomsg(p)
        if np.array_equal(back, m):
            passed += 1
        else:
            failed += 1

    print(f"[cross] (6) primary round-trip identities: {passed}/{executed} matched ({failed} failed)")
    return CheckResult("full_round_trips", selected, executed, passed, failed)


def main() -> int:
    checks = [
        check1_canonical,
        check2_compress_d4,
        check3_compress_d10,
        check4_tobytes_d12,
        check5_msg,
        check6_full_round_trips,
    ]
    results = [check() for check in checks]
    total_selected = sum(r.selected for r in results)
    total_executed = sum(r.executed for r in results)
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    checks_passed = sum(1 for r in results if r.failed == 0 and r.passed == r.selected)

    print(
        f"\nM32d transliteration check: {checks_passed} of {len(checks)} checks successful "
        f"({total_passed} of {total_selected} comparisons matched, {total_failed} failures)"
    )
    if total_failed > 0 or total_passed != total_selected or total_executed != total_selected:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
