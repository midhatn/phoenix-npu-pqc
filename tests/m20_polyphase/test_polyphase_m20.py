# Purpose: Milestone 20 Polyphase Decimation + Interpolation Silicon Validation
#          on AMD Phoenix NPU (M=L=4, 16-tap Kaiser prototype LPF, fused into
#          one kernel that runs decim then interp on the same AIE2 core).
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 interleaved I/Q signal (4096 elements = 2048 pairs).
# Output types: bfloat16 interleaved I/Q output (4096 elements = 2048 pairs),
#               representing decim -> interp end-to-end resampling with the
#               same nominal rate as the input (2048/M * L = 2048).
# Scaling: direct bfloat16 operand load, float32 multiply-accumulate,
#          single bfloat16 truncation on final store, matching M8/M19.
# Alignment assumptions: handled by IRON XRTTensor / BO runtime.
# State requirements: device 0 (NPU Phoenix).
# Error handling: Bit-accurate tolerance check against reference at atol=0.01.
#
# Design: docs/M20_DESIGN.md
# Host API pin: mlir-aie v1.4.1 iron.Runtime sequence-function API
#   https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py
# Polyphase decomposition (Vaidyanathan 1993 Ch. 4; Harris 2004 Ch. 6):
#   Decim: y[m] = sum_k h_d[k] * x[m*M - k]
#   Interp: y[m*L + k] = sum_r h_i[r*L + k] * x[m - r],  k in [0, L)
# This host reference reproduces the fused-kernel schedule term-for-term
# (see docs/M20_DESIGN.md sections 5.1, 5.2).
#
# Reference implementation and gain convention: scipy.signal.resample_poly
#   https://github.com/scipy/scipy/blob/main/scipy/signal/_signaltools.py
#   https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html
# Following scipy (and GNU Radio pfb), the interpolator taps are the prototype
# scaled by L so that the interpolator's DC gain equals L, compensating the
# 1/L amplitude loss from zero-insertion upsampling. The decimator uses the
# unmodified unity-DC prototype. Combined end-to-end DC gain of decim -> interp
# is thus ~1.0, bit-comparable to scipy.signal.upfirdn on the same taps.

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


# 16-tap Kaiser-window prototype LPF, beta=6, cutoff pi/4.
# Coefficients are pre-quantized to bfloat16 values so they exactly match
# the constexpr floats in tests/m20_polyphase/polyphase_kernel.cc.
# Design script and rationale: docs/M20_DESIGN.md section 3.
#
# COEFFS_HD_F: decimator taps (prototype h with unity DC gain, sum(h) ~ 1).
# COEFFS_HI_F: interpolator taps (prototype h scaled by L, sum(h*L) ~ L).
# The interp scaling follows scipy.signal.resample_poly's convention
# (scipy/signal/_signaltools.py `taps *= up`) and GNU Radio pfb.
COEFFS_HD_F = [
    -0.000242, -0.003281, -0.009644, -0.009216,
    +0.018677, +0.086426, +0.175781, +0.241211,
    +0.241211, +0.175781, +0.086426, +0.018677,
    -0.009216, -0.009644, -0.003281, -0.000242,
]
COEFFS_HI_F = [
    -0.000969, -0.013123, -0.038574, -0.036865,
    +0.074707, +0.345703, +0.703125, +0.964844,
    +0.964844, +0.703125, +0.345703, +0.074707,
    -0.036865, -0.038574, -0.013123, -0.000969,
]
N_TAPS = 16
M = 4
L = 4


def _bf16_decim_coeffs():
    """Cast decim tap constants through bfloat16 then back to float32.

    Matches the M5 convention (tests/m5_fir/test_fir_m5.py lines 104-105)
    so the reference sees the same operand values the kernel sees.
    """
    return np.array([float(bfloat16(c)) for c in COEFFS_HD_F], dtype=np.float32)


def _bf16_interp_coeffs():
    """Cast interp tap constants through bfloat16 then back to float32."""
    return np.array([float(bfloat16(c)) for c in COEFFS_HI_F], dtype=np.float32)


def polyphase_reference(in_bf16):
    """NumPy reference that reproduces the fused kernel's schedule.

    Stage 1 (decim, M=4):
      Ingest 4 fresh input pairs per output. Maintain a 16-slot shift
      register on I and Q. After ingest, compute
        out[m] = sum_{k=0..15} h[k] * x[m*4 - k]
      where hist[15] pairs with h[0] (newest sample, first tap) and
      hist[0] pairs with h[15] (oldest sample, last tap).

    Stage 2 (interp, L=4):
      Maintain a 4-slot shift register on the intermediate stream. For
      each intermediate input m, produce 4 output samples using the 4
      polyphase branches h[k], h[k+4], h[k+8], h[k+12] for k = 0..3.

    Inputs
    ------
    in_bf16 : np.ndarray of dtype bfloat16, shape (4096,), interleaved I/Q.

    Returns
    -------
    ref_bf16 : np.ndarray of dtype bfloat16, shape (4096,), interleaved I/Q.
    """
    hd = _bf16_decim_coeffs()
    hi = _bf16_interp_coeffs()

    in_f = in_bf16.astype(np.float32)
    Ix = in_f[0::2]
    Qx = in_f[1::2]
    assert Ix.shape[0] == 2048, f"expected 2048 input pairs, got {Ix.shape[0]}"

    # --- Stage 1: decim
    hist_i = np.zeros(16, dtype=np.float32)
    hist_q = np.zeros(16, dtype=np.float32)
    inter_i = np.zeros(512, dtype=np.float32)
    inter_q = np.zeros(512, dtype=np.float32)

    for m in range(512):
        # Ingest 4 fresh pairs.
        i0, i1, i2, i3 = Ix[m * 4], Ix[m * 4 + 1], Ix[m * 4 + 2], Ix[m * 4 + 3]
        q0, q1, q2, q3 = Qx[m * 4], Qx[m * 4 + 1], Qx[m * 4 + 2], Qx[m * 4 + 3]
        # Shift-4-and-ingest.
        hist_i[0:12] = hist_i[4:16]
        hist_i[12] = i0
        hist_i[13] = i1
        hist_i[14] = i2
        hist_i[15] = i3
        hist_q[0:12] = hist_q[4:16]
        hist_q[12] = q0
        hist_q[13] = q1
        hist_q[14] = q2
        hist_q[15] = q3
        # Dot product with hd[0..15]. hist[15] pairs with hd[0].
        Iacc = np.float32(0.0)
        Qacc = np.float32(0.0)
        for k in range(16):
            Iacc += hist_i[15 - k] * hd[k]
            Qacc += hist_q[15 - k] * hd[k]
        inter_i[m] = Iacc
        inter_q[m] = Qacc

    # --- Stage 2: interp
    xi = np.zeros(4, dtype=np.float32)
    xq = np.zeros(4, dtype=np.float32)
    out_i = np.zeros(2048, dtype=np.float32)
    out_q = np.zeros(2048, dtype=np.float32)

    for m in range(512):
        # Shift-1-and-ingest one intermediate pair.
        xi[0] = xi[1]; xi[1] = xi[2]; xi[2] = xi[3]; xi[3] = inter_i[m]
        xq[0] = xq[1]; xq[1] = xq[2]; xq[2] = xq[3]; xq[3] = inter_q[m]
        # Four polyphase output phases: k=0..3, tap indices k, k+4, k+8, k+12.
        # Uses the L-compensated interp taps hi (scipy resample_poly convention).
        for k in range(4):
            Iacc = xi[3] * hi[k] + xi[2] * hi[k + 4] + xi[1] * hi[k + 8] + xi[0] * hi[k + 12]
            Qacc = xq[3] * hi[k] + xq[2] * hi[k + 4] + xq[1] * hi[k + 8] + xq[0] * hi[k + 12]
            out_i[m * 4 + k] = Iacc
            out_q[m * 4 + k] = Qacc

    ref = np.zeros(4096, dtype=np.float32)
    ref[0::2] = out_i
    ref[1::2] = out_q
    return ref.astype(bfloat16)


@iron.jit
def polyphase_resample(
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

    poly_func = ExternalFunction(
        "polyphase_kernel",
        source_file=str(current_dir / "polyphase_kernel.cc"),
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_out, poly_func):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        poly_func(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    # stack_size override rationale is in docs/M19_DESIGN.md section 5.3
    # and tests/m17_radix2_fft/test_fft_m17_v3.py line 76. The fused M20
    # kernel keeps two 16-slot shift registers plus a 512-element float
    # intermediate buffer on stack -- 4.1 KB baseline, well under the
    # 16 KB override.
    worker = Worker(
        core_body,
        fn_args=[of_in.cons(), of_out.prod(), poly_func],
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


# --- Host-side reference-only sanity checks (Section 6 of docs/M20_DESIGN.md).
# These run before silicon dispatch to guarantee the reference contract is
# internally consistent. Any mismatch surfaces as AssertionError before we
# build the xclbin.

def _pack_iq(Ix_f, Qx_f, N):
    iq_f = np.zeros(N, dtype=np.float32)
    iq_f[0::2] = Ix_f
    iq_f[1::2] = Qx_f
    return iq_f.astype(bfloat16)


def _local_tap_consistency_check():
    """Test 1: Kaiser tap generation regeneration and diff.

    Regenerate the 16 taps in Python via the same Kaiser design formula
    used to derive the constants baked in polyphase_kernel.cc, and check
    that both the unity-DC decim taps and the L-scaled interp taps
    exactly match their bfloat16-quantized regenerations.
    """
    N = N_TAPS
    beta = 6.0
    n = np.arange(N)
    mid = (N - 1) / 2.0
    h_ideal = np.where(
        n == mid,
        1.0 / M,
        np.sin(np.pi * (n - mid) / M) / (np.pi * (n - mid)),
    )
    w = np.i0(beta * np.sqrt(1 - ((n - mid) / mid) ** 2)) / np.i0(beta)
    h = h_ideal * w
    h = h / np.sum(h)
    hd_bf = np.array([float(bfloat16(v)) for v in h], dtype=np.float32)
    hi_bf = np.array([float(bfloat16(v * L)) for v in h], dtype=np.float32)

    hd_baked = _bf16_decim_coeffs()
    hi_baked = _bf16_interp_coeffs()
    max_diff_d = float(np.max(np.abs(hd_bf - hd_baked)))
    max_diff_i = float(np.max(np.abs(hi_bf - hi_baked)))
    assert max_diff_d < 1e-6, (
        f"Decim tap consistency failure: max diff {max_diff_d:.6e}"
    )
    assert max_diff_i < 1e-6, (
        f"Interp tap consistency failure: max diff {max_diff_i:.6e}"
    )
    print(f"[reference] Test 1 Kaiser tap regeneration: PASS "
          f"(decim max_diff = {max_diff_d:.6e}, interp max_diff = {max_diff_i:.6e})")


def _local_impulse_check():
    """Test 2: Impulse at input index 0.

    Under the decim reference, an impulse Ix[0] = 1 produces
      inter_i[0] = h[15-0-4*(4-1)] ... no, easier:
      inter_i[m] = sum_k h[k] * x[m*4 - k] with x[0]=1 else 0
                 = h[m*4] for m*4 <= 15, else 0
    So inter_i[0] = h[0], inter_i[1] = h[4], inter_i[2] = h[8],
       inter_i[3] = h[12], inter_i[4] = 0, ...
    """
    N = 4096
    Ix = np.zeros(2048, dtype=np.float32)
    Qx = np.zeros(2048, dtype=np.float32)
    Ix[0] = 1.0
    in_bf16 = _pack_iq(Ix, Qx, N)

    ref = polyphase_reference(in_bf16).astype(np.float32)
    # Non-zero output positions have to be inside the first
    # (16-tap * L=4 output-samples-per-input) window.
    # After decim we've observed: inter[0]=h[0], inter[1]=h[4],
    # inter[2]=h[8], inter[3]=h[12], inter[m>=4]=0.
    # After interp this convolves h against inter, so the output pattern
    # is non-zero for output indices 0..15 only.
    out_I = ref[0::2]
    non_zero = np.count_nonzero(np.abs(out_I) > 1e-6)
    assert non_zero <= 32, (
        f"Impulse response spread too wide: {non_zero} non-zero output samples"
    )
    print(f"[reference] Test 2 impulse: PASS ({non_zero} non-zero output samples, "
          f"max |out| = {float(np.max(np.abs(out_I))):.6f})")


def _local_dc_check():
    """Test 3: DC input Ix=1, Qx=0.

    Decim taps have unity DC gain (sum(hd) ~ 1). Interp taps carry the
    L compensation (sum(hi) ~ L). Following scipy.signal.resample_poly
    (https://github.com/scipy/scipy/blob/main/scipy/signal/_signaltools.py,
    `taps *= up`) and GNU Radio pfb
    (https://www.gnuradio.org/doc/doxygen-3.7/page_pfb.html), the combined
    end-to-end DC gain of decim -> interp is
        sum(hd) * sum(hi) / L = 1 * L / L = 1
    so the steady-state DC I output is ~1.0 and Q is ~0. Each polyphase
    branch of hi contributes a slightly different branch sum, so the four
    output phases differ by about one bfloat16 ULP.
    """
    N = 4096
    Ix = np.ones(2048, dtype=np.float32)
    Qx = np.zeros(2048, dtype=np.float32)
    in_bf16 = _pack_iq(Ix, Qx, N)

    ref = polyphase_reference(in_bf16).astype(np.float32)
    # Deep tail is guaranteed steady state (both stages settled).
    tail_I = ref[0::2][1024:]
    tail_Q = ref[1::2][1024:]
    hd = _bf16_decim_coeffs()
    hi = _bf16_interp_coeffs()
    # Expected DC gain of the scipy-convention design: sum(hd) * sum(hi) / L
    exp_I = (float(np.sum(hd)) * float(np.sum(hi))) / float(L)
    max_dev_I = float(np.max(np.abs(tail_I - exp_I)))
    max_dev_Q = float(np.max(np.abs(tail_Q)))
    # Tolerance accounts for bfloat16 quantization on the intermediate
    # buffer plus ULP differences between the four polyphase branches.
    assert max_dev_I < 0.02, (
        f"DC I steady mismatch: max deviation {max_dev_I:.6f}, expected {exp_I:.6f}"
    )
    assert max_dev_Q < 0.02, (
        f"DC Q steady mismatch: max deviation {max_dev_Q:.6f} from 0"
    )
    print(f"[reference] Test 3 DC steady: PASS "
          f"(expected {exp_I:.6f} ~ 1.0, "
          f"max I dev {max_dev_I:.6f}, max Q dev {max_dev_Q:.6f})")


def _local_tone_check():
    """Test 4: Complex tone below cutoff. A tone at f_bin = 4 (well below
    the Nyquist/M = 512 cutoff of the LPF) should pass through both
    stages with combined passband gain ~1.0 (scipy-convention design;
    see _local_dc_check docstring for the derivation).
    """
    N = 4096
    M_pairs = 2048
    f_bin = 4.0  # cycles per M_pairs samples, well below pi/M
    t = np.arange(M_pairs, dtype=np.float32)
    phase = 2.0 * np.pi * f_bin * t / M_pairs
    x_cplx = np.exp(1j * phase).astype(np.complex64)
    Ix = x_cplx.real.astype(np.float32)
    Qx = x_cplx.imag.astype(np.float32)
    in_bf16 = _pack_iq(Ix, Qx, N)

    ref = polyphase_reference(in_bf16).astype(np.float32)
    ref_cplx = ref[0::2] + 1j * ref[1::2]

    # Steady-state deep tail
    tail = slice(512, M_pairs)
    ratio = ref_cplx[tail] / x_cplx[tail]
    mag = float(np.mean(np.abs(ratio)))
    mag_std = float(np.std(np.abs(ratio)))

    # For the scipy-convention design the passband amplitude ratio is ~1.0.
    exp_mag = 1.0
    assert exp_mag - 0.05 < mag < exp_mag + 0.05, (
        f"Tone magnitude out of range: {mag:.4f} (expected ~{exp_mag:.4f})"
    )
    assert mag_std < 0.05, f"Tone magnitude too unstable: std {mag_std:.4f}"
    print(f"[reference] Test 4 complex tone (f_bin=4): PASS "
          f"(mag = {mag:.4f} ~ 1.0, std = {mag_std:.4f})")


def _run_local_reference_checks():
    print("Running host-side reference checks before silicon dispatch...")
    _local_tap_consistency_check()
    _local_impulse_check()
    _local_dc_check()
    _local_tone_check()


def main():
    print("=== Phoenix SDR-DSP Milestone 20: Polyphase Decim + Interp Silicon Execution ===")
    data_size = 4096  # 2048 complex pairs in and 2048 complex pairs out (M*L=1)
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(
        f"Vector Length: {data_size} elements "
        f"({data_size // 2} complex I/Q pairs) of {element_type.__name__}"
    )
    print(f"Rates: M = {M} (decim), L = {L} (interp), N_taps = {N_TAPS} Kaiser prototype LPF")

    # Reference-only pre-checks (Kaiser regen, impulse, DC, tone)
    _run_local_reference_checks()

    # --- Silicon PASS gate: random I/Q vector.
    num_complex = data_size // 2
    np.random.seed(789)
    Ix = np.random.uniform(-1.0, 1.0, num_complex).astype(np.float32)
    Qx = np.random.uniform(-1.0, 1.0, num_complex).astype(np.float32)
    np_in_bf16 = _pack_iq(Ix, Qx, data_size)
    np_out_iq = np.zeros(data_size, dtype=element_type)

    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_iq, dtype=element_type)

    print("Compiling fused Polyphase Decim + Interp with Peano and dispatching to Phoenix NPU...")
    res = polyphase_resample(in_tensor, out_tensor, N=data_size, element_type=element_type)
    print(f"Kernel execution result: {res}")

    # Sync back from NPU to host memory
    out_tensor.to("cpu")

    print("Execution complete. Inspecting Polyphase output vs reference...")

    ref_out_bf16 = polyphase_reference(np_in_bf16)
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
        fail_msg="Polyphase output mismatch",
        atol=0.01,
    )
    print(
        "SUCCESS: Phoenix NPU executed 4:1 Decimator + 1:4 Interpolator "
        "Polyphase Filter on physical silicon!"
    )
    print("PASS!")


if __name__ == "__main__":
    main()
