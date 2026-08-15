# Purpose: Milestone 22 Digital Up-Converter (DUC) Silicon Validation on
#          AMD Phoenix NPU (fused interp-by-L=4 with Kaiser*L LPF + complex
#          NCO at f_c = +f_s/8 on one AIE2 core). Mathematical symmetric of
#          M21 DDC.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 interleaved I/Q baseband (4096 slots; first 1024
#              slots = 512 complex baseband pairs, rest zero).
# Output types: bfloat16 interleaved I/Q intermediate-frequency
#               (4096 slots = 2048 complex pairs at f_s, fully populated).
# Scaling: Direct bfloat16 operand load, float32 multiply-accumulate,
#          single bfloat16 truncation on final store.
# Alignment assumptions: handled by IRON XRTTensor / BO runtime.
# State requirements: device 0 (NPU Phoenix).
# Error handling: Bit-accurate tolerance check against reference at atol=0.01.
#
# Design: docs/M22_DESIGN.md
# Host API pin: mlir-aie v1.4.1 iron.Runtime sequence-function API.
#
# Signal-chain math (Harris 2004 section 8.4, DUC):
#     y_bb[n] = sum_r hi[r*L + k] * x_bb[m - r]     # polyphase L-interp LPF
#     x_if[n] = y_bb[n] * e^{+j 2 pi n / 8}         # complex-multiply by LO
# where n = m*L + k and hi is the Kaiser prototype scaled by L.
#
# Complex multiply (Oppenheim & Schafer 3e section 2.2; NIST DLMF section 1.9):
#     (I_y + j Q_y) * (cos_lo + j sin_lo) =
#         (I_y*cos_lo - Q_y*sin_lo) + j*(I_y*sin_lo + Q_y*cos_lo)
#
# LO LUT rationale: at f_c = +f_s/8 the LO repeats every 8 output samples,
# so 8 (cos, sin) pairs are stored and indexed by (n_out & 7). Sign-flipped
# from the M21 DDC LUT (upconvert vs downconvert). Reference:
#   Analog Devices MT-085 "Fundamentals of Direct Digital Synthesis (DDS)"
#   https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf
#
# Kaiser*L LPF rationale: reuses the exact 16-tap Kaiser prototype scaled
# by L=4 that the M20 stage-2 interpolator ships
# (tests/m20_polyphase/polyphase_kernel.cc). The `taps *= up` convention
# comes from
#   scipy.signal.resample_poly
#   https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html
# and compensates the 1/L amplitude loss from zero-stuff upsampling so
# unity DC gain end-to-end. Design formulae from
#   Kaiser 1974 "Nonrecursive digital filter design using I_0-sinh window"
#   https://ieeexplore.ieee.org/document/1451724
# Modified Bessel I_0 evaluated via numpy.i0 (NIST DLMF section 10.25):
#   https://dlmf.nist.gov/10.25
#
# Topology reference:
#   * GNU Radio Frequency Xlating FIR Filter (with negative decim = interp)
#     https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter

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
# 16-tap Kaiser prototype LPF scaled by L=4 (M20 stage-2 interp taps).
# sum(hi) ~ 4.00 for unity end-to-end DC gain after 1/L zero-stuff loss.
COEFFS_HI_F = [
    -0.000969, -0.013123, -0.038574, -0.036865,
    +0.074707, +0.345703, +0.703125, +0.964844,
    +0.964844, +0.703125, +0.345703, +0.074707,
    -0.036865, -0.038574, -0.013123, -0.000969,
]

# 8-entry LO LUT for f_c = +f_s/8 (upconvert baseband to +f_s/8).
# This is the M21 LO with sin_lo negated (positive-frequency mix).
LO_COS_F = [
    +1.000000, +0.707031, +0.000000, -0.707031,
    -1.000000, -0.707031, +0.000000, +0.707031,
]
LO_SIN_F = [
     0.000000, +0.707031, +1.000000, +0.707031,
     0.000000, -0.707031, -1.000000, -0.707031,
]

N_TAPS = 16
L = 4              # interpolation factor
N_LO = 8


def _bf16_taps():
    """Cast interp taps through bfloat16 then back to float32 so the
    reference sees the same operand values the kernel sees.
    """
    return np.array([float(bfloat16(c)) for c in COEFFS_HI_F], dtype=np.float32)


def _bf16_lo_cos():
    return np.array([float(bfloat16(c)) for c in LO_COS_F], dtype=np.float32)


def _bf16_lo_sin():
    return np.array([float(bfloat16(c)) for c in LO_SIN_F], dtype=np.float32)


def duc_reference(in_bf16):
    """Bit-accurate NumPy reference that matches the fused kernel schedule.

    Stage 1 (polyphase interp L=4): 4-slot shift register on the baseband
        stream, one shift-and-ingest per input pair, then L output phases
        from 4 different 4-tap subsets of the same 16-tap prototype.
    Stage 2 (mix): complex multiply each interpolated output pair by
        lo[(m*L + k) & 7], applied at the output (interpolated) rate.

    Inputs
    ------
    in_bf16 : np.ndarray of dtype bfloat16, shape (4096,), interleaved I/Q.
              First 1024 slots (= 512 baseband pairs) hold the input;
              remaining 3072 slots are ignored (kept zero by convention).

    Returns
    -------
    ref_bf16 : np.ndarray of dtype bfloat16, shape (4096,). All 2048 output
               pairs populated at the interpolated rate f_s.
    """
    hi = _bf16_taps()
    lo_cos = _bf16_lo_cos()
    lo_sin = _bf16_lo_sin()

    in_f = in_bf16.astype(np.float32)
    Ix = in_f[0:1024:2]
    Qx = in_f[1:1024:2]
    assert Ix.shape[0] == 512, f"expected 512 baseband pairs, got {Ix.shape[0]}"

    xi = np.zeros(4, dtype=np.float32)
    xq = np.zeros(4, dtype=np.float32)
    out = np.zeros(4096, dtype=np.float32)

    for m in range(512):
        xi[0] = xi[1]; xi[1] = xi[2]; xi[2] = xi[3]; xi[3] = Ix[m]
        xq[0] = xq[1]; xq[1] = xq[2]; xq[2] = xq[3]; xq[3] = Qx[m]

        for k in range(L):
            Iacc = (xi[3] * hi[k]
                    + xi[2] * hi[k + 4]
                    + xi[1] * hi[k + 8]
                    + xi[0] * hi[k + 12])
            Qacc = (xq[3] * hi[k]
                    + xq[2] * hi[k + 4]
                    + xq[1] * hi[k + 8]
                    + xq[0] * hi[k + 12])

            n_out = m * L + k
            c = lo_cos[n_out & 7]
            s = lo_sin[n_out & 7]
            I_if = Iacc * c - Qacc * s
            Q_if = Iacc * s + Qacc * c

            out[2 * n_out    ] = I_if
            out[2 * n_out + 1] = Q_if

    return out.astype(bfloat16)


@iron.jit
def duc_upconvert(
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

    duc_func = ExternalFunction(
        "duc_kernel",
        source_file=str(current_dir / "duc_kernel.cc"),
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_out, duc_func):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        duc_func(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    # stack_size override rationale is in docs/M19_DESIGN.md section 5.3
    # and tests/m17_radix2_fft/test_fft_m17_v3.py line 76. The fused M22
    # DUC kernel keeps only two 4-slot shift registers + 8-entry LO LUT +
    # 16-tap Kaiser*L LPF on stack (~ 130 bytes float32), well under the
    # 16 KB override. The override is retained to match the proven
    # M20/M21 AIE2 scheduling envelope.
    worker = Worker(
        core_body,
        fn_args=[of_in.cons(), of_out.prod(), duc_func],
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
# Host-side reference-only sanity checks (four gates before silicon dispatch).

def _pack_baseband(Ix_f, Qx_f):
    """Pack 512-pair baseband into a 4096-slot buffer (rest zero)."""
    iq = np.zeros(4096, dtype=np.float32)
    iq[0:1024:2] = Ix_f
    iq[1:1024:2] = Qx_f
    return iq.astype(bfloat16)


def _local_lo_lut_check():
    """Test 1: regenerate the LO LUT from the closed-form Analog Devices
    MT-085 formulae and diff against the baked LUT. LO frequency is
    positive (+f_s/8), so lo_sin has the opposite sign versus M21.
    """
    k = np.arange(N_LO)
    lo_cos_ideal = np.cos(+2.0 * np.pi * k / N_LO)
    lo_sin_ideal = np.sin(+2.0 * np.pi * k / N_LO)
    lo_cos_bf = np.array([float(bfloat16(v)) for v in lo_cos_ideal], dtype=np.float32)
    lo_sin_bf = np.array([float(bfloat16(v)) for v in lo_sin_ideal], dtype=np.float32)

    max_dc = float(np.max(np.abs(lo_cos_bf - _bf16_lo_cos())))
    max_ds = float(np.max(np.abs(lo_sin_bf - _bf16_lo_sin())))
    assert max_dc < 1e-6, f"LO cos regeneration mismatch: max diff {max_dc:.6e}"
    assert max_ds < 1e-6, f"LO sin regeneration mismatch: max diff {max_ds:.6e}"
    print(f"[reference] Test 1 LO LUT regeneration: PASS "
          f"(cos max_diff = {max_dc:.6e}, sin max_diff = {max_ds:.6e})")


def _local_impulse_check():
    """Test 2: baseband impulse at m=0.

    Ideal output is the interpolation LPF impulse response of length 16,
    with each output sample multiplied by LO[n & 7]. Since some LO slots
    are zero (cos_lo[2] = cos_lo[6] = 0, sin_lo[0] = sin_lo[4] = 0), the
    number of non-zero output *slots* (I or Q) is bounded by 16
    (one output sample per tap) but the number of non-zero complex
    samples depends on the LO pattern. Assert bounded structure.
    """
    Ix = np.zeros(512, dtype=np.float32)
    Qx = np.zeros(512, dtype=np.float32)
    Ix[0] = 1.0
    in_bf16 = _pack_baseband(Ix, Qx)

    ref = duc_reference(in_bf16).astype(np.float32)
    out_cplx = ref[0::2] + 1j * ref[1::2]
    nz = int(np.count_nonzero(np.abs(out_cplx) > 1e-6))
    # Expect the LPF impulse response is 16 taps long; some output slots
    # get zeroed by the LO but the vast majority survive.
    assert 8 <= nz <= 20, (
        f"Impulse response span out of expected band: {nz} non-zero output samples"
    )
    print(f"[reference] Test 2 impulse: PASS ({nz} non-zero output samples, "
          f"max |out| = {float(np.max(np.abs(out_cplx))):.6f})")


def _local_dc_to_tone_check():
    """Test 3: DC baseband input should upconvert to a pure tone at +f_s/8.

    Drive Ix[m] = 1, Qx[m] = 0 for m in [0, 512). After the polyphase
    LPF (unity DC gain end-to-end) and mix by LO(+f_s/8), the deep-tail
    output should be a complex sinusoid at +f_s/8 with unit magnitude.
    """
    Ix = np.ones(512, dtype=np.float32)
    Qx = np.zeros(512, dtype=np.float32)
    in_bf16 = _pack_baseband(Ix, Qx)

    ref = duc_reference(in_bf16).astype(np.float32)
    out_cplx = ref[0::2] + 1j * ref[1::2]
    # Deep tail after LPF has fully settled.
    tail = out_cplx[512:]
    mag = float(np.mean(np.abs(tail)))
    std = float(np.std(np.abs(tail)))

    # FFT to verify the peak lands at bin corresponding to +f_s/8.
    spec = np.fft.fft(tail) / len(tail)
    peak_bin = int(np.argmax(np.abs(spec)))
    expected_bin = len(tail) // 8  # = fs/8 in FFT bins

    assert 0.95 < mag < 1.05, (
        f"DC-to-tone magnitude out of band: {mag:.4f} (expected ~ 1.0)"
    )
    assert std < 0.02, f"DC-to-tone magnitude too unstable: std {std:.4f}"
    assert peak_bin == expected_bin, (
        f"DC-to-tone FFT peak at bin {peak_bin}, expected {expected_bin} "
        f"(= f_s/8 of the tail length)"
    )
    print(f"[reference] Test 3 DC -> +fs/8 tone: PASS "
          f"(mag = {mag:.4f}, std = {std:.4f}, peak_bin = {peak_bin}, "
          f"expected = {expected_bin})")


def _local_baseband_shift_check():
    """Test 4: baseband tone at -f_bb/8 should upconvert to +f_s/8 - f_s/32
              = +3 f_s/32.

    Drive x_bb[m] = e^{-j 2 pi m / 8}. In output samples (rate f_s = L*f_bb),
    the baseband tone lives at -f_s/32. After mixing by +f_s/8 it lands at
    +f_s/8 - f_s/32 = +3f_s/32. FFT peak of the tail should be at bin
    round(3/32 * tail_len).
    """
    n_bb = np.arange(512, dtype=np.float32)
    tone = np.exp(-1j * 2.0 * np.pi * n_bb / 8.0).astype(np.complex64)
    Ix = tone.real.astype(np.float32)
    Qx = tone.imag.astype(np.float32)
    in_bf16 = _pack_baseband(Ix, Qx)

    ref = duc_reference(in_bf16).astype(np.float32)
    out_cplx = ref[0::2] + 1j * ref[1::2]
    tail = out_cplx[512:]

    spec = np.fft.fft(tail) / len(tail)
    peak_bin = int(np.argmax(np.abs(spec)))
    peak_mag = float(np.abs(spec[peak_bin]))
    expected_bin = int(round(len(tail) * 3.0 / 32.0))

    # Tolerate +/- 1 bin because 512 baseband samples give a slightly
    # windowed peak but the argmax is stable.
    assert abs(peak_bin - expected_bin) <= 1, (
        f"Shift-to-+3fs/32 FFT peak at bin {peak_bin}, expected {expected_bin}"
    )
    assert peak_mag > 0.90, (
        f"Shift-to-+3fs/32 peak magnitude too weak: {peak_mag:.4f}"
    )
    print(f"[reference] Test 4 -f_bb/8 -> +3f_s/32: PASS "
          f"(peak_bin = {peak_bin}, expected = {expected_bin}, "
          f"mag = {peak_mag:.4f})")


def _run_local_reference_checks():
    print("Running host-side reference checks before silicon dispatch...")
    _local_lo_lut_check()
    _local_impulse_check()
    _local_dc_to_tone_check()
    _local_baseband_shift_check()


def main():
    print("=== Phoenix SDR-DSP Milestone 22: DUC (Interp + LPF + Mix) Silicon Execution ===")
    data_size = 4096  # 512 baseband pairs in (first 1024 slots), 2048 IF pairs out
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(
        f"Vector Length: {data_size} elements "
        f"(512 baseband pairs in, 2048 IF pairs out) of {element_type.__name__}"
    )
    print(f"DUC: interp L = {L} (Kaiser*L LPF), f_c = +f_s/8 (8-sample LO LUT)")

    _run_local_reference_checks()

    # --- Silicon PASS gate: random baseband I/Q vector.
    np.random.seed(792)
    Ix = np.random.uniform(-1.0, 1.0, 512).astype(np.float32)
    Qx = np.random.uniform(-1.0, 1.0, 512).astype(np.float32)
    np_in_bf16 = _pack_baseband(Ix, Qx)
    np_out_iq = np.zeros(data_size, dtype=element_type)

    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_iq, dtype=element_type)

    print("Compiling fused DUC (interp + LPF + mix) with Peano and dispatching to Phoenix NPU...")
    res = duc_upconvert(in_tensor, out_tensor, N=data_size, element_type=element_type)
    print(f"Kernel execution result: {res}")

    out_tensor.to("cpu")

    print("Execution complete. Inspecting DUC output vs reference...")

    ref_out_bf16 = duc_reference(np_in_bf16)
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
        fail_msg="DUC output mismatch",
        atol=0.01,
    )
    print(
        "SUCCESS: Phoenix NPU executed fused DUC "
        "(Interp L=4 + Kaiser*L LPF + Mix +f_s/8) on physical silicon!"
    )
    print("PASS!")


if __name__ == "__main__":
    main()
