# Purpose: Milestone 24 Barker-13 Matched-Filter Correlator Silicon Validation
#          on AMD Phoenix NPU. Fused sliding correlator (L = 13 real taps
#          on I and Q independently) on one AIE2 core.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 interleaved complex I/Q (4096 slots = 2048 pairs).
# Output types: bfloat16 interleaved correlator I/Q (4096 slots = 2048 pairs).
#              Peak |y| = 13 on aligned Barker-13 patterns.
# Scaling: Direct bfloat16 operand load, float32 multiply-accumulate,
#          single bfloat16 truncation on final store.
# Alignment assumptions: handled by IRON XRTTensor / BO runtime.
# State requirements: device 0 (NPU Phoenix).
# Error handling: atol = 0.05 on random silicon gate (13 bf16 MAC roundings
#                 accumulated; taps are +/-1 so |y_k| <= 1 per MAC).
#
# Design: docs/M24_DESIGN.md
# Host API pin: mlir-aie v1.4.1 iron.Runtime sequence-function API.
#
# Signal-chain math (Proakis-Salehi Digital Comms 5e sec 5.1.5; GNU Radio
# corr_est_cc):
#     y[n] = sum_{k=0..L-1} conj(s[k]) * x[n+k]
# Barker-13 preamble s = (+1,+1,+1,+1,+1,-1,-1,+1,+1,-1,+1,-1,+1). Because
# s is real-valued, conj(s) = s and the complex correlator splits into two
# independent real FIRs on I and Q.
#
# Correlator-as-reverse-FIR identity (Oppenheim-Schafer DTSP 3e sec 2.6.2):
#     y_corr[n] = sum s[k] * x[n+k] == (h * x)[n + (L-1)], h[k] = s[L-1-k]
# so the kernel uses the M8/M19 shift-and-ingest schedule with taps stored
# in reversed Barker-13 order:
#     s_rev = (+1,-1,+1,-1,+1,+1,-1,-1,+1,+1,+1,+1,+1)
#
# References:
#   * Wikipedia "Barker code" (definition, autocorrelation, PSL bound):
#     https://en.wikipedia.org/wiki/Barker_code
#   * Barker 1953 original synchronization paper:
#     https://ieeexplore.ieee.org/document/6773685
#   * GNU Radio Correlation Estimator (matched-filter correlator block):
#     https://wiki.gnuradio.org/index.php/Correlation_Estimator
#   * GNU Radio corr_est_cc C++ header:
#     https://www.gnuradio.org/doc/doxygen-v3.7.10/corr__est__cc_8h_source.html
#   * liquid-dsp detector_cccf (streaming complex preamble detector):
#     https://liquidsdr.org/doc/detector/
#   * numpy.correlate (host reference for aperiodic cross-correlation):
#     https://numpy.org/doc/stable/reference/generated/numpy.correlate.html
#   * scipy.signal.correlate:
#     https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html

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
# Constants. Barker-13 preamble in canonical order.
L = 13
BARKER13 = np.array(
    [+1, +1, +1, +1, +1, -1, -1, +1, +1, -1, +1, -1, +1],
    dtype=np.float32,
)
# Reversed for the shift-and-ingest FIR convention (hist[L-1] pairs with s_rev[0]).
BARKER13_REV = BARKER13[::-1].copy()
# Sum used by Test 2 (DC-input sanity gate); sum(Barker-13) = +5.
BARKER_SUM = float(BARKER13.sum())


# ------------------------------------------------------------------
# Host reference. Walks the SAME shift-and-ingest schedule as
# correlator_kernel.cc so silicon and host produce term-for-term
# matching output including the L-1 = 12 leading transient samples.

def correlator_reference(in_bf16):
    """Bit-accurate NumPy transliteration of correlator_kernel.cc."""
    x = in_bf16.astype(np.float32)
    Ix = x[0::2]
    Qx = x[1::2]
    N = len(Ix)

    hist_i = np.zeros(L, dtype=np.float32)
    hist_q = np.zeros(L, dtype=np.float32)
    Iy = np.zeros(N, dtype=np.float32)
    Qy = np.zeros(N, dtype=np.float32)

    for i in range(N):
        # Shift left by one, ingest at slot 12.
        hist_i[:L - 1] = hist_i[1:L]
        hist_i[L - 1] = Ix[i]
        hist_q[:L - 1] = hist_q[1:L]
        hist_q[L - 1] = Qx[i]

        # y = sum_{k=0..L-1} hist[L-1-k] * s[k] (canonical Barker order),
        # equivalent to y = sum s_rev[k] * hist[L-1-k] with reversed taps.
        # Force each MAC through float32 to match the natural left-to-right
        # accumulation the compiler emits from the .cc.
        Ia = np.float32(0.0)
        Qa = np.float32(0.0)
        for k in range(L):
            # hist[L-1-k] pairs with s_rev[k] = BARKER13[L-1-k] = BARKER13_REV[k]
            Ia = Ia + np.float32(hist_i[L - 1 - k] * BARKER13_REV[k])
            Qa = Qa + np.float32(hist_q[L - 1 - k] * BARKER13_REV[k])

        Iy[i] = Ia
        Qy[i] = Qa

    out = np.zeros(2 * N, dtype=np.float32)
    out[0::2] = Iy
    out[1::2] = Qy
    return out.astype(bfloat16)


# ------------------------------------------------------------------
# IRON JIT plumbing (identical topology to M22/M23). The @iron.jit
# decorator plus In/Out/CompileTime annotations are what tell IRON to
# actually compile + dispatch to silicon; without them resolve_program()
# returns MLIR text only and the NPU is never invoked (the M24 kernel
# was silently a no-op through the first three bring-up attempts).

@iron.jit
def correlator_program(
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
        "correlator_kernel",
        source_file=str(current_dir / "correlator_kernel.cc"),
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_out, ch_func):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        ch_func(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    # Stack footprint: hist_i, hist_q (13*4 = 52 bytes each). ~ 250 bytes,
    # well under the 16 KB override reused from M19/M22/M23.
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
# Host-side sanity gates. Each walks the reference to produce silicon-
# matching output; assertions run on the reference stream.

def _pack_iq(Ix_f, Qx_f):
    """Pack 2048-pair complex I/Q into a 4096-slot interleaved buffer."""
    iq = np.zeros(4096, dtype=np.float32)
    iq[0::2] = Ix_f
    iq[1::2] = Qx_f
    return iq.astype(bfloat16)


def _local_preamble_alignment_check():
    """Test 1: aligned Barker-13 pattern produces peak |y| = 13.

    Drive x[n] = 0 everywhere except x[100..112] = Barker-13 (I only).
    Correlator with reversed-tap FIR schedule outputs y[i] with peak at
    i = 100 + (L-1) = 112 (group delay of the reversed FIR).
    """
    Ix = np.zeros(2048, dtype=np.float32)
    Qx = np.zeros(2048, dtype=np.float32)
    offset = 100
    Ix[offset:offset + L] = BARKER13
    x = _pack_iq(Ix, Qx)
    y = correlator_reference(x).astype(np.float32)
    Iy = y[0::2]
    Qy = y[1::2]
    mag = np.sqrt(Iy * Iy + Qy * Qy)
    peak_idx = int(np.argmax(mag))
    peak_val = float(mag[peak_idx])
    # Group delay of the reversed FIR is L-1 = 12 samples.
    expected_peak = offset + L - 1
    assert peak_idx == expected_peak, (
        f"peak at sample {peak_idx}, expected {expected_peak}"
    )
    assert 12.5 < peak_val <= 13.05, (
        f"peak magnitude out of band: {peak_val:.3f}, expected ~13.0"
    )
    # Sidelobe magnitudes should be small (Barker-13 |c_v| <= 1 for v != 0;
    # the actual peak-vs-sidelobe ratio on the reversed-FIR stream still holds).
    others_max = float(np.max(np.delete(mag, peak_idx)))
    assert others_max <= 2.0, f"sidelobe too tall: {others_max:.3f}"
    print(
        f"[reference] Test 1 aligned Barker-13: PASS "
        f"(peak = {peak_val:.3f} at sample {peak_idx}, "
        f"max sidelobe = {others_max:.3f})"
    )


def _local_dc_check():
    """Test 2: DC input produces I steady-state = sum(Barker-13) = +5.

    Drive x[n] = 1 + 0j. Once shift registers are full (i >= L-1) the
    I-channel output settles at 5.0 and the Q-channel stays at 0.
    """
    Ix = np.ones(2048, dtype=np.float32)
    Qx = np.zeros(2048, dtype=np.float32)
    x = _pack_iq(Ix, Qx)
    y = correlator_reference(x).astype(np.float32)
    Iy = y[0::2]
    Qy = y[1::2]
    steady_I = float(np.mean(Iy[L:]))
    steady_Q = float(np.max(np.abs(Qy[L:])))
    assert abs(steady_I - BARKER_SUM) < 0.1, (
        f"DC I steady state {steady_I:.3f}, expected {BARKER_SUM}"
    )
    assert steady_Q < 0.1, f"DC Q leak too large: {steady_Q:.3f}"
    print(
        f"[reference] Test 2 DC input: PASS "
        f"(Iy steady = {steady_I:.3f}, max |Qy| = {steady_Q:.3f})"
    )


def _local_rotated_preamble_check():
    """Test 3: Barker-13 rotated by exp(j pi/4) preserves phase.

    Drive x[offset..offset+L] = Barker-13 * exp(j pi/4), zeros elsewhere.
    Correlator peak sits at offset + L - 1 with |y| = 13 and arg(y) = pi/4.
    """
    Ix = np.zeros(2048, dtype=np.float32)
    Qx = np.zeros(2048, dtype=np.float32)
    offset = 200
    phase = np.pi / 4.0
    rot = np.exp(1j * phase)
    preamble_c = BARKER13.astype(np.complex64) * rot
    Ix[offset:offset + L] = preamble_c.real.astype(np.float32)
    Qx[offset:offset + L] = preamble_c.imag.astype(np.float32)
    x = _pack_iq(Ix, Qx)
    y = correlator_reference(x).astype(np.float32)
    Iy = y[0::2]
    Qy = y[1::2]
    mag = np.sqrt(Iy * Iy + Qy * Qy)
    peak_idx = int(np.argmax(mag))
    expected_peak = offset + L - 1
    assert peak_idx == expected_peak, (
        f"rotated peak at {peak_idx}, expected {expected_peak}"
    )
    peak_val = float(mag[peak_idx])
    peak_phase = float(np.arctan2(Qy[peak_idx], Iy[peak_idx]))
    assert 12.5 < peak_val <= 13.05, (
        f"rotated peak magnitude out of band: {peak_val:.3f}"
    )
    assert abs(peak_phase - phase) < 0.05, (
        f"peak phase {peak_phase:.4f}, expected {phase:.4f}"
    )
    print(
        f"[reference] Test 3 rotated preamble (+45 deg): PASS "
        f"(peak = {peak_val:.3f}, phase = {peak_phase:.4f} rad)"
    )


def _local_negated_preamble_check():
    """Test 4: -Barker-13 produces peak Iy = -13 (sign fidelity)."""
    Ix = np.zeros(2048, dtype=np.float32)
    Qx = np.zeros(2048, dtype=np.float32)
    offset = 300
    Ix[offset:offset + L] = -BARKER13
    x = _pack_iq(Ix, Qx)
    y = correlator_reference(x).astype(np.float32)
    Iy = y[0::2]
    Qy = y[1::2]
    expected_peak = offset + L - 1
    peak_val = float(Iy[expected_peak])
    q_at_peak = float(Qy[expected_peak])
    assert -13.05 <= peak_val < -12.5, (
        f"negated peak Iy = {peak_val:.3f}, expected ~ -13.0"
    )
    assert abs(q_at_peak) < 0.1, (
        f"negated peak Qy leak: {q_at_peak:.3f}"
    )
    print(
        f"[reference] Test 4 negated preamble: PASS "
        f"(Iy at sample {expected_peak} = {peak_val:.3f}, "
        f"|Qy| = {abs(q_at_peak):.3f})"
    )


def _run_local_reference_checks():
    print("Running host-side reference checks before silicon dispatch...")
    _local_preamble_alignment_check()
    _local_dc_check()
    _local_rotated_preamble_check()
    _local_negated_preamble_check()


def main():
    print("=== Phoenix SDR-DSP Milestone 24: Barker-13 Matched-Filter Correlator Silicon Execution ===")
    data_size = 4096  # 2048 complex I/Q pairs in / 2048 correlator pairs out
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(
        f"Vector Length: {data_size} elements "
        f"(2048 complex I/Q pairs in, 2048 correlator I/Q pairs out) "
        f"of {element_type.__name__}"
    )
    print(f"Correlator: L = {L} taps, preamble = Barker-13")

    _run_local_reference_checks()

    # --- Silicon PASS gate: random wideband I/Q vector.
    np.random.seed(794)
    Ix = np.random.uniform(-1.0, 1.0, 2048).astype(np.float32)
    Qx = np.random.uniform(-1.0, 1.0, 2048).astype(np.float32)
    np_in_bf16 = _pack_iq(Ix, Qx)
    np_out_iq = np.zeros(data_size, dtype=element_type)

    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_iq, dtype=element_type)

    print("Compiling fused Barker-13 correlator with Peano and dispatching to Phoenix NPU...")
    res = correlator_program(in_tensor, out_tensor, N=data_size, element_type=element_type)
    print(f"Kernel execution result: {res}")

    out_tensor.to("cpu")

    print("Execution complete. Inspecting correlator output vs reference...")

    ref_out_bf16 = correlator_reference(np_in_bf16)
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
        fail_msg="Correlator output mismatch",
        atol=0.05,
    )
    print(
        "SUCCESS: Phoenix NPU executed fused Barker-13 matched-filter correlator "
        f"(L = {L}) on physical silicon!"
    )
    print("PASS!")


if __name__ == "__main__":
    main()
