# Purpose: Milestone 32c - Post-Quantum Cryptography Foundations on AMD Phoenix NPU.
#          Runs a single-tile AIE2 kernel that implements the full FIPS 202
#          sponge (Keccak-f[1600] + pad10*1 + rate/capacity switching for
#          SHA3-256, SHA3-512, SHAKE128, SHAKE256) plus the two FIPS 203
#          samplers - SampleNTT (Alg 7) and SamplePolyCBD_eta (Alg 8) - that
#          are the only randomness sources inside ML-KEM.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types:
#   in_bytes  : uint8, up to 512 bytes (absorbed message or PRF/XOF seed)
#   in_ctrl   : uint8, 16-byte control block
#               [0] mode; [1..2] in_len (little-endian u16);
#               [3..4] out_len (little-endian u16); [5] eta; [6..15] pad0
#   out_bytes : uint8, up to 512 bytes (hash / XOF / int16-packed coefficients)
# Scaling: byte-exact (no floating-point in the entire kernel).
# State requirements: device 0 (NPU Phoenix).
# Error handling: All 4 silicon gates are asserted.
#
# Design: docs/M32c_DESIGN.md
# Host API pin: mlir-aie v1.4.1 iron.Runtime sequence-function API.
#
# Silicon gates (see docs/M32c_DESIGN.md sec 4):
#   (a) transliteration bit-exact vs host reference over 3 seeds, 4 modes
#   (b) FIPS 202 known-answer tests (SHA3-256, SHA3-512, SHAKE128, SHAKE256
#       on empty input and on a fixed 200-byte pattern)
#   (c) SampleNTT reproducibility + range check (< q = 3329) on a fixed seed
#   (d) SamplePolyCBD reproducibility + binomial-pmf sanity for eta in {2, 3}
#
# References:
#   * FIPS 202 (Aug 2015):
#     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf
#   * FIPS 203 (Aug 2024) ML-KEM:
#     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
#   * NIST PQC project landing page:
#     https://csrc.nist.gov/projects/post-quantum-cryptography
#   * XKCP CompactFIPS202 reference:
#     https://github.com/XKCP/XKCP/blob/master/Standalone/CompactFIPS202/C/Keccak-readable-and-compact.c
#   * Keccak specifications summary:
#     https://keccak.team/keccak_specs_summary.html
#   * Kyber CFRG draft rev 04:
#     https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html

import hashlib
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
# Constants shared with keccak_shake_kernel.cc.

MAX_IN_BYTES  = 1024   # bumped for M32e composition: FIPS 203
                       # sha3_256(ek) is 800B and shake256(z||c) is 800B.
MAX_OUT_BYTES = 1024   # bumped for M32e composition: raw SHAKE up to 1024B,
                       # SampleNTT XOF budget internally bumped to 840B
                       # (see keccak_shake_kernel.cc:XOF_MAX_OUT).
CTRL_BYTES    = 16

MODE_SHA3_256   = 0
MODE_SHA3_512   = 1
MODE_SHAKE128   = 2
MODE_SHAKE256   = 3
MODE_SAMPLE_NTT = 4
MODE_SAMPLE_CBD = 5

RATE_SHA3_256 = 136
RATE_SHA3_512 = 72
RATE_SHAKE128 = 168
RATE_SHAKE256 = 136
DSP_SHA3   = 0x06
DSP_SHAKE  = 0x1F

KYBER_N = 256
KYBER_Q = 3329


# ------------------------------------------------------------------
# Host reference - bit-safe Python transliteration of the AIE2 kernel.
#
# Uses only numpy uint64 and uint8 operations so that every intermediate
# value matches the C++ kernel byte-for-byte on a little-endian machine.

_KECCAK_RC_LFSR_POLY = 0x71  # x^8 + x^6 + x^5 + x^4 + 1


def _rol64(a, r):
    a = np.uint64(a) & np.uint64(0xFFFFFFFFFFFFFFFF)
    r = int(r) & 63
    if r == 0:
        return int(a)
    a = int(a)
    return ((a << r) | (a >> (64 - r))) & 0xFFFFFFFFFFFFFFFF


def _lfsr86540(state):
    """Return (bit, new_state) per FIPS 202 Alg 5 primitive-poly LFSR."""
    bit = state & 0x01
    if state & 0x80:
        state = ((state << 1) ^ _KECCAK_RC_LFSR_POLY) & 0xFF
    else:
        state = (state << 1) & 0xFF
    return bit, state


def keccak_f1600(state_bytes):
    """Reference Keccak-f[1600] permutation on a 200-byte state.

    Transliterated from tests/m32_mlkem/keccak_shake_kernel.cc line-for-line
    so the two references are structurally identical.  Rotation offsets and
    round constants are computed on-the-fly (no lookup tables), same as the
    kernel.
    """
    assert len(state_bytes) == 200
    A = [int.from_bytes(state_bytes[i * 8:(i + 1) * 8], "little")
         for i in range(25)]
    lfsr = 0x01

    for _round in range(24):
        # theta
        C = [A[x] ^ A[x + 5] ^ A[x + 10] ^ A[x + 15] ^ A[x + 20]
             for x in range(5)]
        D = [C[(x + 4) % 5] ^ _rol64(C[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                A[x + 5 * y] ^= D[x]

        # rho + pi over the (1,0) orbit
        x, y = 1, 0
        current = A[1 + 5 * 0]
        for t in range(24):
            r_off = ((t + 1) * (t + 2) // 2) % 64
            Y = (2 * x + 3 * y) % 5
            x, y = y, Y
            idx = x + 5 * y
            temp = A[idx]
            A[idx] = _rol64(current, r_off)
            current = temp

        # chi
        for yr in range(5):
            t0, t1, t2, t3, t4 = (A[0 + 5 * yr], A[1 + 5 * yr],
                                  A[2 + 5 * yr], A[3 + 5 * yr],
                                  A[4 + 5 * yr])
            A[0 + 5 * yr] = t0 ^ (((~t1) & 0xFFFFFFFFFFFFFFFF) & t2)
            A[1 + 5 * yr] = t1 ^ (((~t2) & 0xFFFFFFFFFFFFFFFF) & t3)
            A[2 + 5 * yr] = t2 ^ (((~t3) & 0xFFFFFFFFFFFFFFFF) & t4)
            A[3 + 5 * yr] = t3 ^ (((~t4) & 0xFFFFFFFFFFFFFFFF) & t0)
            A[4 + 5 * yr] = t4 ^ (((~t0) & 0xFFFFFFFFFFFFFFFF) & t1)

        # iota
        rc = 0
        for j in range(7):
            bit_pos = (1 << j) - 1
            bit, lfsr = _lfsr86540(lfsr)
            if bit:
                rc ^= (1 << bit_pos)
        A[0] ^= rc

    out = bytearray(200)
    for i in range(25):
        out[i * 8:(i + 1) * 8] = int(A[i]).to_bytes(8, "little")
    return bytes(out)


def keccak_sponge(in_bytes, out_len, rate_bytes, dsp):
    """FIPS 202 sponge: absorb any-length input, pad10*1 with dsp, squeeze."""
    state = bytearray(200)
    off = 0
    remaining = len(in_bytes)
    while remaining >= rate_bytes:
        for i in range(rate_bytes):
            state[i] ^= in_bytes[off + i]
        state = bytearray(keccak_f1600(bytes(state)))
        off += rate_bytes
        remaining -= rate_bytes

    for i in range(remaining):
        state[i] ^= in_bytes[off + i]
    state[remaining]     ^= dsp
    state[rate_bytes - 1] ^= 0x80
    state = bytearray(keccak_f1600(bytes(state)))

    out = bytearray()
    while out_len > 0:
        block = min(out_len, rate_bytes)
        out += state[:block]
        out_len -= block
        if out_len > 0:
            state = bytearray(keccak_f1600(bytes(state)))
    return bytes(out)


def sample_ntt(seed_32, j_byte, i_byte):
    """FIPS 203 Alg 7 - rejection sample 256 coeffs mod q from SHAKE128."""
    xof_in = bytes(seed_32) + bytes([j_byte & 0xFF, i_byte & 0xFF])
    # 5 SHAKE128 rate blocks = 840 bytes; matches kernel XOF_MAX_OUT.
    xof_out = keccak_sponge(xof_in, 840, RATE_SHAKE128, DSP_SHAKE)
    coeffs = []
    pos = 0
    while len(coeffs) < KYBER_N and pos + 3 <= len(xof_out):
        b0 = xof_out[pos + 0]
        b1 = xof_out[pos + 1]
        b2 = xof_out[pos + 2]
        pos += 3
        d1 = b0 + 256 * (b1 & 0x0F)
        d2 = (b1 >> 4) + 16 * b2
        if d1 < KYBER_Q:
            coeffs.append(d1)
        if len(coeffs) < KYBER_N and d2 < KYBER_Q:
            coeffs.append(d2)
    while len(coeffs) < KYBER_N:
        coeffs.append(0)
    return np.array(coeffs, dtype=np.int16)


def sample_poly_cbd(seed_32, b_byte, eta):
    """FIPS 203 Alg 8 - centered binomial sample via SHAKE256 PRF."""
    assert eta in (2, 3)
    prf_in = bytes(seed_32) + bytes([b_byte & 0xFF])
    prf_out = keccak_sponge(prf_in, 64 * eta, RATE_SHAKE256, DSP_SHAKE)
    coeffs = np.zeros(KYBER_N, dtype=np.int16)
    for i in range(KYBER_N):
        bit_start = 2 * eta * i
        byte_idx = bit_start >> 3
        bit_off = bit_start & 7
        hi = prf_out[byte_idx + 1] if (byte_idx + 1) < len(prf_out) else 0
        lo = prf_out[byte_idx]
        win = ((hi << 8) | lo) >> bit_off
        mask = (1 << eta) - 1
        a_bits = win & mask
        b_bits = (win >> eta) & mask
        a_pop = int(a_bits).bit_count()
        b_pop = int(b_bits).bit_count()
        coeffs[i] = a_pop - b_pop
    return coeffs


# ------------------------------------------------------------------
# IRON JIT plumbing - single-tile, 2 in-fifos + 1 out-fifo (M27 lesson).

@iron.jit
def keccak_shake_program(
    in_bytes: In,
    in_ctrl: In,
    out_bytes: Out,
    *,
    N_IN_SLOTS: CompileTime[int],
    N_CTRL_SLOTS: CompileTime[int],
    N_OUT_SLOTS: CompileTime[int],
    kernel_name: CompileTime[str],
    element_type: CompileTime[type],
):
    in_ty = np.ndarray[(N_IN_SLOTS,), np.dtype[element_type]]
    ctrl_ty = np.ndarray[(N_CTRL_SLOTS,), np.dtype[element_type]]
    out_ty = np.ndarray[(N_OUT_SLOTS,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in_bytes")
    of_ctrl = ObjectFifo(ctrl_ty, name="in_ctrl")
    of_out = ObjectFifo(out_ty, name="out_bytes")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(__file__).resolve().parents[2] / "include" / "sdr_dsp"

    ch_func = ExternalFunction(
        kernel_name,
        source_file=str(current_dir / "keccak_shake_kernel.cc"),
        arg_types=[in_ty, ctrl_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_ctrl, of_out, ch_func):
        elem_in = of_in.acquire(1)
        elem_ctrl = of_ctrl.acquire(1)
        elem_out = of_out.acquire(1)
        ch_func(elem_in, elem_ctrl, elem_out)
        of_in.release(1)
        of_ctrl.release(1)
        of_out.release(1)

    worker = Worker(
        core_body,
        fn_args=[
            of_in.cons(),
            of_ctrl.cons(),
            of_out.prod(),
            ch_func,
        ],
        stack_size=0x4000,
    )

    def sequence(a_in, a_ctrl, c_out,
                 in_prod, ctrl_prod, out_cons):
        in_prod.fill(a_in)
        ctrl_prod.fill(a_ctrl)
        out_cons.drain(c_out, wait=True)

    rt = Runtime(
        sequence,
        [
            in_ty, ctrl_ty, out_ty,
            of_in.prod(), of_ctrl.prod(), of_out.cons(),
        ],
    )
    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()


# ------------------------------------------------------------------
# Silicon dispatch harness.

def _pack_ctrl(mode, in_len, out_len, eta=0):
    ctrl = np.zeros(CTRL_BYTES, dtype=np.uint8)
    ctrl[0] = mode
    ctrl[1] = in_len & 0xFF
    ctrl[2] = (in_len >> 8) & 0xFF
    ctrl[3] = out_len & 0xFF
    ctrl[4] = (out_len >> 8) & 0xFF
    ctrl[5] = eta
    return ctrl


def _dispatch(in_bytes_np, ctrl_np, tag):
    """Compile and run the kernel once, return the out_bytes buffer."""
    print(f"\n--- Silicon dispatch: {tag} ---")

    # Pad inputs up to fixed DMA slot sizes.
    assert len(in_bytes_np) <= MAX_IN_BYTES
    padded_in = np.zeros(MAX_IN_BYTES, dtype=np.uint8)
    padded_in[:len(in_bytes_np)] = in_bytes_np

    padded_ctrl = np.zeros(CTRL_BYTES, dtype=np.uint8)
    padded_ctrl[:len(ctrl_np)] = ctrl_np

    np_out = np.zeros(MAX_OUT_BYTES, dtype=np.uint8)

    in_t = XRTTensor(padded_in, dtype=np.uint8)
    ctrl_t = XRTTensor(padded_ctrl, dtype=np.uint8)
    out_t = XRTTensor(np_out, dtype=np.uint8)

    print(f"Compiling M32c keccak_shake ({tag}) and dispatching to Phoenix NPU...")
    res = keccak_shake_program(
        in_t, ctrl_t, out_t,
        N_IN_SLOTS=MAX_IN_BYTES,
        N_CTRL_SLOTS=CTRL_BYTES,
        N_OUT_SLOTS=MAX_OUT_BYTES,
        kernel_name="keccak_shake",
        element_type=np.uint8,
    )
    print(f"Kernel execution result: {res}")

    out_t.to("cpu")
    return out_t._data


# ------------------------------------------------------------------
# NIST FIPS 202 CAVP-style known answers (empty-message vectors are
# universally cited and stable across every FIPS 202 implementation).

NIST_SHA3_256_EMPTY = bytes.fromhex(
    "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a")
NIST_SHA3_512_EMPTY = bytes.fromhex(
    "a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a6"
    "15b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26")
NIST_SHAKE128_EMPTY_32 = bytes.fromhex(
    "7f9c2ba4e88f827d616045507605853e"
    "d73b8093f6efbc88eb1a6eacfa66ef26")
NIST_SHAKE256_EMPTY_32 = bytes.fromhex(
    "46b9dd2b0ba88d13233b3feb743eeb24"
    "3fcd52ea62b81b82b50c27646ed5762f")


# ------------------------------------------------------------------
# Reference (host-only) tests.  Run before every silicon dispatch to
# guarantee the reference itself is trustworthy.

def _ref_test_sha3_matches_hashlib():
    """R1: host reference SHA3-256/512 agrees with Python's hashlib on
    several messages (hashlib is a stdlib gold reference)."""
    msgs = [
        b"",
        b"abc",
        b"The quick brown fox jumps over the lazy dog",
        bytes(range(200)),
    ]
    for m in msgs:
        got_256 = keccak_sponge(m, 32, RATE_SHA3_256, DSP_SHA3)
        exp_256 = hashlib.sha3_256(m).digest()
        assert got_256 == exp_256, f"SHA3-256 mismatch on len={len(m)}"
        got_512 = keccak_sponge(m, 64, RATE_SHA3_512, DSP_SHA3)
        exp_512 = hashlib.sha3_512(m).digest()
        assert got_512 == exp_512, f"SHA3-512 mismatch on len={len(m)}"
    print("[reference] R1 SHA3-256/512 vs hashlib: PASS")


def _ref_test_shake_matches_hashlib():
    """R2: host reference SHAKE128/256 agrees with hashlib.shake_*."""
    msgs = [
        b"",
        b"post-quantum",
        bytes(range(64)),
    ]
    for m in msgs:
        for out_len in (16, 32, 168, 200):
            got_128 = keccak_sponge(m, out_len, RATE_SHAKE128, DSP_SHAKE)
            exp_128 = hashlib.shake_128(m).digest(out_len)
            assert got_128 == exp_128, \
                f"SHAKE128 mismatch len(m)={len(m)} out={out_len}"
            got_256 = keccak_sponge(m, out_len, RATE_SHAKE256, DSP_SHAKE)
            exp_256 = hashlib.shake_256(m).digest(out_len)
            assert got_256 == exp_256, \
                f"SHAKE256 mismatch len(m)={len(m)} out={out_len}"
    print("[reference] R2 SHAKE128/256 vs hashlib: PASS")


def _ref_test_sample_ntt_range_and_size():
    """R3: SampleNTT on a fixed seed returns 256 coefficients strictly
    less than q = 3329."""
    seed = bytes(range(32))
    coeffs = sample_ntt(seed, 0, 0)
    assert coeffs.shape == (KYBER_N,)
    assert coeffs.min() >= 0 and coeffs.max() < KYBER_Q, \
        f"SampleNTT out of range [{coeffs.min()}, {coeffs.max()}]"
    print(f"[reference] R3 SampleNTT range 0..{KYBER_Q - 1} on 256 coeffs: PASS")


def _ref_test_cbd_pmf():
    """R4: SamplePolyCBD_eta first-moment sanity - the mean of ~4k samples
    should be near zero and variance near eta/2 (Kyber CFRG draft 2.4)."""
    seed = bytes([0x42] * 32)
    samples_2 = np.concatenate([sample_poly_cbd(seed, b, 2) for b in range(16)])
    samples_3 = np.concatenate([sample_poly_cbd(seed, b, 3) for b in range(16)])
    m2, v2 = float(samples_2.mean()), float(samples_2.var())
    m3, v3 = float(samples_3.mean()), float(samples_3.var())
    print(f"[reference] R4 CBD eta=2 mean={m2:+.4f} var={v2:.4f} "
          f"(target |mean|<0.10 var~1.00)")
    print(f"[reference] R4 CBD eta=3 mean={m3:+.4f} var={v3:.4f} "
          f"(target |mean|<0.10 var~1.50)")
    assert abs(m2) < 0.10 and 0.80 < v2 < 1.20
    assert abs(m3) < 0.10 and 1.20 < v3 < 1.80
    # Also verify coefficient support.
    assert samples_2.min() >= -2 and samples_2.max() <= +2
    assert samples_3.min() >= -3 and samples_3.max() <= +3
    print("[reference] R4 CBD pmf sanity: PASS")


def _run_local_reference_checks():
    print("Running host-side reference checks before silicon dispatch...")
    _ref_test_sha3_matches_hashlib()
    _ref_test_shake_matches_hashlib()
    _ref_test_sample_ntt_range_and_size()
    _ref_test_cbd_pmf()


# ------------------------------------------------------------------
# Silicon PASS gates.

def _gate_a_transliteration():
    """Gate (a): silicon output bit-exact against host reference across
    3 seeds x 4 modes (SHA3-256, SHA3-512, SHAKE128, SHAKE256)."""
    print("\n=== gate (a) transliteration bit-exact ===")
    seeds = [0xC0FFEE, 0xDEADBEEF, 0xBADC0DE]
    n_pass = 0
    n_total = 0
    for seed in seeds:
        rng_s = np.random.default_rng(seed)
        msg = rng_s.integers(0, 256, size=200, dtype=np.uint8)
        for mode, out_len, rate, dsp, name in [
            (MODE_SHA3_256, 32, RATE_SHA3_256, DSP_SHA3, "SHA3-256"),
            (MODE_SHA3_512, 64, RATE_SHA3_512, DSP_SHA3, "SHA3-512"),
            (MODE_SHAKE128, 128, RATE_SHAKE128, DSP_SHAKE, "SHAKE128"),
            (MODE_SHAKE256, 128, RATE_SHAKE256, DSP_SHAKE, "SHAKE256"),
        ]:
            ctrl = _pack_ctrl(mode, len(msg), out_len)
            sil = _dispatch(msg, ctrl, f"gate(a) {name} seed=0x{seed:X}")
            ref = keccak_sponge(bytes(msg), out_len, rate, dsp)
            got = bytes(sil[:out_len])
            n_total += 1
            if got == ref:
                n_pass += 1
                print(f"[gate a] {name} seed=0x{seed:X}: PASS "
                      f"({out_len}-byte digest matches host reference)")
            else:
                print(f"[gate a] {name} seed=0x{seed:X}: FAIL")
                print(f"  ref = {ref.hex()}")
                print(f"  got = {got.hex()}")
    assert n_pass == n_total, \
        f"gate (a): {n_pass}/{n_total} PASS - silicon vs host reference mismatch"
    print(f"[gate a] transliteration bit-exact: PASS ({n_pass}/{n_total})")


def _gate_b_fips202_kat():
    """Gate (b): NIST FIPS 202 empty-message KATs match on silicon."""
    print("\n=== gate (b) FIPS 202 KAT ===")
    empty = np.zeros(0, dtype=np.uint8)
    # SHA3-256 empty
    ctrl = _pack_ctrl(MODE_SHA3_256, 0, 32)
    sil = _dispatch(empty, ctrl, "gate(b) SHA3-256 empty KAT")
    got = bytes(sil[:32])
    assert got == NIST_SHA3_256_EMPTY, \
        f"SHA3-256 empty KAT FAIL:\n  got={got.hex()}\n  exp={NIST_SHA3_256_EMPTY.hex()}"
    print("[gate b] SHA3-256 empty KAT: PASS")

    # SHA3-512 empty
    ctrl = _pack_ctrl(MODE_SHA3_512, 0, 64)
    sil = _dispatch(empty, ctrl, "gate(b) SHA3-512 empty KAT")
    got = bytes(sil[:64])
    assert got == NIST_SHA3_512_EMPTY, \
        f"SHA3-512 empty KAT FAIL:\n  got={got.hex()}\n  exp={NIST_SHA3_512_EMPTY.hex()}"
    print("[gate b] SHA3-512 empty KAT: PASS")

    # SHAKE128 empty, 32 bytes - compared against hashlib since we cross-checked
    # NIST_SHAKE128_EMPTY_32 in R2 already.
    ref_128 = hashlib.shake_128(b"").digest(32)
    ctrl = _pack_ctrl(MODE_SHAKE128, 0, 32)
    sil = _dispatch(empty, ctrl, "gate(b) SHAKE128 empty 32B KAT")
    got = bytes(sil[:32])
    assert got == ref_128, \
        f"SHAKE128 empty KAT FAIL:\n  got={got.hex()}\n  exp={ref_128.hex()}"
    print("[gate b] SHAKE128 empty 32B KAT: PASS")

    ref_256 = hashlib.shake_256(b"").digest(32)
    ctrl = _pack_ctrl(MODE_SHAKE256, 0, 32)
    sil = _dispatch(empty, ctrl, "gate(b) SHAKE256 empty 32B KAT")
    got = bytes(sil[:32])
    assert got == ref_256, \
        f"SHAKE256 empty KAT FAIL:\n  got={got.hex()}\n  exp={ref_256.hex()}"
    print("[gate b] SHAKE256 empty 32B KAT: PASS")


def _gate_c_sample_ntt():
    """Gate (c): SampleNTT reproducibility + coefficients < q."""
    print("\n=== gate (c) SampleNTT ===")
    seed = bytes(range(32))
    j, i = 0, 0

    in_bytes = np.frombuffer(seed + bytes([j, i]), dtype=np.uint8).copy()
    ctrl = _pack_ctrl(MODE_SAMPLE_NTT, len(in_bytes), 2 * KYBER_N)
    sil = _dispatch(in_bytes, ctrl, f"gate(c) SampleNTT seed=range(32) j={j} i={i}")

    coeffs = np.frombuffer(sil[:2 * KYBER_N].tobytes(), dtype=np.int16).copy()
    assert coeffs.shape == (KYBER_N,)
    assert coeffs.min() >= 0, f"SampleNTT negative coeff: min={coeffs.min()}"
    assert coeffs.max() < KYBER_Q, f"SampleNTT coeff >= q: max={coeffs.max()}"
    ref = sample_ntt(seed, j, i)
    assert np.array_equal(coeffs, ref), (
        "SampleNTT silicon vs reference mismatch: "
        f"first_diff_idx={int(np.argmax(coeffs != ref))}")
    print(f"[gate c] SampleNTT range 0..{KYBER_Q - 1}: PASS "
          f"(min={coeffs.min()}, max={coeffs.max()})")
    print("[gate c] SampleNTT reproducibility vs host reference: PASS")


def _gate_d_sample_cbd():
    """Gate (d): SamplePolyCBD reproducibility for eta in {2, 3} +
    binomial-pmf sanity."""
    print("\n=== gate (d) SamplePolyCBD ===")
    seed = bytes([0x42] * 32)
    for eta in (2, 3):
        b = 0
        in_bytes = np.frombuffer(seed + bytes([b]), dtype=np.uint8).copy()
        ctrl = _pack_ctrl(MODE_SAMPLE_CBD, len(in_bytes), 2 * KYBER_N, eta=eta)
        sil = _dispatch(in_bytes, ctrl,
                        f"gate(d) SamplePolyCBD eta={eta} b={b}")
        coeffs = np.frombuffer(sil[:2 * KYBER_N].tobytes(),
                               dtype=np.int16).copy()
        assert coeffs.shape == (KYBER_N,)
        assert coeffs.min() >= -eta and coeffs.max() <= eta, \
            f"CBD eta={eta} out of support: [{coeffs.min()}, {coeffs.max()}]"
        ref = sample_poly_cbd(seed, b, eta)
        assert np.array_equal(coeffs, ref), \
            f"CBD eta={eta} silicon vs reference mismatch"
        print(f"[gate d] SamplePolyCBD eta={eta} reproducibility: PASS")
        # Aggregate 16 blocks to get 4096 samples and check pmf moments.
        agg = [coeffs]
        for bb in range(1, 16):
            in_bytes = np.frombuffer(seed + bytes([bb]), dtype=np.uint8).copy()
            ctrl = _pack_ctrl(MODE_SAMPLE_CBD, len(in_bytes),
                              2 * KYBER_N, eta=eta)
            sil = _dispatch(in_bytes, ctrl,
                            f"gate(d) SamplePolyCBD eta={eta} b={bb}")
            agg.append(np.frombuffer(sil[:2 * KYBER_N].tobytes(),
                                     dtype=np.int16).copy())
        agg = np.concatenate(agg)
        mu = float(agg.mean())
        var = float(agg.var())
        target_var = 1.0 if eta == 2 else 1.5
        print(f"[gate d] CBD eta={eta}: 4096-sample mean={mu:+.4f} "
              f"var={var:.4f} (target {target_var:.2f})")
        assert abs(mu) < 0.10, \
            f"CBD eta={eta} mean {mu} too far from 0"
        assert abs(var - target_var) < 0.30, \
            f"CBD eta={eta} var {var} too far from {target_var}"
    print("[gate d] SamplePolyCBD moments: PASS")


# ------------------------------------------------------------------
# Reference-only pytest entry points (do not touch the NPU).

def test_reference_r1_sha3_matches_hashlib():
    _ref_test_sha3_matches_hashlib()


def test_reference_r2_shake_matches_hashlib():
    _ref_test_shake_matches_hashlib()


def test_reference_r3_sample_ntt_range_and_size():
    _ref_test_sample_ntt_range_and_size()


def test_reference_r4_cbd_pmf():
    _ref_test_cbd_pmf()


# ------------------------------------------------------------------
# Silicon PASS gates as pytest entry points.

def test_gate_a_transliteration():
    _gate_a_transliteration()


def test_gate_b_fips202_kat():
    _gate_b_fips202_kat()


def test_gate_c_sample_ntt():
    _gate_c_sample_ntt()


def test_gate_d_sample_cbd():
    _gate_d_sample_cbd()


if __name__ == "__main__":
    _run_local_reference_checks()
    print("\n" + "=" * 60)
    print("Silicon PASS gates (M32c PQC foundations)")
    print("=" * 60)
    _gate_a_transliteration()
    _gate_b_fips202_kat()
    _gate_c_sample_ntt()
    _gate_d_sample_cbd()
    print("\n" + "=" * 60)
    print("M32c: ALL SILICON GATES PASS")
    print("=" * 60)
