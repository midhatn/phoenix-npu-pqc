# Purpose: Milestone 23 M-path Polyphase Channelizer (Analysis Filter Bank)
#          Silicon Validation on AMD Phoenix NPU. Fused M = 8 channel bank
#          with 8-tap polyphase branches + 8-point DFT on one AIE2 core.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 interleaved I/Q wideband (4096 slots = 2048 complex
#              pairs at rate f_s).
# Output types: bfloat16 interleaved I/Q per-channel decimated (4096 slots =
#               256 frames of M = 8 channels, each channel at rate f_s / M).
# Scaling: Direct bfloat16 operand load, float32 multiply-accumulate,
#          single bfloat16 truncation on final store.
# Alignment assumptions: handled by IRON XRTTensor / BO runtime.
# State requirements: device 0 (NPU Phoenix).
# Error handling: Bit-accurate tolerance check against reference at atol = 0.02.
#                 Larger than M22's 0.01 because the 8x8 DFT accumulates 8
#                 bf16 rounding errors versus M22's 4-tap dot + 1 mix.
#
# Design: docs/M23_DESIGN.md
# Host API pin: mlir-aie v1.4.1 iron.Runtime sequence-function API.
#
# Signal-chain math (Harris 2004 chapter 6 fig. 6.8, M-path analysis bank):
#     v[p] = sum_{k=0..K-1} hp[p][k] * s[p][k]           # polyphase FIR
#     y[k] = sum_{p=0..M-1} v[p] * exp(-j 2 pi k p / M)  # M-point DFT
# where hp[p][k] = h_prototype[p + k*M] and s[p][:] is the K-slot shift
# register for branch p. Natural sample-to-branch commutator order (p = q).
#
# Prototype filter (docs/M23_DESIGN.md section 3.1):
#   * length N = M * K = 64
#   * Kaiser window (beta ~ 5.653) with cutoff omega_c = 1 / M = pi / M
#   * scipy.signal.firwin(..., scale=True) so sum(h) ~ 1.0
#   * bfloat16-quantized -> constexpr in kernel, list in host reference
#
# References:
#   * Harris, "Multirate Signal Processing for Communication Systems",
#     Prentice Hall 2004, chapter 6 section 6.3 (M-path analysis bank).
#     https://ieeexplore.ieee.org/book/9448967
#   * Vaidyanathan, "Multirate Systems and Filter Banks", Prentice Hall 1993,
#     chapter 4 (polyphase commutator identity).
#     https://dl.acm.org/doi/10.5555/151045
#   * GNU Radio Polyphase Channelizer (pfb_channelizer_ccf):
#     https://wiki.gnuradio.org/index.php/Polyphase_Channelizer
#   * NVIDIA MatX channelize_poly (natural sample-to-branch order):
#     https://nvidia.github.io/MatX/api/signalimage/filtering/channelize_poly.html
#   * Kaiser 1974 "Nonrecursive digital filter design using I_0-sinh window":
#     https://ieeexplore.ieee.org/document/1451724
#   * scipy.signal.firwin (Kaiser prototype design with normalized gain):
#     https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.firwin.html

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
from aie.utils.verify import assert_pass
from ml_dtypes import bfloat16

# ------------------------------------------------------------------
# Constants (bfloat16-quantized so the reference matches the silicon
# term-for-term). Values emitted by tools/m23_dump_constants.py.
M = 8               # number of channels
K = 8               # taps per polyphase branch
NTAPS = M * K       # 64

# Polyphase branches hp[p][k] = h_proto[p + k*M], with values matching the
# EXACT bfloat16 quantum used by channelizer_kernel.cc (single-truncation:
# firwin output -> bfloat16 -> float32 literal). Kernel and host reference
# share this one canonical table so silicon vs host is bit-exact.
HP_BF16 = np.array([
    [-4.029273987e-05, +4.959106445e-04, -2.075195312e-03, +7.141113281e-03, +1.240234375e-01, -6.042480469e-03, +1.770019531e-03, -3.986358643e-04],
    [-1.850128174e-04, +1.747131348e-03, -6.896972656e-03, +2.441406250e-02, +1.171875000e-01, -1.464843750e-02, +4.302978516e-03, -8.964538574e-04],
    [-4.119873047e-04, +3.173828125e-03, -1.196289062e-02, +4.443359375e-02, +1.040039062e-01, -1.879882812e-02, +5.462646484e-03, -1.037597656e-03],
    [-6.866455078e-04, +4.516601562e-03, -1.647949219e-02, +6.591796875e-02, +8.642578125e-02, -1.904296875e-02, +5.401611328e-03, -9.307861328e-04],
    [-9.307861328e-04, +5.401611328e-03, -1.904296875e-02, +8.642578125e-02, +6.591796875e-02, -1.647949219e-02, +4.516601562e-03, -6.866455078e-04],
    [-1.037597656e-03, +5.462646484e-03, -1.879882812e-02, +1.040039062e-01, +4.443359375e-02, -1.196289062e-02, +3.173828125e-03, -4.119873047e-04],
    [-8.964538574e-04, +4.302978516e-03, -1.464843750e-02, +1.171875000e-01, +2.441406250e-02, -6.896972656e-03, +1.747131348e-03, -1.850128174e-04],
    [-3.986358643e-04, +1.770019531e-03, -6.042480469e-03, +1.240234375e-01, +7.141113281e-03, -2.075195312e-03, +4.959106445e-04, -4.029273987e-05],
], dtype=np.float32)


def _polyphase_branches():
    """Return hp[p][k] = h_bf16[p + k*M], shape (M, K)."""
    return HP_BF16.copy()


def _dft_twiddles():
    """8x8 DFT twiddles (analysis convention: exp(-j 2 pi k n / M)).

    Bfloat16-quantized, with entries at multiples of pi/2 hard-zeroed to
    match the kernel's constexpr table. numpy's cos(pi/2) returns ~ 6e-17
    which is representable in bfloat16 but has no meaningful signal --
    keeping the residual would perturb ~ 30 of 4096 output slots at
    output bfloat16 resolution (see channelizer_kernel.cc DFT twiddle
    comment). This matches the M17p hard-zero pattern.
    """
    W_re = np.zeros((M, M), dtype=np.float32)
    W_im = np.zeros((M, M), dtype=np.float32)
    THRESH = 1e-6
    for k in range(M):
        for n in range(M):
            ang = -2.0 * np.pi * k * n / M
            vr = float(bfloat16(np.cos(ang)))
            vi = float(bfloat16(np.sin(ang)))
            W_re[k, n] = 0.0 if abs(vr) < THRESH else vr
            W_im[k, n] = 0.0 if abs(vi) < THRESH else vi
    return W_re, W_im


def channelizer_reference(in_bf16):
    """Bit-accurate NumPy reference that matches the fused kernel schedule.

    Inputs
    ------
    in_bf16 : np.ndarray of dtype bfloat16, shape (4096,), interleaved I/Q.
              All 2048 pairs are processed at rate f_s.

    Returns
    -------
    ref_bf16 : np.ndarray of dtype bfloat16, shape (4096,).
               256 frames * M = 8 complex outputs, each channel at rate f_s / M.
               Interleaved as (I_frame0_ch0, Q_frame0_ch0, I_frame0_ch1, Q_frame0_ch1,
               ..., I_frame0_ch7, Q_frame0_ch7, I_frame1_ch0, ...).
    """
    hp = _polyphase_branches()
    W_re, W_im = _dft_twiddles()

    in_f = in_bf16.astype(np.float32)
    Ix = in_f[0::2]   # 2048
    Qx = in_f[1::2]   # 2048

    si = np.zeros((M, K), dtype=np.float32)
    sq = np.zeros((M, K), dtype=np.float32)
    out = np.zeros(4096, dtype=np.float32)

    N_FRAMES = 256
    for frame in range(N_FRAMES):
        # Input commutator (natural: p = q).
        for q in range(M):
            p = q
            si[p, 1:] = si[p, :-1]
            sq[p, 1:] = sq[p, :-1]
            si[p, 0] = Ix[frame * M + q]
            sq[p, 0] = Qx[frame * M + q]

        # M-path polyphase FIR. Sequential `+=` accumulation to match the
        # kernel's C++ scalar accumulator bit-for-bit (numpy.dot uses SIMD
        # summation order which can round slightly differently).
        v_re = np.zeros(M, dtype=np.float32)
        v_im = np.zeros(M, dtype=np.float32)
        for p in range(M):
            acc_re = np.float32(0.0)
            acc_im = np.float32(0.0)
            for k in range(K):
                acc_re = np.float32(acc_re + np.float32(np.float32(si[p, k]) * np.float32(hp[p, k])))
                acc_im = np.float32(acc_im + np.float32(np.float32(sq[p, k]) * np.float32(hp[p, k])))
            v_re[p] = acc_re
            v_im[p] = acc_im

        # 8-point DFT (matmul-style). Sequential float32 accumulation with
        # C++ operator-precedence grouping: `yr += a - b` compiles to
        # `yr = yr + (a - b)` (the product-sum is evaluated first, then
        # added into the accumulator). This grouping matters at bfloat16
        # output quantization -- see docs/M23_DESIGN.md section 5.2.
        for k in range(M):
            yr = np.float32(0.0)
            yi = np.float32(0.0)
            for n in range(M):
                a = np.float32(np.float32(v_re[n]) * np.float32(W_re[k, n]))
                b = np.float32(np.float32(v_im[n]) * np.float32(W_im[k, n]))
                c = np.float32(np.float32(v_re[n]) * np.float32(W_im[k, n]))
                d = np.float32(np.float32(v_im[n]) * np.float32(W_re[k, n]))
                yr = np.float32(yr + np.float32(a - b))
                yi = np.float32(yi + np.float32(c + d))
            slot = 2 * (frame * M + k)
            out[slot    ] = yr
            out[slot + 1] = yi

    return out.astype(bfloat16)


@iron.jit
def polyphase_channelizer(
    input_iq: In,
    output_iq: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type],
):
    in_ty = np.ndarray[(N,), np.dtype[element_type]]
    out_ty = np.ndarray[(N,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in_iq")
    of_out = ObjectFifo(out_ty, name="out_iq")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(__file__).resolve().parents[2] / "include" / "sdr_dsp"

    ch_func = ExternalFunction(
        "channelizer_kernel",
        source_file=str(current_dir / "channelizer_kernel.cc"),
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_out, ch_func):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        ch_func(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    # stack_size override rationale in docs/M19_DESIGN.md section 5.3 and
    # M22 kernel notes. Channelizer footprint on stack: si/sq (8*8*4 = 256
    # bytes each), v_re/v_im (8*4 = 32 each). ~ 600 bytes, well under the
    # 16 KB override.
    worker = Worker(
        core_body,
        fn_args=[of_in.cons(), of_out.prod(), ch_func],
        stack_size=0x4000,
    )

    def sequence(a_in, c_out, in_prod, out_cons):
        in_prod.fill(a_in)
        out_cons.drain(c_out, wait=True)

    rt = Runtime(
        sequence,
        [in_ty, out_ty, of_in.prod(), of_out.cons()],
    )
    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()


# ------------------------------------------------------------------
# Host-side reference sanity checks (four gates before silicon dispatch).

def _pack_iq(Ix_f, Qx_f):
    """Pack 2048-pair wideband I/Q into a 4096-slot interleaved buffer."""
    iq = np.zeros(4096, dtype=np.float32)
    iq[0::2] = Ix_f
    iq[1::2] = Qx_f
    return iq.astype(bfloat16)


def _local_prototype_check():
    """Test 1: prototype LPF has correct DC gain and even symmetry."""
    # Reconstruct linear prototype h[p + k*M] from the polyphase branches.
    h = np.zeros(NTAPS, dtype=np.float32)
    for p in range(M):
        for k in range(K):
            h[p + k * M] = HP_BF16[p, k]
    dc_gain = float(h.sum())
    assert 0.99 < dc_gain < 1.01, f"prototype DC gain out of band: {dc_gain:.6f}"
    # Even symmetry: h[i] ~ h[N-1-i]
    sym_err = float(np.max(np.abs(h - h[::-1])))
    assert sym_err < 1e-6, f"prototype symmetry broken: max diff {sym_err:.6e}"
    print(f"[reference] Test 1 prototype: PASS (sum(h) = {dc_gain:.6f}, "
          f"symmetry max diff = {sym_err:.2e})")


def _local_dc_to_ch0_check():
    """Test 2: DC baseband input goes entirely to channel 0.

    Drive x[n] = 1 + j 0 for all n. After the polyphase FIR (unity DC
    gain end-to-end) and 8-point DFT, channel 0 output should be a pure
    DC term with unit magnitude and all other channels near zero.
    """
    Ix = np.ones(2048, dtype=np.float32)
    Qx = np.zeros(2048, dtype=np.float32)
    x = _pack_iq(Ix, Qx)
    y = channelizer_reference(x).astype(np.float32)
    yc = y[0::2] + 1j * y[1::2]
    ycf = yc.reshape(256, M)
    steady = np.mean(np.abs(ycf[K:]), axis=0)
    assert 0.95 < steady[0] < 1.05, f"ch0 DC magnitude out of band: {steady[0]:.4f}"
    iso = 20 * np.log10(steady[0] / max(steady[1:]))
    assert iso > 40.0, f"ch0 isolation too weak: {iso:.1f} dB"
    print(f"[reference] Test 2 DC -> ch0: PASS "
          f"(|ch0| = {steady[0]:.4f}, isolation = {iso:.1f} dB)")


def _local_on_channel_tone_check():
    """Test 3: on-carrier tone at f = +3*f_s/M lands in channel 3.

    Drive x[n] = exp(+j 2 pi 3 n / M). All other channels should be
    below -40 dB.
    """
    n = np.arange(2048)
    k_ch = 3
    tone = np.exp(1j * 2.0 * np.pi * k_ch * n / M).astype(np.complex64)
    Ix = tone.real.astype(np.float32)
    Qx = tone.imag.astype(np.float32)
    x = _pack_iq(Ix, Qx)
    y = channelizer_reference(x).astype(np.float32)
    yc = y[0::2] + 1j * y[1::2]
    ycf = yc.reshape(256, M)
    steady = np.mean(np.abs(ycf[K:]), axis=0)
    peak_ch = int(np.argmax(steady))
    others = np.delete(steady, k_ch)
    iso = 20 * np.log10(steady[k_ch] / max(others))
    assert peak_ch == k_ch, (
        f"on-channel tone peak in channel {peak_ch}, expected {k_ch}"
    )
    assert 0.95 < steady[k_ch] < 1.05, (
        f"on-channel |ch{k_ch}| out of band: {steady[k_ch]:.4f}"
    )
    assert iso > 40.0, f"on-channel isolation too weak: {iso:.1f} dB"
    print(f"[reference] Test 3 tone -> ch{k_ch}: PASS "
          f"(|ch{k_ch}| = {steady[k_ch]:.4f}, isolation = {iso:.1f} dB)")


def _local_two_tone_check():
    """Test 4: superposed tones at channels 1 and 5 split cleanly.

    x[n] = exp(+j 2 pi n / M) + exp(+j 2 pi 5 n / M). Channels 1 and 5
    each see magnitude ~ 1; other channels below -40 dB relative.
    """
    n = np.arange(2048)
    tone = (np.exp(1j * 2.0 * np.pi * n / M)
            + np.exp(1j * 2.0 * np.pi * 5 * n / M)).astype(np.complex64)
    Ix = tone.real.astype(np.float32)
    Qx = tone.imag.astype(np.float32)
    x = _pack_iq(Ix, Qx)
    y = channelizer_reference(x).astype(np.float32)
    yc = y[0::2] + 1j * y[1::2]
    ycf = yc.reshape(256, M)
    steady = np.mean(np.abs(ycf[K:]), axis=0)
    peak_targets = {1, 5}
    peaks = {i for i in range(M) if steady[i] > 0.5}
    assert peaks == peak_targets, f"two-tone peaks: got {peaks}, expected {peak_targets}"
    others = np.array([steady[m] for m in range(M) if m not in peak_targets])
    iso = 20 * np.log10(min(steady[1], steady[5]) / max(others))
    assert iso > 40.0, f"two-tone isolation too weak: {iso:.1f} dB"
    print(f"[reference] Test 4 two-tone (ch1 + ch5): PASS "
          f"(|ch1| = {steady[1]:.4f}, |ch5| = {steady[5]:.4f}, "
          f"isolation = {iso:.1f} dB)")


def _run_local_reference_checks():
    print("Running host-side reference checks before silicon dispatch...")
    _local_prototype_check()
    _local_dc_to_ch0_check()
    _local_on_channel_tone_check()
    _local_two_tone_check()


def main():
    print("=== Phoenix SDR-DSP Milestone 23: Polyphase Channelizer (M=8) Silicon Execution ===")
    data_size = 4096  # 2048 complex I/Q pairs in / 256 * 8 complex pairs out
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(
        f"Vector Length: {data_size} elements "
        f"(2048 complex I/Q pairs in, 256 frames * {M} channels out) "
        f"of {element_type.__name__}"
    )
    print(f"Channelizer: M = {M} channels, K = {K} taps/branch, "
          f"prototype length = {NTAPS}")

    _run_local_reference_checks()

    # --- Silicon PASS gate: random wideband I/Q vector.
    np.random.seed(793)
    Ix = np.random.uniform(-1.0, 1.0, 2048).astype(np.float32)
    Qx = np.random.uniform(-1.0, 1.0, 2048).astype(np.float32)
    np_in_bf16 = _pack_iq(Ix, Qx)
    np_out_iq = np.zeros(data_size, dtype=element_type)

    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_iq, dtype=element_type)

    print("Compiling fused polyphase channelizer with Peano and dispatching to Phoenix NPU...")
    res = polyphase_channelizer(in_tensor, out_tensor, N=data_size, element_type=element_type)
    print(f"Kernel execution result: {res}")

    out_tensor.to("cpu")

    print("Execution complete. Inspecting channelizer output vs reference...")

    ref_out_bf16 = channelizer_reference(np_in_bf16)
    out_np = out_tensor._data

    print(f"Input I/Q sample [0..4]:  {np_in_bf16[:4]}")
    print(f"Ref Out sample [0..4]:    {ref_out_bf16[:4]}")
    print(f"Actual Out sample [0..4]: {out_np[:4]}")

    max_err = float(
        np.max(
            np.abs(
                out_np.astype(np.float32) - ref_out_bf16.astype(np.float32)
            )
        )
    )
    print(f"Maximum absolute error: {max_err:.6f}")

    assert_pass(
        out_np,
        ref_out_bf16,
        fail_msg="Channelizer output mismatch",
        atol=0.02,
    )
    print(
        "SUCCESS: Phoenix NPU executed fused M-path polyphase channelizer "
        f"(M = {M}, K = {K}) on physical silicon!"
    )
    print("PASS!")


if __name__ == "__main__":
    main()
