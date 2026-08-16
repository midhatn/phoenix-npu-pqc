# Purpose: Milestone 32d - Post-Quantum Cryptography K-PKE byte-serialization
#          on AMD Phoenix NPU.
#          Runs a single-tile AIE2 kernel that implements the pq-crystals
#          reference primitives called by FIPS 203 Algorithms 13-15
#          (K-PKE.KeyGen / K-PKE.Encrypt / K-PKE.Decrypt):
#              poly_compress   / poly_decompress   (d=4,  128-byte payload)
#              polyvec_compress/ polyvec_decompress (d=10, 320-byte per-poly slice)
#              poly_tobytes    / poly_frombytes    (d=12, 384-byte payload)
#              poly_frommsg    / poly_tomsg        (d=1,  32-byte message)
#          Combined with M32b (NTT/INTT/MultiplyNTTs/BaseCaseMultiply, poly
#          add/sub) and M32c (SHA-3, SHAKE, SampleNTT, SamplePolyCBD) this
#          closes the compute floor needed to compose ML-KEM-512 (M32e).
#
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types:
#   in_a    : int16 lanes (up to 512), byte streams packed as low byte of int16
#   in_ctrl : int16, 8-element control block  (mode, ...)
#   out_c   : int16 lanes (up to 512)
# Scaling: bit-exact integer, no floating-point.
# State requirements: device 0 (NPU Phoenix).
# Error handling: All silicon gates are asserted.
#
# Design: docs/M32d_DESIGN.md
# Host API pin: mlir-aie v1.4.1 iron.Runtime sequence-function API.
#
# Silicon gates (see docs/M32d_DESIGN.md sec 4):
#   (a) d=4 Compress/Decompress round-trip on ciphertext-realistic inputs
#       (values already close to a d=4 lattice) is bit-exact vs host and
#       satisfies Compress(Decompress(y)) == y.
#   (b) d=10 Compress/Decompress round-trip on ciphertext-realistic inputs.
#   (c) d=12 ByteEncode/ByteDecode is a pure serialization (lossless): silicon
#       poly_frombytes(poly_tobytes(a)) == a canonicalized to [0, q-1], and
#       both directions match the host reference bit-exactly.
#   (d) d=1 message round-trip: poly_tomsg(poly_frommsg(m)) == m for random
#       32-byte messages, on silicon, and both directions match host.
#
# References:
#   * FIPS 203 (Aug 2024), ML-KEM standard, Algorithms 13-15 and Section 4.2.1.
#     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
#   * pq-crystals/kyber ref/poly.c and ref/polyvec.c.
#     https://github.com/pq-crystals/kyber/blob/main/ref/poly.c
#     https://github.com/pq-crystals/kyber/blob/main/ref/polyvec.c
#   * CRYSTALS-Kyber round-3 specification.
#     https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf

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
# Constants (must match kpke_kernel.cc exactly).

MAX_LANES = 512
CTRL_LEN  = 8

MODE_COMPRESS_D4     = 0
MODE_DECOMPRESS_D4   = 1
MODE_COMPRESS_D10    = 2
MODE_DECOMPRESS_D10  = 3
MODE_TOBYTES_D12     = 4
MODE_FROMBYTES_D12   = 5
MODE_FROMMSG         = 6
MODE_TOMSG           = 7

KYBER_N = 256
KYBER_Q = 3329


# ------------------------------------------------------------------
# Host reference - bit-exact Python transliteration of kpke_kernel.cc.
# All arithmetic uses Python ints; masking to uint32/uint64 windows is
# done explicitly to mirror the C code.

_U32 = (1 << 32) - 1
_U64 = (1 << 64) - 1


def _to_int16(x):
    """C-style int16 wrap."""
    v = int(x) & 0xFFFF
    if v >= 0x8000:
        v -= 0x10000
    return v


def _canonical(v):
    """u += (u >> 15) & KYBER_Q -- signed-to-canonical.

    In C the expression is:  (int16_t)((int16_t)(v >> 15) & KYBER_Q).
    Arithmetic right shift of a negative int16 by 15 yields -1 (all-ones),
    which AND'd with q yields q. For a non-negative v it yields 0.
    So the correction is: add q if v < 0, else add 0.
    """
    s = KYBER_Q if int(v) < 0 else 0
    return _to_int16(int(v) + s)


def ref_compress_d4(coeffs):
    """poly_compress d=4: 256 int16 -> 128 uint8."""
    out = np.zeros(128, dtype=np.uint8)
    r = 0
    for i in range(KYBER_N // 8):
        t = [0] * 8
        for j in range(8):
            u = _canonical(int(coeffs[8 * i + j]))
            d0 = (u & 0xFFFF) << 4
            d0 = (d0 + 1665) & _U32
            d0 = (d0 * 80635) & _U32
            d0 >>= 28
            t[j] = d0 & 0xF
        out[r + 0] = (t[0] | (t[1] << 4)) & 0xFF
        out[r + 1] = (t[2] | (t[3] << 4)) & 0xFF
        out[r + 2] = (t[4] | (t[5] << 4)) & 0xFF
        out[r + 3] = (t[6] | (t[7] << 4)) & 0xFF
        r += 4
    return out


def ref_decompress_d4(bytes128):
    """poly_decompress d=4: 128 uint8 -> 256 int16 (values in [0, q-1])."""
    out = np.zeros(KYBER_N, dtype=np.int16)
    for i in range(KYBER_N // 2):
        a0 = int(bytes128[i])
        lo = a0 & 15
        hi = a0 >> 4
        out[2 * i + 0] = ((lo * KYBER_Q) + 8) >> 4
        out[2 * i + 1] = ((hi * KYBER_Q) + 8) >> 4
    return out


def ref_compress_d10(coeffs):
    """polyvec_compress d=10 for one poly: 256 int16 -> 320 uint8."""
    out = np.zeros(320, dtype=np.uint8)
    r = 0
    for j in range(KYBER_N // 4):
        t = [0] * 4
        for k in range(4):
            v = _canonical(int(coeffs[4 * j + k]))
            d0 = (v & 0xFFFF)
            d0 = (d0 << 10) & _U64
            d0 = (d0 + 1665) & _U64
            d0 = (d0 * 1290167) & _U64
            d0 >>= 32
            t[k] = d0 & 0x3FF
        out[r + 0] = (t[0] >> 0) & 0xFF
        out[r + 1] = ((t[0] >> 8) | (t[1] << 2)) & 0xFF
        out[r + 2] = ((t[1] >> 6) | (t[2] << 4)) & 0xFF
        out[r + 3] = ((t[2] >> 4) | (t[3] << 6)) & 0xFF
        out[r + 4] = (t[3] >> 2) & 0xFF
        r += 5
    return out


def ref_decompress_d10(bytes320):
    """polyvec_decompress d=10 for one poly: 320 uint8 -> 256 int16."""
    out = np.zeros(KYBER_N, dtype=np.int16)
    a = 0
    for j in range(KYBER_N // 4):
        a0 = int(bytes320[a + 0])
        a1 = int(bytes320[a + 1])
        a2 = int(bytes320[a + 2])
        a3 = int(bytes320[a + 3])
        a4 = int(bytes320[a + 4])
        t = [
            ((a0 >> 0) | (a1 << 8)) & 0xFFFF,
            ((a1 >> 2) | (a2 << 6)) & 0xFFFF,
            ((a2 >> 4) | (a3 << 4)) & 0xFFFF,
            ((a3 >> 6) | (a4 << 2)) & 0xFFFF,
        ]
        a += 5
        for k in range(4):
            x = ((t[k] & 0x3FF) * KYBER_Q + 512) & _U32
            out[4 * j + k] = x >> 10
    return out


def ref_tobytes_d12(coeffs):
    """poly_tobytes: 256 int16 -> 384 uint8. Canonicalizes first."""
    out = np.zeros(384, dtype=np.uint8)
    for i in range(KYBER_N // 2):
        c0 = int(coeffs[2 * i + 0])
        c1 = int(coeffs[2 * i + 1])
        t0 = _canonical(c0) & 0xFFFF
        t1 = _canonical(c1) & 0xFFFF
        out[3 * i + 0] = (t0 >> 0) & 0xFF
        out[3 * i + 1] = ((t0 >> 8) | (t1 << 4)) & 0xFF
        out[3 * i + 2] = (t1 >> 4) & 0xFF
    return out


def ref_frombytes_d12(bytes384):
    """poly_frombytes: 384 uint8 -> 256 int16 (values in [0, 4095])."""
    out = np.zeros(KYBER_N, dtype=np.int16)
    for i in range(KYBER_N // 2):
        b0 = int(bytes384[3 * i + 0])
        b1 = int(bytes384[3 * i + 1])
        b2 = int(bytes384[3 * i + 2])
        out[2 * i + 0] = ((b0 >> 0) | (b1 << 8)) & 0xFFF
        out[2 * i + 1] = ((b1 >> 4) | (b2 << 4)) & 0xFFF
    return out


def ref_frommsg(msg32):
    """poly_frommsg: 32 uint8 -> 256 int16 (each coeff is 0 or (q+1)/2)."""
    out = np.zeros(KYBER_N, dtype=np.int16)
    mask = (KYBER_Q + 1) // 2
    for i in range(32):
        mi = int(msg32[i])
        for j in range(8):
            bit = (mi >> j) & 1
            out[8 * i + j] = bit * mask
    return out


def ref_tomsg(coeffs):
    """poly_tomsg: 256 int16 -> 32 uint8."""
    out = np.zeros(32, dtype=np.uint8)
    for i in range(32):
        mi = 0
        for j in range(8):
            v = _canonical(int(coeffs[8 * i + j])) & 0xFFFF
            t = v & _U32
            t = (t << 1) & _U32
            t = (t + 1665) & _U32
            t = (t * 80635) & _U32
            t >>= 28
            t &= 1
            mi |= (t << j)
        out[i] = mi & 0xFF
    return out


# ------------------------------------------------------------------
# IRON JIT plumbing - single-tile, 2 in-fifos + 1 out-fifo, identical
# topology to M32c/M32b (both silicon-PASSed).

@iron.jit
def kpke_program(
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
        source_file=str(current_dir / "kpke_kernel.cc"),
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

def _pack_ctrl(mode):
    ctrl = np.zeros(CTRL_LEN, dtype=np.int16)
    ctrl[0] = mode
    return ctrl


def _pack_bytes_as_int16(byte_arr, n_lanes=MAX_LANES):
    """Byte stream -> int16 lane array (low byte carries value, high byte = 0)."""
    out = np.zeros(n_lanes, dtype=np.int16)
    for i, b in enumerate(byte_arr):
        out[i] = int(b) & 0xFF
    return out


def _unpack_int16_to_bytes(int16_arr, n_bytes):
    """int16 lane array -> byte stream (take low byte of each lane)."""
    return np.array([int(int16_arr[i]) & 0xFF for i in range(n_bytes)],
                    dtype=np.uint8)


def _dispatch(in_lanes, ctrl, tag):
    """Compile and run once, return out_c buffer as int16 array of MAX_LANES."""
    print(f"\n--- Silicon dispatch: {tag} ---")

    padded_a = np.zeros(MAX_LANES, dtype=np.int16)
    padded_a[:len(in_lanes)] = in_lanes
    padded_ctrl = np.zeros(CTRL_LEN, dtype=np.int16)
    padded_ctrl[:len(ctrl)] = ctrl
    np_out = np.zeros(MAX_LANES, dtype=np.int16)

    a_t = XRTTensor(padded_a, dtype=np.int16)
    ctrl_t = XRTTensor(padded_ctrl, dtype=np.int16)
    out_t = XRTTensor(np_out, dtype=np.int16)

    print(f"Compiling M32d kpke ({tag}) and dispatching to Phoenix NPU...")
    res = kpke_program(
        a_t, ctrl_t, out_t,
        N_A_SLOTS=MAX_LANES,
        N_CTRL_SLOTS=CTRL_LEN,
        N_OUT_SLOTS=MAX_LANES,
        kernel_name="kpke",
        element_type=np.int16,
    )
    print(f"Kernel execution result: {res}")

    out_t.to("cpu")
    return out_t._data


# ------------------------------------------------------------------
# Reference (host-only) tests.

def _random_poly_signed(rng):
    """Uniform int16 polynomial in (-q/2, q/2] -- canonical signed form."""
    v = rng.integers(0, KYBER_Q, size=KYBER_N).astype(np.int64)
    v = np.where(v > KYBER_Q // 2, v - KYBER_Q, v).astype(np.int16)
    return v


def _random_poly_unsigned(rng):
    """Uniform int16 polynomial in [0, q-1] -- canonical unsigned form."""
    return rng.integers(0, KYBER_Q, size=KYBER_N).astype(np.int16)


def _ref_test_compress_d4_roundtrip():
    """R1: Decompress_d4(Compress_d4(Decompress_d4(y))) == Decompress_d4(y)
    (Compress o Decompress is the identity on Z_{2^d}). We verify by starting
    from a uint8 lattice y in [0, 16), lifting to a poly via Decompress_d4,
    Compress_d4-ing back, and checking bit-exact equality with y."""
    rng = np.random.default_rng(0xC0FFEE01)
    for k in range(3):
        y = rng.integers(0, 16, size=KYBER_N, dtype=np.uint8)
        # pack y into 128 bytes exactly as poly_compress d=4 would emit them
        # so we can decompress the 128 bytes.
        packed = np.zeros(128, dtype=np.uint8)
        for i in range(KYBER_N // 2):
            packed[i] = (y[2 * i] | (y[2 * i + 1] << 4)) & 0xFF
        p = ref_decompress_d4(packed)
        c = ref_compress_d4(p)
        # Rebuild y' from c and compare byte-for-byte with the original packed.
        assert np.array_equal(c, packed), \
            f"compress_d4 round-trip mismatch on trial #{k}"
    print("[reference] R1 Compress_d4(Decompress_d4(y)) == y on 3 trials: PASS")


def _ref_test_compress_d10_roundtrip():
    """R2: Compress_d10(Decompress_d10(y)) == y for uint8 lattice y with 10-bit
    codewords."""
    rng = np.random.default_rng(0xC0FFEE02)
    for k in range(3):
        y = rng.integers(0, 1 << 10, size=KYBER_N, dtype=np.uint16)
        # Emit as a d=10 packed byte stream (5 bytes per 4 codewords).
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
        p = ref_decompress_d10(packed)
        c = ref_compress_d10(p)
        assert np.array_equal(c, packed), \
            f"compress_d10 round-trip mismatch on trial #{k}"
    print("[reference] R2 Compress_d10(Decompress_d10(y)) == y on 3 trials: PASS")


def _ref_test_tobytes_d12_roundtrip():
    """R3: ByteEncode_12/ByteDecode_12 is a pure serialization (no lossy
    step), so tobytes(frombytes(b)) == b for arbitrary 12-bit codeword arrays,
    and frombytes(tobytes(a)) == canonical(a) mod 2^12."""
    rng = np.random.default_rng(0xC0FFEE03)
    for k in range(3):
        # frombytes(tobytes(a)) == a canonicalized
        a = _random_poly_signed(rng)
        packed = ref_tobytes_d12(a)
        back = ref_frombytes_d12(packed)
        exp = np.array([(_canonical(int(x)) & 0xFFF) for x in a], dtype=np.int16)
        assert np.array_equal(back, exp), \
            f"tobytes_d12 canonical round-trip mismatch on trial #{k}"
    print("[reference] R3 frombytes_d12(tobytes_d12(a)) == canonical(a): PASS")


def _ref_test_msg_roundtrip():
    """R4: poly_tomsg(poly_frommsg(m)) == m for random 32-byte messages."""
    rng = np.random.default_rng(0xC0FFEE04)
    for k in range(3):
        m = rng.integers(0, 256, size=32, dtype=np.uint8)
        p = ref_frommsg(m)
        back = ref_tomsg(p)
        assert np.array_equal(back, m), \
            f"tomsg(frommsg(m)) mismatch on trial #{k}"
    print("[reference] R4 tomsg(frommsg(m)) == m on 3 trials: PASS")


def _run_local_reference_checks():
    print("Running host-side reference checks before silicon dispatch...")
    _ref_test_compress_d4_roundtrip()
    _ref_test_compress_d10_roundtrip()
    _ref_test_tobytes_d12_roundtrip()
    _ref_test_msg_roundtrip()


# ------------------------------------------------------------------
# Silicon PASS gates.

def _silicon_extract_bytes(sil_raw, n_bytes):
    """Extract byte stream from silicon output (each byte is low byte of int16)."""
    return _unpack_int16_to_bytes(sil_raw, n_bytes)


def _silicon_extract_coeffs(sil_raw, n_coeffs=KYBER_N):
    return np.frombuffer(
        sil_raw[:n_coeffs * 2].tobytes()
        if hasattr(sil_raw, "tobytes") else bytes(sil_raw[:n_coeffs * 2]),
        dtype=np.int16).copy()[:n_coeffs]


def _gate_a_compress_d4():
    """Gate (a): silicon Compress_d4 and Decompress_d4 bit-exact vs host on
    random coefficient inputs, and Compress_d4(Decompress_d4(y)) == y round-trip
    on silicon."""
    print("\n=== gate (a) Compress/Decompress d=4 ===")
    rng = np.random.default_rng(0xA0B0C0D0)
    for k in range(3):
        # forward: signed poly -> 128 bytes
        a = _random_poly_signed(rng)
        ref_bytes = ref_compress_d4(a)
        sil_out = _dispatch(a, _pack_ctrl(MODE_COMPRESS_D4),
                            f"gate(a) compress_d4 #{k}")
        sil_bytes = _silicon_extract_bytes(sil_out, 128)
        assert np.array_equal(sil_bytes, ref_bytes), \
            f"gate (a) compress_d4 mismatch on #{k}: " \
            f"first_diff_idx={int(np.argmax(sil_bytes != ref_bytes))}"

        # inverse: 128 bytes -> poly, bit-exact vs host
        in_lanes = _pack_bytes_as_int16(ref_bytes)
        ref_p = ref_decompress_d4(ref_bytes)
        sil_out2 = _dispatch(in_lanes, _pack_ctrl(MODE_DECOMPRESS_D4),
                             f"gate(a) decompress_d4 #{k}")
        sil_p = _silicon_extract_coeffs(sil_out2)
        assert np.array_equal(sil_p, ref_p), \
            f"gate (a) decompress_d4 mismatch on #{k}"

        # Round-trip: Compress(Decompress(y)) == y on 16-value lattice
        y = rng.integers(0, 16, size=KYBER_N, dtype=np.uint8)
        packed_y = np.zeros(128, dtype=np.uint8)
        for i in range(KYBER_N // 2):
            packed_y[i] = (y[2 * i] | (y[2 * i + 1] << 4)) & 0xFF
        # Decompress on silicon
        in_lanes2 = _pack_bytes_as_int16(packed_y)
        sil_dec = _dispatch(in_lanes2, _pack_ctrl(MODE_DECOMPRESS_D4),
                            f"gate(a) roundtrip decompress #{k}")
        p_sil = _silicon_extract_coeffs(sil_dec)
        # Compress on silicon
        sil_com = _dispatch(p_sil, _pack_ctrl(MODE_COMPRESS_D4),
                            f"gate(a) roundtrip compress #{k}")
        c_sil = _silicon_extract_bytes(sil_com, 128)
        assert np.array_equal(c_sil, packed_y), \
            f"gate (a) round-trip identity failed on #{k}"
        print(f"[gate a] compress/decompress d=4 pair #{k}: PASS "
              f"(bit-exact vs host + Compress(Decompress(y)) == y)")


def _gate_b_compress_d10():
    """Gate (b): silicon Compress_d10 and Decompress_d10 bit-exact vs host,
    and Compress_d10(Decompress_d10(y)) == y round-trip on silicon."""
    print("\n=== gate (b) Compress/Decompress d=10 ===")
    rng = np.random.default_rng(0xB0C0D0E0)
    for k in range(3):
        a = _random_poly_signed(rng)
        ref_bytes = ref_compress_d10(a)
        sil_out = _dispatch(a, _pack_ctrl(MODE_COMPRESS_D10),
                            f"gate(b) compress_d10 #{k}")
        sil_bytes = _silicon_extract_bytes(sil_out, 320)
        assert np.array_equal(sil_bytes, ref_bytes), \
            f"gate (b) compress_d10 mismatch on #{k}: " \
            f"first_diff_idx={int(np.argmax(sil_bytes != ref_bytes))}"

        in_lanes = _pack_bytes_as_int16(ref_bytes)
        ref_p = ref_decompress_d10(ref_bytes)
        sil_out2 = _dispatch(in_lanes, _pack_ctrl(MODE_DECOMPRESS_D10),
                             f"gate(b) decompress_d10 #{k}")
        sil_p = _silicon_extract_coeffs(sil_out2)
        assert np.array_equal(sil_p, ref_p), \
            f"gate (b) decompress_d10 mismatch on #{k}"

        # Round-trip on 10-bit lattice
        y = rng.integers(0, 1 << 10, size=KYBER_N, dtype=np.uint16)
        packed_y = np.zeros(320, dtype=np.uint8)
        r = 0
        for j in range(KYBER_N // 4):
            t0, t1, t2, t3 = int(y[4*j]), int(y[4*j+1]), int(y[4*j+2]), int(y[4*j+3])
            packed_y[r + 0] = t0 & 0xFF
            packed_y[r + 1] = ((t0 >> 8) | (t1 << 2)) & 0xFF
            packed_y[r + 2] = ((t1 >> 6) | (t2 << 4)) & 0xFF
            packed_y[r + 3] = ((t2 >> 4) | (t3 << 6)) & 0xFF
            packed_y[r + 4] = (t3 >> 2) & 0xFF
            r += 5
        in_lanes2 = _pack_bytes_as_int16(packed_y)
        sil_dec = _dispatch(in_lanes2, _pack_ctrl(MODE_DECOMPRESS_D10),
                            f"gate(b) roundtrip decompress #{k}")
        p_sil = _silicon_extract_coeffs(sil_dec)
        sil_com = _dispatch(p_sil, _pack_ctrl(MODE_COMPRESS_D10),
                            f"gate(b) roundtrip compress #{k}")
        c_sil = _silicon_extract_bytes(sil_com, 320)
        assert np.array_equal(c_sil, packed_y), \
            f"gate (b) round-trip identity failed on #{k}"
        print(f"[gate b] compress/decompress d=10 pair #{k}: PASS "
              f"(bit-exact vs host + Compress(Decompress(y)) == y)")


def _gate_c_tobytes_d12():
    """Gate (c): silicon poly_tobytes/poly_frombytes is a lossless serialization,
    bit-exact vs host, and frombytes(tobytes(a)) == canonical(a) mod 2^12."""
    print("\n=== gate (c) ByteEncode/ByteDecode d=12 ===")
    rng = np.random.default_rng(0xC1D2E3F4)
    for k in range(3):
        a = _random_poly_signed(rng)
        ref_bytes = ref_tobytes_d12(a)
        sil_out = _dispatch(a, _pack_ctrl(MODE_TOBYTES_D12),
                            f"gate(c) tobytes_d12 #{k}")
        sil_bytes = _silicon_extract_bytes(sil_out, 384)
        assert np.array_equal(sil_bytes, ref_bytes), \
            f"gate (c) tobytes_d12 mismatch on #{k}"

        in_lanes = _pack_bytes_as_int16(ref_bytes)
        ref_p = ref_frombytes_d12(ref_bytes)
        sil_out2 = _dispatch(in_lanes, _pack_ctrl(MODE_FROMBYTES_D12),
                             f"gate(c) frombytes_d12 #{k}")
        sil_p = _silicon_extract_coeffs(sil_out2)
        assert np.array_equal(sil_p, ref_p), \
            f"gate (c) frombytes_d12 mismatch on #{k}"

        # frombytes(tobytes(a)) == canonical(a) mod 2^12 -- lossless
        # Use silicon for both directions
        sil_com = _dispatch(a, _pack_ctrl(MODE_TOBYTES_D12),
                            f"gate(c) roundtrip tobytes #{k}")
        c_bytes = _silicon_extract_bytes(sil_com, 384)
        in_lanes_rt = _pack_bytes_as_int16(c_bytes)
        sil_dec = _dispatch(in_lanes_rt, _pack_ctrl(MODE_FROMBYTES_D12),
                            f"gate(c) roundtrip frombytes #{k}")
        back = _silicon_extract_coeffs(sil_dec)
        exp = np.array([(_canonical(int(x)) & 0xFFF) for x in a], dtype=np.int16)
        assert np.array_equal(back, exp), \
            f"gate (c) lossless round-trip failed on #{k}"
        print(f"[gate c] tobytes/frombytes d=12 pair #{k}: PASS "
              f"(lossless, bit-exact vs host)")


def _gate_d_msg_roundtrip():
    """Gate (d): silicon poly_frommsg/poly_tomsg bit-exact vs host, and
    tomsg(frommsg(m)) == m on silicon for random 32-byte messages."""
    print("\n=== gate (d) message frommsg/tomsg d=1 ===")
    rng = np.random.default_rng(0xD1E2F3A4)
    for k in range(3):
        m = rng.integers(0, 256, size=32, dtype=np.uint8)
        in_lanes = _pack_bytes_as_int16(m)
        # frommsg on silicon
        sil_out = _dispatch(in_lanes, _pack_ctrl(MODE_FROMMSG),
                            f"gate(d) frommsg #{k}")
        sil_p = _silicon_extract_coeffs(sil_out)
        ref_p = ref_frommsg(m)
        assert np.array_equal(sil_p, ref_p), \
            f"gate (d) frommsg mismatch on #{k}"
        # tomsg on silicon
        sil_out2 = _dispatch(sil_p, _pack_ctrl(MODE_TOMSG),
                             f"gate(d) tomsg #{k}")
        sil_m = _silicon_extract_bytes(sil_out2, 32)
        assert np.array_equal(sil_m, m), \
            f"gate (d) tomsg(frommsg(m)) == m failed on #{k}"
        ref_m = ref_tomsg(sil_p)
        assert np.array_equal(sil_m, ref_m), \
            f"gate (d) tomsg mismatch vs host on #{k}"
        print(f"[gate d] frommsg/tomsg pair #{k}: PASS "
              f"(bit-exact vs host + tomsg(frommsg(m)) == m)")


# ------------------------------------------------------------------
# Pytest entrypoints.

def test_R1_compress_d4_roundtrip_reference():
    _ref_test_compress_d4_roundtrip()


def test_R2_compress_d10_roundtrip_reference():
    _ref_test_compress_d10_roundtrip()


def test_R3_tobytes_d12_roundtrip_reference():
    _ref_test_tobytes_d12_roundtrip()


def test_R4_msg_roundtrip_reference():
    _ref_test_msg_roundtrip()


def test_gate_a_compress_d4_silicon():
    _gate_a_compress_d4()


def test_gate_b_compress_d10_silicon():
    _gate_b_compress_d10()


def test_gate_c_tobytes_d12_silicon():
    _gate_c_tobytes_d12()


def test_gate_d_msg_roundtrip_silicon():
    _gate_d_msg_roundtrip()


if __name__ == "__main__":
    _run_local_reference_checks()
    print("\nALL REFERENCE TESTS PASSED\n")
