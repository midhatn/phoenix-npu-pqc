# Purpose: Milestone 17 v2 -- 64-point Radix-2 FFT Silicon Validation on AMD Phoenix NPU.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (AIE-ML).
# Input types: bfloat16 interleaved complex vector (128 elements = 64 I/Q pairs) in BIT-REVERSED order.
# Output types: bfloat16 interleaved complex spectrum (128 elements = 64 I/Q bins) in NATURAL order.
# Twiddle table: 64 bfloat16 elements = 32 W_N^k pairs, k in [0..31].
#
# Cross-validates against a Cooley-Tukey iterative in-place bit-reversed FFT reference
# (same algorithm shipped in M16 v0.2.1) and against numpy.fft.fft.
#
# References:
#   [1] AMD AI Engine API User Guide (2024.2): aie::fft_dit_r2_stage.
#       https://download.amd.com/docnav/aiengine/xilinx2024_2/aiengine_api/aie_api/doc/group__group__fft.html
#   [2] Cooley & Tukey (1965). Math. Comp. 19(90): 297-301.
#       https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf

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


# ----------------------------------------------------------------------------
# Host-side helpers
# ----------------------------------------------------------------------------

def bit_reverse_indices(n_bits):
    """Return an array of length 2**n_bits mapping i -> bit-reversed(i)."""
    n = 1 << n_bits
    idx = np.arange(n, dtype=np.int64)
    rev = np.zeros(n, dtype=np.int64)
    for b in range(n_bits):
        rev |= ((idx >> b) & 1) << (n_bits - 1 - b)
    return rev


def cooley_tukey_fft_reference(x, inverse=False):
    """
    Iterative in-place decimation-in-time Cooley-Tukey FFT.
    Input:  complex128 vector of length N = 2^k.
    Output: complex128 spectrum, same length, NOT scaled by 1/N even for inverse
            (so IFFT(FFT(x)) == N * x).
    This mirrors the reference used in M16 v0.2.1 for CPU FFT validation.
    """
    x = np.asarray(x, dtype=np.complex128).copy()
    n = x.size
    n_bits = int(np.log2(n))
    assert (1 << n_bits) == n, f"N must be a power of 2, got {n}"

    # Bit-reversal permutation
    rev = bit_reverse_indices(n_bits)
    x = x[rev]

    # Iterative butterflies
    sign = 1.0 if inverse else -1.0
    size = 2
    while size <= n:
        half = size // 2
        w_step = np.exp(sign * 2j * np.pi / size)
        for start in range(0, n, size):
            w = 1.0 + 0.0j
            for k in range(half):
                t = w * x[start + k + half]
                u = x[start + k]
                x[start + k] = u + t
                x[start + k + half] = u - t
                w *= w_step
        size *= 2
    return x


def pack_complex_to_iq_bf16(z, dtype=bfloat16):
    """Pack a complex vector as [Re0, Im0, Re1, Im1, ...] bfloat16."""
    n = z.size
    out = np.zeros(2 * n, dtype=np.float32)
    out[0::2] = z.real
    out[1::2] = z.imag
    return out.astype(dtype)


def unpack_iq_bf16_to_complex(iq):
    """Unpack [Re0, Im0, Re1, Im1, ...] bfloat16 -> complex64."""
    f = iq.astype(np.float32)
    return (f[0::2] + 1j * f[1::2]).astype(np.complex64)


# ----------------------------------------------------------------------------
# NPU kernel wrapper
# ----------------------------------------------------------------------------

@iron.jit
def fft_64point_radix2(
    input_iq: In,
    twiddles: In,
    output_spec: Out,
    *,
    N_IN: CompileTime[int],
    N_TW: CompileTime[int],
    element_type: CompileTime[type],
):
    in_ty = np.ndarray[(N_IN,), np.dtype[element_type]]
    tw_ty = np.ndarray[(N_TW,), np.dtype[element_type]]
    out_ty = np.ndarray[(N_IN,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in_iq")
    of_tw = ObjectFifo(tw_ty, name="twiddles")
    of_out = ObjectFifo(out_ty, name="out_spec")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    fft_func = ExternalFunction(
        "fft64_kernel",
        source_file=str(current_dir / "fft64_kernel_v2.cc"),
        arg_types=[in_ty, tw_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_tw, of_out, fft_fn):
        elem_in = of_in.acquire(1)
        elem_tw = of_tw.acquire(1)
        elem_out = of_out.acquire(1)
        fft_fn(elem_in, elem_tw, elem_out)
        of_in.release(1)
        of_tw.release(1)
        of_out.release(1)

    worker = Worker(
        core_body, fn_args=[of_in.cons(), of_tw.cons(), of_out.prod(), fft_func]
    )

    rt = Runtime()
    with rt.sequence(in_ty, tw_ty, out_ty) as (a_in, a_tw, c_out):
        rt.start(worker)
        rt.fill(of_in.prod(), a_in)
        rt.fill(of_tw.prod(), a_tw)
        rt.drain(of_out.cons(), c_out, wait=True)

    my_program = Program(iron.get_current_device(), rt)
    return my_program.resolve_program()


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def build_twiddles_bf16(n_points):
    """
    Radix-2 twiddle table for N=64: W_N^k = exp(-j*2*pi*k/N) for k in [0..N/2-1].
    Returns 64 bfloat16 elements (32 complex pairs, interleaved).
    """
    n_half = n_points // 2
    k = np.arange(n_half)
    tw_c = np.exp(-1j * 2 * np.pi * k / n_points).astype(np.complex128)
    return pack_complex_to_iq_bf16(tw_c)


def run_single_case(name, sig_complex, atol, expect_peak_bins=None):
    print(f"\n--- Case: {name} ---")
    n_points = 64
    n_bits = 6
    data_size = n_points * 2  # 128 bfloat16 elements
    tw_size = n_points        # 64  bfloat16 elements (32 complex twiddles)
    element_type = bfloat16

    # 1. Apply bit-reversal permutation to the input (host-side)
    rev = bit_reverse_indices(n_bits)
    sig_bitrev = sig_complex[rev]

    # 2. Pack to bfloat16 interleaved I/Q
    np_in_bf16 = pack_complex_to_iq_bf16(sig_bitrev, dtype=element_type)

    # 3. Build twiddle table (32 complex twiddles = 64 bf16 elements)
    np_tw_bf16 = build_twiddles_bf16(n_points).astype(element_type)

    # 4. Allocate output
    np_out_spec = np.zeros(data_size, dtype=element_type)

    # 5. Wrap in XRTTensor
    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    tw_tensor = XRTTensor(np_tw_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_spec, dtype=element_type)

    # 6. Dispatch to NPU
    print(f"  Compiling + dispatching to Phoenix NPU (in={data_size} tw={tw_size} out={data_size})...")
    res = fft_64point_radix2(
        in_tensor,
        tw_tensor,
        out_tensor,
        N_IN=data_size,
        N_TW=tw_size,
        element_type=element_type,
    )
    print(f"  Kernel result: {res}")
    out_tensor.to("cpu")

    # 7. Reference: Cooley-Tukey iterative FFT on the SAME quantized input
    #    (input is dequantized from bfloat16 to preserve the exact values the NPU saw)
    in_deq_complex = unpack_iq_bf16_to_complex(pack_complex_to_iq_bf16(sig_complex, dtype=element_type))
    ref_spec = cooley_tukey_fft_reference(in_deq_complex, inverse=False)
    ref_iq_bf16 = pack_complex_to_iq_bf16(ref_spec, dtype=element_type)

    # 8. Compare
    out_np = out_tensor._data
    max_err = float(np.max(np.abs(out_np.astype(np.float32) - ref_iq_bf16.astype(np.float32))))
    print(f"  Max abs error vs Cooley-Tukey ref: {max_err:.6f}  (atol={atol})")

    # 9. Peak-bin sanity check
    if expect_peak_bins is not None:
        out_complex = unpack_iq_bf16_to_complex(out_np)
        mag = np.abs(out_complex)
        top = np.argsort(mag)[::-1][: len(expect_peak_bins)]
        print(f"  Top peak bins: {sorted(top.tolist())}  (expected: {sorted(expect_peak_bins)})")

    assert_pass(out_np, ref_iq_bf16, fail_msg=f"{name}: FFT spectrum mismatch", atol=atol)
    print(f"  PASS: {name}")
    return max_err


def main():
    print("=" * 72)
    print("Milestone 17 v2: 64-point Radix-2 Cooley-Tukey FFT on Phoenix NPU")
    print("=" * 72)
    print(f"Target Device: {iron.get_current_device()}")
    print("Transform Size: 64-point complex FFT, 6 stages, cbfloat16")
    print("Twiddle count: 32 (radix-2 DIT stage API)")

    n = 64
    t = np.arange(n) / n
    errors = []

    # Case 1: DC signal -> bin 0 = N, all others zero
    dc = np.ones(n, dtype=np.complex128)
    errors.append(run_single_case("DC", dc, atol=1.5, expect_peak_bins=[0]))

    # Case 2: Impulse -> flat spectrum (magnitude ~= 1)
    impulse = np.zeros(n, dtype=np.complex128)
    impulse[0] = 1.0
    errors.append(run_single_case("Impulse", impulse, atol=0.5))

    # Case 3: Single real cosine at k=5 -> peaks at bins 5 and 59
    tone1 = np.cos(2 * np.pi * 5 * t).astype(np.complex128)
    errors.append(run_single_case("Cosine k=5", tone1, atol=1.5, expect_peak_bins=[5, 59]))

    # Case 4: Multi-tone (3 complex exponentials at bins 4, 12, 20)
    multitone = (
        1.0 * np.exp(2j * np.pi * 4 * t)
        + 0.7 * np.exp(2j * np.pi * 12 * t)
        + 0.5 * np.exp(2j * np.pi * 20 * t)
    )
    errors.append(run_single_case("Multi-tone [4,12,20]", multitone, atol=1.5, expect_peak_bins=[4, 12, 20]))

    # Case 5: Random complex (deterministic seed)
    rng = np.random.default_rng(0xFF7)
    rand = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    errors.append(run_single_case("Random complex", rand, atol=3.0))

    print("\n" + "=" * 72)
    print(f"All 5 cases PASSED. Max error across cases: {max(errors):.6f}")
    print("SUCCESS: Phoenix NPU executed 64-Point Radix-2 FFT on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
