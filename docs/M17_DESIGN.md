# M17: NPU 64-point Radix-2 FFT/IFFT -- Design Document

**Status:** Design phase (kernel + host driver ready; silicon verification pending)
**Supersedes:** `tests/m17_fft_dft/` (O(N^2) direct-DFT -- will be retired after M17 v2 is silicon-verified)
**Target:** AMD Ryzen 9 7940HS Phoenix NPU1 / XDNA1 / AIE-ML (AIE2)
**Toolchain:** IRON v1.4.1, mlir-aie 2024.2

---

## 1. Problem Statement

Milestone 17 in the Phoenix-SDR-DSP master prompt requires "NPU FFT and IFFT."
The prior implementation (`tests/m17_fft_dft/fft64_kernel.cc`) was a scalar
O(N^2) direct DFT computing 4096 complex multiplies per 64-point frame.
This design replaces it with an O(N log N) Cooley-Tukey radix-2 FFT computing
192 complex multiplies per 64-point frame -- a **21x reduction in arithmetic
work** -- using AMD's native `aie::fft_dit_r2_stage` API (Ref [1], [2]).

## 2. Algorithm

Standard 6-stage **decimation-in-time (DIT) radix-2** Cooley-Tukey FFT
(Ref [3]) for N=64:

| Stage | Vectorization | Butterflies |
|-------|---------------|-------------|
| 0     | 32            | 32          |
| 1     | 16            | 32          |
| 2     | 8             | 32          |
| 3     | 4             | 32          |
| 4     | 2             | 32          |
| 5     | 1             | 32          |

- **6 stages** (`log2(64) = 6`)
- **32 butterflies per stage** = 192 total complex multiply-adds per frame
- Input in **bit-reversed order**, output in **natural order**
  (host applies the bit-reversal permutation before submitting the frame)
- **Same kernel binary** handles FFT and IFFT via the `inv` parameter

## 3. Data Types

- **Sample & bin type:** `cbfloat16` -- `struct { bfloat16 real, imag; }`
  (per `aie_api/types.hpp:114`, 4 bytes each, 32-bit aligned)
- **Twiddle type:** `cbfloat16` (defaulted by `detail::default_twiddle_type_t` for
  floating-point inputs)
- **ABI on the host boundary:** `bfloat16*` interleaved I/Q arrays -- identical
  memory layout to `cbfloat16*` because `cbfloat16` is a POD `{bfloat16 real, imag;}`.
  The kernel reinterprets the incoming pointers, so the Python host side is
  unchanged from M11/M17 v1 conventions.
- **Total memory footprint per frame:**
  - Input: 64 * 4B = 256 B
  - Output: 64 * 4B = 256 B
  - Twiddles: 32 * 4B = 128 B
  - Two ping-pong scratch buffers: 2 * 64 * 4B = 512 B
  - **Total: 1,152 B** -- well under the 64 KB AIE-ML tile memory

## 4. API Overload Used

From `aie_api/fft.hpp:262-279` (verified locally in
`third_party/mlir-aie/ironenv/Lib/site-packages/mlir_aie/include/`):

```cpp
template <unsigned Vectorization, typename Input, typename Output, typename Twiddle>
    requires(arch::is(arch::AIE, arch::AIE_ML, arch::AIE_MLv2) &&
             detail::is_floating_point_v<Input>)
void fft_dit_r2_stage(const Input * __restrict x,
                      const Twiddle * __restrict tw,
                      unsigned n, bool inv, Output * __restrict out);
```

- **`arch::AIE_ML` = Phoenix XDNA1** -- this overload is enabled on target hardware
- **Float overload:** no `shift_tw` or `shift` parameters (unlike integer overloads)
- **`is_valid_fft_op_v<2, cbfloat16, cbfloat16, cbfloat16>`** must resolve `true`
  at compile time -- if it does not, `static_assert` fires and the build fails
  cleanly.

## 5. Twiddle Factors

The kernel expects a precomputed twiddle table of length `N/2 = 32` `cbfloat16`
values, laid out as:

```
tw[k] = exp(-j * 2 * pi * k / N) = cos(2*pi*k/N) - j*sin(2*pi*k/N)   for k in [0..31]
```

Generated on the host in float64 -> converted to bfloat16 -> packed as
interleaved (real, imag) pairs. IFFT reuses the same twiddle table; the
`inv=true` flag inside the kernel handles sign inversion internally.

## 6. Host Driver Responsibilities

1. Generate a 64-sample complex input (test signal)
2. Apply the bit-reversal permutation: `out[i] = in[bit_reverse(i, 6)]`
3. Convert float32 -> bfloat16, pack as `(real, imag)` pairs
4. Precompute and pack the 32 twiddles
5. Compile and load the kernel via mlir-aie / IRON
6. DMA input + twiddles onto the NPU, launch kernel, DMA output back
7. Cross-validate against a Cooley-Tukey iterative in-place reference (same
   algorithm shipped in M16 v0.2.1). Expected error: <= 1 ULP of bfloat16 per
   stage, compounded across 6 stages -> maximum expected relative error ~ 2^-4
   per bin in worst case, ~ 2^-7 typical. Absolute tolerance in the test suite
   is set case-by-case (`atol` in the range 0.5 -- 3.0 depending on signal energy).

## 7. Validation Plan

| Test | Signal | Expected Result |
|------|--------|-----------------|
| DC   | x[n] = 1 for all n | Spectrum has bin 0 ~= 64, all other bins ~= 0 |
| Impulse | x[0] = 1, x[n != 0] = 0 | All bins ~= 1 in magnitude, phase varies |
| Single tone | x[n] = cos(2*pi * 5 * n / 64) | Bins 5 and 59 dominate, rest ~= 0 |
| Multi-tone | 3 exponentials at k = 4, 12, 20 | Peaks at 4, 12, 20 |
| Random complex | Uniform noise, seed 0xFF7 | Bit-accurate match vs Cooley-Tukey ref |

Once forward FFT is silicon-green, add:

- **IFFT variant:** identical kernel, `inv=true`. Divide result by N on host.
- **Round-trip test:** `IFFT(FFT(x)) == x` within 2^-6 relative.

## 8. Retirement of Direct-DFT

Once M17 v2 is silicon-verified:

- `tests/m17_fft_dft/` becomes a historical reference -- its README will point
  to `tests/m17_radix2_fft/` as the current milestone.
- `run_all_silicon_tests.py` swaps entry `M17` from `m17_fft_dft` to
  `m17_radix2_fft`.
- The direct-DFT stays in git history and remains useful as a slow-but-correct
  reference oracle for future FFT tests.

## References

[1] AMD AI Engine API User Guide (2024.2), Section: FFT.
    https://download.amd.com/docnav/aiengine/xilinx2024_2/aiengine_api/aie_api/doc/group__group__fft.html

[2] AMD UG1603 -- AI Engine ML Kernel Coding: Floating-Point Operations.
    https://docs.amd.com/r/en-US/ug1603-ai-engine-ml-kernel-graph/Floating-Point-Operations

[3] Cooley, J. W. & Tukey, J. W. (1965). "An algorithm for the machine
    calculation of complex Fourier series." Mathematics of Computation,
    19(90): 297-301.
    https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf

[4] Xilinx aie_api Changelog (upstream API reference).
    https://github.com/Xilinx/aie_api/blob/main/Changelog.hpp

[5] IRON documentation v1.4.1 -- Xilinx mlir-aie.
    https://xilinx.github.io/mlir-aie/1.4.1/
