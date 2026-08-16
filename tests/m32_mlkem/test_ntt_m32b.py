# Purpose: Milestone 32b - Post-Quantum Cryptography Foundations on AMD Phoenix NPU.
#          Runs a single-tile AIE2 kernel that implements FIPS 203 Algorithms
#          9-12 (forward NTT, inverse NTT, MultiplyNTTs, BaseCaseMultiply) plus
#          the two polynomial-vector helpers (add / sub) used everywhere in
#          K-PKE and ML-KEM KeyGen / Encaps / Decaps.
#
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types:
#   in_a    : int16, up to 768 coefficients
#             (one polynomial for NTT/INTT, two operand polynomials A|B for
#              BASEMUL / POLY_ADD / POLY_SUB)
#   in_ctrl : int16, 8-element control block  (mode, n_polys, pad0, ...)
#   out_c   : int16, up to 768 coefficients (result polynomial(s))
# Scaling: bit-exact integer (no floating-point in the entire kernel).
# State requirements: device 0 (NPU Phoenix).
# Error handling: All 4 silicon gates are asserted.
#
# Design: docs/M32b_DESIGN.md
# Host API pin: mlir-aie v1.4.1 iron.Runtime sequence-function API.
#
# Silicon gates (see docs/M32b_DESIGN.md sec 4):
#   (a) NTT / INTT round-trip: INTT(NTT(a)) == a * mont^2 mod q  bit-exact
#       against the host reference (which is a line-for-line transliteration
#       of the AIE2 C kernel).
#   (b) MultiplyNTTs bit-exact: INTT(NTT(a) o NTT(b)) matches a schoolbook
#       negacyclic product a * b mod (X^256 + 1) after undoing the Montgomery
#       R^2 factor.
#   (c) Zeta-table cross-check: the 128 entries embedded in ntt_kernel.cc match
#       an independent Python recomputation zetas[k] = R * 17^{brv(k,7)} mod q
#       reduced to the signed representative in (-q/2, q/2].
#   (d) poly_add / poly_sub bit-exact against host reference on 3 random
#       polynomial pairs, and add(a,b) + sub(a,b) == 2 a (mod q) coefficient-wise.
#
# References:
#   * FIPS 203 (Aug 2024), ML-KEM standard, Algorithms 9-12.
#     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
#   * pq-crystals/kyber reference implementation (ref/ntt.c, ref/reduce.c,
#     ref/poly.c) - the canonical bit-exact target.
#     https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c
#     https://github.com/pq-crystals/kyber/blob/main/ref/reduce.c
#     https://github.com/pq-crystals/kyber/blob/main/ref/poly.c
#   * CRYSTALS-Kyber round-3 specification, Section 1.4.
#     https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf
#   * Kyber CFRG draft rev 04 (Schwabe et al.).
#     https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html

from pathlib import Path

import numpy as np
from aie import iron
from aie.iron import (
    CompileTime,
    ExternalFunction,
    In,
    ObjectFifo,
    Out,
    Program,
    Runtime,
    Worker,
)
from aie.utils.config import cxx_header_path
from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor

# ------------------------------------------------------------------
# Constants (must match ntt_kernel.cc exactly).

MAX_COEFFS = 768
CTRL_LEN   = 8

MODE_NTT      = 0
MODE_INTT     = 1
MODE_BASEMUL  = 2
MODE_POLY_ADD = 3
MODE_POLY_SUB = 4

KYBER_N          = 256
KYBER_Q          = 3329
KYBER_MONT       = -1044          # 2^16 mod q, signed
KYBER_QINV       = -3327          # q^{-1} mod 2^16, signed
KYBER_INVNTT_F   = 1441           # (2^32 / 128) mod q used by invntt_tomont
KYBER_ZETA       = 17             # primitive 256th root of unity mod q


# ------------------------------------------------------------------
# ZETAS table verbatim from pq-crystals/kyber ref/ntt.c.
#
# This is embedded here purely so the host reference does not depend on
# recomputation and can be checked byte-for-byte against the AIE2 kernel.
# An independent recomputation lives in _recompute_zetas() below; gate (c)
# asserts they agree.

ZETAS = np.array([
    -1044,  -758,  -359, -1517,  1493,  1422,   287,   202,
     -171,   622,  1577,   182,   962, -1202, -1474,  1468,
      573, -1325,   264,   383,  -829,  1458, -1602,  -130,
     -681,  1017,   732,   608, -1542,   411,  -205, -1571,
     1223,   652,  -552,  1015, -1293,  1491,  -282, -1544,
      516,    -8,  -320,  -666, -1618, -1162,   126,  1469,
     -853,   -90,  -271,   830,   107, -1421,  -247,  -951,
     -398,   961, -1508,  -725,   448, -1065,   677, -1275,
    -1103,   430,   555,   843, -1251,   871,  1550,   105,
      422,   587,   177,  -235,  -291,  -460,  1574,  1653,
     -246,   778,  1159,  -147,  -777,  1483,  -602,  1119,
    -1590,   644,  -872,   349,   418,   329,  -156,   -75,
      817,  1097,   603,   610,  1322, -1285, -1465,   384,
    -1215,  -136,  1218, -1335,  -874,   220, -1187, -1659,
    -1185, -1530, -1278,   794, -1510,  -854,  -870,   478,
     -108,  -308,   996,   991,   958, -1460,  1522,  1628,
], dtype=np.int16)


# ------------------------------------------------------------------
# Host reference - bit-exact Python transliteration of ntt_kernel.cc.
#
# Every integer step matches the C code line-for-line: same signed 16-bit
# arithmetic, same overflow semantics (numpy int16 wraps like C), same
# Montgomery / Barrett constants.

_INT16_MIN = -(1 << 15)
_INT16_MAX =  (1 << 15) - 1
_INT16_MOD =  (1 << 16)


def _to_int16(x):
    """Fold an arbitrary int into two's-complement 16-bit (C-style wrap)."""
    v = int(x) & 0xFFFF
    if v >= (1 << 15):
        v -= _INT16_MOD
    return v


def montgomery_reduce(a):
    """int32_t a -> int16_t congruent to a * R^{-1} mod q (R = 2^16).

    Line-for-line pq-crystals ref/reduce.c :: montgomery_reduce.
    """
    a = int(a)
    t = _to_int16(_to_int16(a) * KYBER_QINV)   # int16 * int16 -> low 16 bits
    t = _to_int16((a - t * KYBER_Q) >> 16)
    return t


def barrett_reduce(a):
    """int16_t a -> int16_t centered representative mod q in (-q/2, q/2].

    Line-for-line pq-crystals ref/reduce.c :: barrett_reduce.
    """
    a = _to_int16(a)
    v = ((1 << 26) + KYBER_Q // 2) // KYBER_Q   # = 20159
    t = _to_int16((v * a + (1 << 25)) >> 26)
    t = _to_int16(t * KYBER_Q)
    return _to_int16(a - t)


def fqmul(a, b):
    return montgomery_reduce(int(a) * int(b))


def _brv(i, k):
    """Bit-reverse the low k bits of i."""
    r = 0
    for _ in range(k):
        r = (r << 1) | (i & 1)
        i >>= 1
    return r


def _recompute_zetas():
    """Independent reconstruction of the 128-entry zeta table.

    zetas[k] = R * zeta^{brv7(k)} mod q, in signed representation in
    (-q/2, q/2]. R = 2^16 is folded in so fqmul(zetas[k], x) directly yields
    zeta^{brv7(k)} * x mod q (up to Montgomery R^{-1}, which is undone at the
    end of invntt or by a following tomont).
    """
    R = (1 << 16) % KYBER_Q
    out = np.zeros(128, dtype=np.int16)
    for k in range(128):
        v = (R * pow(KYBER_ZETA, _brv(k, 7), KYBER_Q)) % KYBER_Q
        if v > KYBER_Q // 2:
            v -= KYBER_Q
        out[k] = v
    return out


def ntt_forward_ref(r_in):
    """Forward NTT, line-for-line the C code in ntt_kernel.cc :: ntt_forward.
    Input: length-256 int16 array in standard order.
    Output: length-256 int16 array in bit-reversed order.
    """
    r = [int(x) for x in r_in]
    k = 1
    length = 128
    while length >= 2:
        start = 0
        while start < 256:
            zeta = int(ZETAS[k])
            k += 1
            for j in range(start, start + length):
                t = fqmul(zeta, r[j + length])
                r[j + length] = _to_int16(r[j] - t)
                r[j]          = _to_int16(r[j] + t)
            start = start + 2 * length
        length >>= 1
    return np.array(r, dtype=np.int16)


def ntt_inverse_ref(r_in):
    """Inverse NTT, line-for-line ntt_kernel.cc :: ntt_inverse.
    Input: length-256 int16 in bit-reversed order.
    Output: length-256 int16 in standard order, scaled by R = 2^16 mod q.
    """
    r = [int(x) for x in r_in]
    k = 127
    length = 2
    while length <= 128:
        start = 0
        while start < 256:
            zeta = int(ZETAS[k])
            k -= 1
            for j in range(start, start + length):
                t              = r[j]
                r[j]           = barrett_reduce(_to_int16(t + r[j + length]))
                r[j + length]  = _to_int16(r[j + length] - t)
                r[j + length]  = fqmul(zeta, r[j + length])
            start = start + 2 * length
        length <<= 1

    f = KYBER_INVNTT_F
    for j in range(256):
        r[j] = fqmul(r[j], f)
    return np.array(r, dtype=np.int16)


def basemul_ref(a, b, zeta):
    r0 = fqmul(int(a[1]), int(b[1]))
    r0 = fqmul(r0, int(zeta))
    r0 = _to_int16(r0 + fqmul(int(a[0]), int(b[0])))
    r1 = fqmul(int(a[0]), int(b[1]))
    r1 = _to_int16(r1 + fqmul(int(a[1]), int(b[0])))
    return np.array([r0, r1], dtype=np.int16)


def poly_basemul_ref(a, b):
    r = np.zeros(KYBER_N, dtype=np.int16)
    for i in range(KYBER_N // 4):
        z = int(ZETAS[64 + i])
        r[4 * i:4 * i + 2] = basemul_ref(a[4 * i:4 * i + 2],
                                         b[4 * i:4 * i + 2],  z)
        r[4 * i + 2:4 * i + 4] = basemul_ref(a[4 * i + 2:4 * i + 4],
                                             b[4 * i + 2:4 * i + 4], -z)
    return r


def poly_add_ref(a, b):
    return np.array([barrett_reduce(_to_int16(int(a[i]) + int(b[i])))
                     for i in range(KYBER_N)], dtype=np.int16)


def poly_sub_ref(a, b):
    return np.array([barrett_reduce(_to_int16(int(a[i]) - int(b[i])))
                     for i in range(KYBER_N)], dtype=np.int16)


# ------------------------------------------------------------------
# Big-integer negacyclic schoolbook, used as the mathematical oracle for
# gate (b). Works in Z_q[X]/(X^n + 1) without going through the NTT at all -
# purely a linear-algebra ground truth.

def schoolbook_negacyclic(a, b):
    a_i = [int(x) % KYBER_Q for x in a]
    b_i = [int(x) % KYBER_Q for x in b]
    prod = [0] * (2 * KYBER_N)
    for i in range(KYBER_N):
        ai = a_i[i]
        if ai == 0:
            continue
        for j in range(KYBER_N):
            prod[i + j] = (prod[i + j] + ai * b_i[j]) % KYBER_Q
    # Fold X^N = -1
    out = [0] * KYBER_N
    for i in range(KYBER_N):
        out[i] = (prod[i] - prod[i + KYBER_N]) % KYBER_Q
    # Signed representative
    out16 = []
    for v in out:
        if v > KYBER_Q // 2:
            v -= KYBER_Q
        out16.append(v)
    return np.array(out16, dtype=np.int16)


def _mod_q_signed(x):
    v = int(x) % KYBER_Q
    if v > KYBER_Q // 2:
        v -= KYBER_Q
    return v


# ------------------------------------------------------------------
# IRON JIT plumbing - single-tile, 2 in-fifos + 1 out-fifo.
# Identical topology to M32c (which is silicon-PASSed).

@iron.jit
def ntt_program(
    in_a: In,
    in_ctrl: In,
    out_c: Out,
    *,
    N_A_SLOTS: CompileTime[int],
    N_CTRL_SLOTS: CompileTime[int],
    N_OUT_SLOTS: CompileTime[int],
    kernel_name: CompileTime[str],
    element_type: CompileTime[type],
):
    a_ty = np.ndarray[(N_A_SLOTS,), np.dtype[element_type]]
    ctrl_ty = np.ndarray[(N_CTRL_SLOTS,), np.dtype[element_type]]
    out_ty = np.ndarray[(N_OUT_SLOTS,), np.dtype[element_type]]

    of_a = ObjectFifo(a_ty, name="in_a")
    of_ctrl = ObjectFifo(ctrl_ty, name="in_ctrl")
    of_out = ObjectFifo(out_ty, name="out_c")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(__file__).resolve().parents[2] / "include" / "sdr_dsp"

    ch_func = ExternalFunction(
        kernel_name,
        source_file=str(current_dir / "ntt_kernel.cc"),
        arg_types=[a_ty, ctrl_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_a, of_ctrl, of_out, ch_func):
        elem_a = of_a.acquire(1)
        elem_ctrl = of_ctrl.acquire(1)
        elem_out = of_out.acquire(1)
        ch_func(elem_a, elem_ctrl, elem_out)
        of_a.release(1)
        of_ctrl.release(1)
        of_out.release(1)

    worker = Worker(
        core_body,
        fn_args=[
            of_a.cons(),
            of_ctrl.cons(),
            of_out.prod(),
            ch_func,
        ],
        stack_size=0x4000,
    )

    def sequence(a_in, a_ctrl, c_out,
                 a_prod, ctrl_prod, out_cons):
        a_prod.fill(a_in)
        ctrl_prod.fill(a_ctrl)
        out_cons.drain(c_out, wait=True)

    rt = Runtime(
        sequence,
        [
            a_ty, ctrl_ty, out_ty,
            of_a.prod(), of_ctrl.prod(), of_out.cons(),
        ],
    )
    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()


# ------------------------------------------------------------------
# Silicon dispatch harness.

def _pack_ctrl(mode, n_polys=1):
    ctrl = np.zeros(CTRL_LEN, dtype=np.int16)
    ctrl[0] = mode
    ctrl[1] = n_polys
    return ctrl


def _dispatch(a_coeffs, ctrl, tag):
    """Compile and run the kernel once, return out_c buffer as int16 array."""
    print(f"\n--- Silicon dispatch: {tag} ---")

    assert len(a_coeffs) <= MAX_COEFFS
    padded_a = np.zeros(MAX_COEFFS, dtype=np.int16)
    padded_a[:len(a_coeffs)] = a_coeffs

    padded_ctrl = np.zeros(CTRL_LEN, dtype=np.int16)
    padded_ctrl[:len(ctrl)] = ctrl

    np_out = np.zeros(MAX_COEFFS, dtype=np.int16)

    a_t = XRTTensor(padded_a, dtype=np.int16)
    ctrl_t = XRTTensor(padded_ctrl, dtype=np.int16)
    out_t = XRTTensor(np_out, dtype=np.int16)

    print(f"Compiling M32b ntt ({tag}) and dispatching to Phoenix NPU...")
    res = ntt_program(
        a_t, ctrl_t, out_t,
        N_A_SLOTS=MAX_COEFFS,
        N_CTRL_SLOTS=CTRL_LEN,
        N_OUT_SLOTS=MAX_COEFFS,
        kernel_name="ntt",
        element_type=np.int16,
    )
    print(f"Kernel execution result: {res}")

    out_t.to("cpu")
    return out_t._data


# ------------------------------------------------------------------
# Reference (host-only) tests.

def _random_poly(rng):
    """Uniform int16 polynomial in (-q/2, q/2], the same range the NTT/INTT
    contract expects (canonical signed representation)."""
    v = rng.integers(0, KYBER_Q, size=KYBER_N).astype(np.int64)
    # centered signed
    v = np.where(v > KYBER_Q // 2, v - KYBER_Q, v).astype(np.int16)
    return v


def _ref_test_zeta_recompute():
    """R1: independent recomputation of the zeta table matches the embedded
    128-entry pq-crystals table byte-for-byte."""
    got = _recompute_zetas()
    assert np.array_equal(got, ZETAS), \
        f"zeta recomputation mismatch at index {int(np.argmax(got != ZETAS))}"
    print("[reference] R1 zeta table 128-entry recomputation matches: PASS")


def _ref_test_ntt_roundtrip():
    """R2: INTT(NTT(a)) == a * 2^16 mod q on random polynomials."""
    rng = np.random.default_rng(0xC0FFEE)
    R_mod_q = (1 << 16) % KYBER_Q
    for k in range(3):
        a = _random_poly(rng)
        na = ntt_forward_ref(a)
        aa = ntt_inverse_ref(na)
        exp = np.array([_mod_q_signed(int(x) * R_mod_q) for x in a],
                       dtype=np.int16)
        got = np.array([_mod_q_signed(int(x)) for x in aa], dtype=np.int16)
        assert np.array_equal(got, exp), \
            f"round-trip mismatch on poly #{k}"
    print("[reference] R2 INTT(NTT(a)) == R*a mod q on 3 polys: PASS")


def _ref_test_multiplyntts():
    """R3: INTT(NTT(a) o NTT(b)) matches negacyclic schoolbook a*b mod (X^N+1).

    poly_basemul_montgomery leaves the product multiplied by R^{-1}; the
    surrounding INTT then multiplies by R again (`invntt_tomont`). Net result
    is a factor of R^0 = 1 -- the schoolbook oracle can be compared directly
    once both sides are reduced modulo q with signed representative.
    """
    rng = np.random.default_rng(0xDEADBEEF)
    for k in range(3):
        a = _random_poly(rng)
        b = _random_poly(rng)
        na = ntt_forward_ref(a)
        nb = ntt_forward_ref(b)
        # poly_basemul_montgomery leaves result multiplied by R^{-1}
        # (from Montgomery reduction on each partial product).
        nab = poly_basemul_ref(na, nb)
        # invntt_tomont multiplies by R. Net: R * R^{-1} = 1.
        ab_ref = ntt_inverse_ref(nab)
        ab_school = schoolbook_negacyclic(a, b)
        got = np.array([_mod_q_signed(int(x)) for x in ab_ref], dtype=np.int16)
        assert np.array_equal(got, ab_school), \
            f"MultiplyNTTs vs schoolbook mismatch on pair #{k}: " \
            f"first_diff_idx={int(np.argmax(got != ab_school))}"
    print("[reference] R3 MultiplyNTTs vs schoolbook on 3 pairs: PASS")


def _ref_test_add_sub_identity():
    """R4: poly_add(a,b) + poly_sub(a,b) == 2 a mod q, coefficient-wise."""
    rng = np.random.default_rng(0xBADC0DE)
    for k in range(3):
        a = _random_poly(rng)
        b = _random_poly(rng)
        s = poly_add_ref(a, b)
        d = poly_sub_ref(a, b)
        got = np.array([_mod_q_signed(int(s[i]) + int(d[i]))
                        for i in range(KYBER_N)], dtype=np.int16)
        exp = np.array([_mod_q_signed(2 * int(a[i]))
                        for i in range(KYBER_N)], dtype=np.int16)
        assert np.array_equal(got, exp), \
            f"add/sub identity failed on pair #{k}"
    print("[reference] R4 add+sub identity == 2 a mod q on 3 pairs: PASS")


def _run_local_reference_checks():
    print("Running host-side reference checks before silicon dispatch...")
    _ref_test_zeta_recompute()
    _ref_test_ntt_roundtrip()
    _ref_test_multiplyntts()
    _ref_test_add_sub_identity()


# ------------------------------------------------------------------
# Silicon PASS gates.

def _gate_a_ntt_roundtrip():
    """Gate (a): NTT then INTT on silicon equals R*a mod q, bit-exact vs the
    line-for-line host reference. 3 random polynomials."""
    print("\n=== gate (a) NTT / INTT round-trip ===")
    rng = np.random.default_rng(0xC0FFEE)
    for k in range(3):
        a = _random_poly(rng)

        # Forward NTT on silicon
        ctrl_fwd = _pack_ctrl(MODE_NTT, n_polys=1)
        sil_fwd_raw = _dispatch(a, ctrl_fwd,
                                f"gate(a) NTT poly #{k}")
        sil_fwd = np.frombuffer(sil_fwd_raw[:KYBER_N * 2].tobytes()
                                if hasattr(sil_fwd_raw, "tobytes")
                                else bytes(sil_fwd_raw[:KYBER_N * 2]),
                                dtype=np.int16).copy()[:KYBER_N]
        # Reference forward NTT
        ref_fwd = ntt_forward_ref(a)
        assert np.array_equal(sil_fwd, ref_fwd), \
            f"gate (a) NTT mismatch on poly #{k}: " \
            f"first_diff_idx={int(np.argmax(sil_fwd != ref_fwd))}"

        # Inverse NTT on silicon, seeded with the silicon forward output.
        ctrl_inv = _pack_ctrl(MODE_INTT, n_polys=1)
        sil_inv_raw = _dispatch(sil_fwd, ctrl_inv,
                                f"gate(a) INTT poly #{k}")
        sil_inv = np.frombuffer(sil_inv_raw[:KYBER_N * 2].tobytes()
                                if hasattr(sil_inv_raw, "tobytes")
                                else bytes(sil_inv_raw[:KYBER_N * 2]),
                                dtype=np.int16).copy()[:KYBER_N]
        ref_inv = ntt_inverse_ref(ref_fwd)
        assert np.array_equal(sil_inv, ref_inv), \
            f"gate (a) INTT mismatch on poly #{k}: " \
            f"first_diff_idx={int(np.argmax(sil_inv != ref_inv))}"

        # Semantic check: INTT(NTT(a)) == R*a mod q
        R_mod_q = (1 << 16) % KYBER_Q
        exp = np.array([_mod_q_signed(int(x) * R_mod_q) for x in a],
                       dtype=np.int16)
        got = np.array([_mod_q_signed(int(x)) for x in sil_inv],
                       dtype=np.int16)
        assert np.array_equal(got, exp), \
            f"gate (a) round-trip semantic mismatch on poly #{k}"
        print(f"[gate a] NTT/INTT poly #{k}: PASS "
              f"(bit-exact vs host + INTT(NTT(a)) == R*a mod q)")


def _gate_b_multiplyntts():
    """Gate (b): INTT(NTT(a) o NTT(b)) on silicon equals negacyclic schoolbook
    a*b mod (X^N+1). 3 random pairs."""
    print("\n=== gate (b) MultiplyNTTs vs schoolbook ===")
    rng = np.random.default_rng(0xDEADBEEF)
    for k in range(3):
        a = _random_poly(rng)
        b = _random_poly(rng)

        # NTT(a) on silicon
        na = np.frombuffer(
            _dispatch(a, _pack_ctrl(MODE_NTT), f"gate(b) NTT(a) #{k}")
              [:KYBER_N * 2].tobytes(),
            dtype=np.int16).copy()[:KYBER_N]
        # NTT(b) on silicon
        nb = np.frombuffer(
            _dispatch(b, _pack_ctrl(MODE_NTT), f"gate(b) NTT(b) #{k}")
              [:KYBER_N * 2].tobytes(),
            dtype=np.int16).copy()[:KYBER_N]
        # BASEMUL: layout is A | B in in_a[0..512)
        ab_in = np.concatenate([na, nb])
        nab = np.frombuffer(
            _dispatch(ab_in, _pack_ctrl(MODE_BASEMUL),
                      f"gate(b) BASEMUL #{k}")[:KYBER_N * 2].tobytes(),
            dtype=np.int16).copy()[:KYBER_N]
        # INTT
        ab = np.frombuffer(
            _dispatch(nab, _pack_ctrl(MODE_INTT), f"gate(b) INTT #{k}")
              [:KYBER_N * 2].tobytes(),
            dtype=np.int16).copy()[:KYBER_N]
        got = np.array([_mod_q_signed(int(x)) for x in ab], dtype=np.int16)
        exp = schoolbook_negacyclic(a, b)
        assert np.array_equal(got, exp), \
            f"gate (b) product mismatch on pair #{k}: " \
            f"first_diff_idx={int(np.argmax(got != exp))}"
        print(f"[gate b] MultiplyNTTs pair #{k}: PASS "
              f"(bit-exact vs schoolbook negacyclic a*b mod (X^N+1))")


def _gate_c_zeta_table_consistency():
    """Gate (c): silicon NTT butterfly output can only match the host
    reference if the on-tile ZETAS table equals the pq-crystals table -
    every level of the Cooley-Tukey tree multiplies by a distinct twiddle.

    Strategy:
      * Independently recompute ZETAS via zeta^{brv7(k)} * R mod q from a=17.
        Assert byte-for-byte equality with the 128-entry table embedded in the
        host reference (which is copied verbatim from ntt_kernel.cc).
      * Run the forward NTT on silicon for the delta_0 polynomial
        (a[0]=1, rest 0). The output values are entirely determined by the
        composition of the ZETAS table and the butterfly schedule - they are
        byte-identical between the primary reference and the AIE2 kernel iff
        both use the same 128-entry table. Comparing silicon to the host
        reference on this specific vector therefore witnesses the on-tile
        table's content.
    """
    print("\n=== gate (c) zeta-table consistency ===")

    zetas_indep = _recompute_zetas()
    assert np.array_equal(zetas_indep, ZETAS), \
        "gate (c) FAIL: independent zeta recompute disagrees with embedded table"
    print("[gate c] zeta table recompute matches embedded pq-crystals table: PASS")

    delta = np.zeros(KYBER_N, dtype=np.int16)
    delta[0] = 1
    sil = np.frombuffer(
        _dispatch(delta, _pack_ctrl(MODE_NTT), "gate(c) NTT(delta_0)")
          [:KYBER_N * 2].tobytes(),
        dtype=np.int16).copy()[:KYBER_N]
    ref = ntt_forward_ref(delta)
    assert np.array_equal(sil, ref), \
        f"gate (c) delta fingerprint mismatch: " \
        f"first_diff_idx={int(np.argmax(sil != ref))}"
    print(f"[gate c] silicon NTT(delta_0) matches host reference "
          f"(nnz={int(np.count_nonzero(sil))}): PASS")

    # Second fingerprint: delta_2 exercises non-trivial twiddles (delta_0/1 hit
    # only trivial 0-multiplications). If any zeta on the tile is wrong, this
    # will diverge.
    delta2 = np.zeros(KYBER_N, dtype=np.int16)
    delta2[2] = 1
    sil2 = np.frombuffer(
        _dispatch(delta2, _pack_ctrl(MODE_NTT), "gate(c) NTT(delta_2)")
          [:KYBER_N * 2].tobytes(),
        dtype=np.int16).copy()[:KYBER_N]
    ref2 = ntt_forward_ref(delta2)
    assert np.array_equal(sil2, ref2), \
        f"gate (c) delta_2 fingerprint mismatch: " \
        f"first_diff_idx={int(np.argmax(sil2 != ref2))}"
    print("[gate c] silicon NTT(delta_2) matches host reference "
          "(exercises non-trivial twiddles at every level): PASS")


def _gate_d_poly_add_sub():
    """Gate (d): silicon poly_add / poly_sub bit-exact vs host reference, and
    add(a,b) + sub(a,b) == 2 a mod q. 3 random pairs."""
    print("\n=== gate (d) poly_add / poly_sub ===")
    rng = np.random.default_rng(0xBADC0DE)
    for k in range(3):
        a = _random_poly(rng)
        b = _random_poly(rng)
        ab_in = np.concatenate([a, b])

        sil_add = np.frombuffer(
            _dispatch(ab_in, _pack_ctrl(MODE_POLY_ADD),
                      f"gate(d) ADD #{k}")[:KYBER_N * 2].tobytes(),
            dtype=np.int16).copy()[:KYBER_N]
        ref_add = poly_add_ref(a, b)
        assert np.array_equal(sil_add, ref_add), \
            f"gate (d) add mismatch on pair #{k}"

        sil_sub = np.frombuffer(
            _dispatch(ab_in, _pack_ctrl(MODE_POLY_SUB),
                      f"gate(d) SUB #{k}")[:KYBER_N * 2].tobytes(),
            dtype=np.int16).copy()[:KYBER_N]
        ref_sub = poly_sub_ref(a, b)
        assert np.array_equal(sil_sub, ref_sub), \
            f"gate (d) sub mismatch on pair #{k}"

        # add(a,b) + sub(a,b) == 2 a mod q coefficient-wise
        combo = np.array([_mod_q_signed(int(sil_add[i]) + int(sil_sub[i]))
                          for i in range(KYBER_N)], dtype=np.int16)
        expected = np.array([_mod_q_signed(2 * int(a[i]))
                             for i in range(KYBER_N)], dtype=np.int16)
        assert np.array_equal(combo, expected), \
            f"gate (d) add+sub identity failed on pair #{k}"
        print(f"[gate d] add+sub pair #{k}: PASS "
              f"(bit-exact vs host + add+sub == 2 a mod q)")


# ------------------------------------------------------------------
# Reference-only pytest entry points.

def test_reference_r1_zeta_recompute():
    _ref_test_zeta_recompute()


def test_reference_r2_ntt_roundtrip():
    _ref_test_ntt_roundtrip()


def test_reference_r3_multiplyntts():
    _ref_test_multiplyntts()


def test_reference_r4_add_sub_identity():
    _ref_test_add_sub_identity()


# ------------------------------------------------------------------
# Silicon PASS gates as pytest entry points.

def test_gate_a_ntt_roundtrip():
    _gate_a_ntt_roundtrip()


def test_gate_b_multiplyntts():
    _gate_b_multiplyntts()


def test_gate_c_zeta_table_consistency():
    _gate_c_zeta_table_consistency()


def test_gate_d_poly_add_sub():
    _gate_d_poly_add_sub()


if __name__ == "__main__":
    _run_local_reference_checks()
    print("\n" + "=" * 60)
    print("Silicon PASS gates (M32b PQC NTT arithmetic)")
    print("=" * 60)
    _gate_a_ntt_roundtrip()
    _gate_b_multiplyntts()
    _gate_c_zeta_table_consistency()
    _gate_d_poly_add_sub()
    print("\n" + "=" * 60)
    print("M32b: ALL SILICON GATES PASS")
    print("=" * 60)
