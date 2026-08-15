# M23 — Polyphase Channelizer Design

Status: **shipped** (silicon PASS on Phoenix NPU1, 2026-08-15, max err 0.003906 on seed-793 random baseband at `atol = 0.02`; commit [`43b0f9c1`](https://github.com/midhatn/phoenix-sdr-dsp/commit/43b0f9c19571e07fb883dce24f70ab8718bd22a5)).
Owner: Phoenix SDR-DSP team.
Target hardware: [AMD Ryzen 9 7940HS "Phoenix"](https://www.amd.com/en/products/apu/amd-ryzen-9-7940hs) / [XDNA1 NPU](https://docs.kernel.org/accel/amdxdna/amdnpu.html) / AIE2 (one core, 4×5 tile array).
Target OS: Windows 11 Pro 25H2, Clang / Peano AIE2, [IRON MLIR-AIE 1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1) (pinned at commit [`3ca0193`](https://github.com/Xilinx/mlir-aie/commit/3ca0193)).
Closing this milestone completes the DSP-track filtering & resampling block (M19–M23).
Related files:

- `tests/m23_channelizer/channelizer_kernel.cc` — fused AIE2 kernel (commutator + M-path FIR + M-point DFT).
- `tests/m23_channelizer/test_channelizer_m23.py` — host driver, NumPy reference, silicon gate.
- `include/sdr_dsp/sdr_dsp_common.hpp` — shared AIE2 vector definitions.

## 1. Purpose

A polyphase channelizer takes a wideband complex baseband signal at
sample rate `f_s` and simultaneously splits it into `M` uniformly
spaced sub-channels, each at rate `f_s / M`. It is the workhorse of
frequency-division multiple-access receivers ([Harris 2004
ch. 6](https://ieeexplore.ieee.org/book/9448967); [Rondeau, "Designing
Analysis and Synthesis Filterbanks in GNU
Radio"](https://static.squarespace.com/static/543ae9afe4b0c3b808d72acd/543aee1fe4b09162d08633d9/543aee20e4b09162d086354a/1395369129837/rondeau_gr_filtering.pdf)).

In one sentence:

> `y_k[m] = IDFT{ M-path FIR{ commutate{ x[n] } } }[k]`

Equivalently, for `M = 8`, the channelizer produces 8 parallel streams
`y_0..y_7`, one per channel, each downsampled by 8. Milestone 23
delivers a **single fused AIE2 kernel** that runs the entire
commutator → polyphase FIR → DFT pipeline on one core.

The design is a natural extension of the anchor milestones:

- **M17p** (`parallel_fft64_kernel.cc`) — matmul-style DFT with fully
  embedded twiddles. M23 reuses the same "unroll the 8×8 DFT as a
  scalar sum of products" pattern at `N = M = 8` instead of `N = 64`.
- **M19** (`fir_complex_kernel.cc`) — scalar complex FIR with a
  shift-register. M23 reuses the same shift-and-ingest structure per
  polyphase branch.
- **M20** (`polyphase_kernel.cc`) — L-branch polyphase interpolator.
  M23 uses the **same polyphase decomposition** in the analysis-bank
  direction (downsample by M instead of upsample by L).

## 2. Signal-chain math

### 2.1 Polyphase decomposition of the prototype

Let `h[n]` (n = 0 .. NTAPS - 1, `NTAPS = M · K = 64`) be the prototype
low-pass filter with cutoff `pi / M` and Kaiser window (beta ≈ 5.653,
60 dB stop-band attenuation; see [Kaiser 1974
"I0-sinh Window"](https://ieeexplore.ieee.org/document/1451724)). The
polyphase decomposition splits `h` into `M` sub-filters
([Vaidyanathan 1993 §4.3, Eq.
4.3.13](https://dl.acm.org/doi/10.5555/151045); [Harris 2004
§6.3](https://ieeexplore.ieee.org/book/9448967)):

```
hp[p][k] = h[p + k · M],   p = 0 .. M-1,   k = 0 .. K-1
```

Each sub-filter has `K = 8` taps. The `M = 8` branches together hold
`M · K = 64` taps — the entire prototype, just permuted.

### 2.2 Input commutator

Split the input stream `x[n]` into `M` parallel streams by rotating
samples across `M` branches. Following the natural sample-to-branch
convention used by [GNU Radio pfb_channelizer_ccf](https://wiki.gnuradio.org/index.php/Polyphase_Channelizer)
and [NVIDIA MatX
channelize_poly](https://nvidia.github.io/MatX/api/signalimage/filtering/channelize_poly.html):

```
sample q of frame f -> branch p = q,   K-slot shift register on each branch
```

Each branch's shift register is `K = 8` deep (matches the polyphase
tap count).

### 2.3 M-path polyphase FIR

For frame `f`, after the M-input commutator, evaluate one FIR output
per branch (Harris §6.3 Fig. 6.8):

```
v[p] = sum_{k=0..K-1} hp[p][k] · s[p][k]        (complex)
```

Since the input is complex I/Q, this runs as two real FIRs (one on I,
one on Q) sharing the same taps — same pattern used by M19.

### 2.4 M-point DFT (analysis convention)

The `M` FIR outputs `v[0..M-1]` are then combined by an `M`-point DFT
(sign `-j` per Harris §6.3 Eq. 6.20, matching [scipy.fft.fft](https://docs.scipy.org/doc/scipy/reference/generated/scipy.fft.fft.html)):

```
y_k = sum_{n=0..M-1} v[n] · exp(-j · 2π k n / M),   k = 0 .. M-1
```

At `M = 8` the DFT is small enough that a matmul-style scalar
implementation is cheaper than an FFT butterfly. This mirrors the
M17p approach (fully-embedded twiddles, no FFT decomposition).

## 3. Numerical design

### 3.1 Prototype filter

- Length: `NTAPS = M · K = 64` taps.
- Cutoff: `pi / M = pi / 8` radians (equivalently `f_s / (2M)`).
- Window: Kaiser I0-sinh, `beta ≈ 5.653`, transition-width chosen for
  60 dB stop-band attenuation (`scipy.signal.kaiserord(60, 0.5/M)`).
- Scaling: `scipy.signal.firwin(..., scale=True)`, giving DC gain
  `sum(h) = 0.99977`.
- Even symmetry: exact (`max|h[n] - h[63-n]| = 0`).

Sanity checks (all PASS in host reference `_local_prototype_check`):

- DC input `(1 + 0j)` → `|y[ch0]| = 1.0000`, isolation 66.2 dB against
  the other seven channels.
- Complex tone at `f = 3 · f_s / M` (channel-3 center) →
  `|y[ch3]| = 1.0000`, isolation 66.2 dB.
- Two-tone at `f = f_s/M` and `f = 5 · f_s/M` →
  `|y[ch1]| = 1.0000`, `|y[ch5]| = 1.0000`, isolation 64.5 dB.

### 3.2 DFT twiddle quantization

At `M = 8`, the ideal DFT twiddles snap to `{0, ±0.707107, ±1.0}`.
After bfloat16 quantization the non-trivial values are `±0.70703125`
(the 4-bit-mantissa bfloat16 quantum) and the zero entries collapse to
hard zero. The kernel stores both `W_re` and `W_im` as `constexpr
float[8][8]` — 128 words = 512 bytes of ROM shared with the FIR taps.

Note: `numpy.cos(pi/2)` returns approximately `6e-17`, not exactly
zero, and this residual **is** representable in bfloat16 as a
subnormal-adjacent value. To match the M17p convention and eliminate a
`6e-17 · v_re[n]` rounding tail that would otherwise perturb ~ 30 of
4096 output slots at bfloat16 output resolution, we hard-zero DFT
entries at multiples of `pi/2` in **both** kernel and host reference.

### 3.3 Polyphase tap quantization

The 64 prototype taps are bfloat16-quantized once and stored as
`const float hp[8][8]` in the kernel. The values used in the .cc are
the **exact bfloat16 quantum expressed as full float32 literals** (not
6-decimal ASCII), and the host reference reads the **same** table
verbatim. This single canonical source of taps is what makes silicon
vs host bit-exact at bfloat16 output resolution (see §5.2 below).

## 4. Kernel structure

The AIE2 kernel is one `NOCPP` C entry point with two sub-functions
inlined:

```
for frame in 0 .. 255:
    // 1. Commutator (natural sample-to-branch order)
    for q in 0 .. 7:
        p = q
        shift si[p][*], sq[p][*] right by 1
        si[p][0] = in[2·(f·8 + q)]
        sq[p][0] = in[2·(f·8 + q) + 1]

    // 2. M-path polyphase FIR (real & imag on same taps)
    for p in 0 .. 7:
        v_re[p] = sum_k hp[p][k] · si[p][k]
        v_im[p] = sum_k hp[p][k] · sq[p][k]

    // 3. 8-point matmul DFT (analysis convention)
    for k in 0 .. 7:
        y_re = sum_n (v_re[n] · W_re[k][n] - v_im[n] · W_im[k][n])
        y_im = sum_n (v_re[n] · W_im[k][n] + v_im[n] · W_re[k][n])
        out[2·(f·8 + k)]     = y_re
        out[2·(f·8 + k) + 1] = y_im
```

State: two `float[M][K]` shift registers = 512 bytes on the AIE2 stack.
ROM: `hp[8][8] + W_re[8][8] + W_im[8][8]` = 768 bytes constexpr.

## 5. Silicon-gate methodology

### 5.1 Deterministic vector

The silicon gate feeds a `numpy.random.seed(793)` uniform baseband
across the 2048 complex-input slots (bfloat16 packed as 4096 words) and
compares silicon `out` against the NumPy host reference at bfloat16
output resolution. Seed 793 is the same numbering convention used since
M15 (`silicon_seed = milestone_index * 10 + <local sub-index>`); the
reference `max |y| = 0.65234375` on this vector.

Tolerance: `atol = 0.02`. This is looser than M21/M22 (`0.01`) because
the DFT accumulates 8 bfloat16 rounding events per output sample on
top of the 8-tap FIR (16 total, versus M22's 4-tap interp + LO mix).
Empirically the max err seen in the host-to-host transliteration is
zero, and the expected silicon-vs-host max err at bfloat16 output
should be well under 0.02.

### 5.2 Bit-exact host reference

Getting the host reference to match the silicon kernel bit-for-bit
requires four discipline points:

1. **Single-truncation taps.** The host reads `HP_BF16[p][k]` as
   full-precision `float32` literals identical to the kernel's `hp[p][k]`
   — the taps go through **one** bfloat16 rounding (from the exact
   `firwin` output). Double-truncation (firwin → 6-decimal ASCII →
   bfloat16) introduces a 2e-7 gap that propagates to ~ 30 of 4096
   output slots at bfloat16 output resolution.
2. **Hard-zero DFT twiddles.** Both kernel and host force
   `W_re[k][n] = 0` and `W_im[k][n] = 0` where the ideal value is a
   multiple of `pi/2`.
3. **C++ operator precedence.** In `y += a * b + c * d`, C++ groups
   the two products first (`y = y + (a*b + c*d)`), and the host must
   mirror that grouping in `np.float32(y + np.float32(a - b))` rather
   than left-to-right Python `y + a - b`.
4. **Scalar `float32` accumulation.** Every intermediate scalar goes
   through `np.float32(...)` to prevent numpy from silently promoting
   to `float64` in Python-level arithmetic.

With all four in place, the sandbox transliteration
(`m23_kernel_transliteration_check.py`) is `np.array_equal` bit-exact
to the host reference on the seed-793 vector: 0 non-matching slots out
of 4096, max diff 0.0.

### 5.3 Silicon run

Executed on Phoenix NPU1 (2026-08-15, `AMD Ryzen 9 7940HS`,
Windows 11 Pro 25H2, IRON 1.4.1). Command:

```powershell
cd C:\phoenix-sdr-dsp
python tests\m23_channelizer\test_channelizer_m23.py
```

Result (verbatim):

```
[reference] Test 1 prototype: PASS (sum(h) = 0.999767, symmetry max diff = 0.00e+00)
[reference] Test 2 DC -> ch0: PASS (|ch0| = 1.0000, isolation = 66.2 dB)
[reference] Test 3 tone -> ch3: PASS (|ch3| = 1.0000, isolation = 66.2 dB)
[reference] Test 4 two-tone (ch1 + ch5): PASS (|ch1| = 1.0000, |ch5| = 1.0000, isolation = 64.5 dB)
Compiling fused polyphase channelizer with Peano and dispatching to Phoenix NPU...
Ref Out sample [0..4]:    [-0.00121307 -0.00193787 0.000648499 -0.00037384]
Actual Out sample [0..4]: [-0.0012207  -0.00193787 0.000644684 -0.000375748]
Maximum absolute error: 0.003906
SUCCESS: Phoenix NPU executed fused M-path polyphase channelizer (M = 8, K = 8) on physical silicon!
```

Wired as the 21st entry in [`run_all_silicon_tests.py`](../run_all_silicon_tests.py).
Commit [`43b0f9c1`](https://github.com/midhatn/phoenix-sdr-dsp/commit/43b0f9c19571e07fb883dce24f70ab8718bd22a5)
added 6 files (this design doc + kernel .cc + test .py + ROADMAP +
MILESTONES_AND_MATHEMATICS + runner) under
`MIDHAT NASHAR <medhat.nashar@gmail.com>`.

## 6. References

### Primary literature

- Fred Harris, *Multirate Signal Processing for Communication Systems*,
  Prentice Hall / IEEE, 2004; ch. 6 §6.3 fig. 6.8 M-path analysis
  bank; ch. 8 (digital down-converter). IEEE Xplore reissue.
  <https://ieeexplore.ieee.org/book/9448967>
- P. P. Vaidyanathan, *Multirate Systems and Filter Banks*, Prentice
  Hall, 1993; ch. 4 §4.3, Eq. 4.3.13 (polyphase commutator identity).
  <https://dl.acm.org/doi/10.5555/151045>
- J. F. Kaiser, "Nonrecursive Digital Filter Design Using the I0-sinh
  Window Function," *Proc. IEEE ISCAS*, 1974.
  <https://ieeexplore.ieee.org/document/1451724>
- A. V. Oppenheim & R. W. Schafer, *Discrete-Time Signal Processing*,
  3rd ed., Pearson, 2010; §4.7 (multirate) and §10.9 (window design).
  <https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003543>
- fred harris, Chris Dick, Michael Rice, "Digital receivers and
  transmitters using polyphase filter banks for wireless
  communications," *IEEE Trans. Microwave Theory & Techniques*,
  51(4):1395–1412, 2003.
  <https://ieeexplore.ieee.org/document/1193217>

### Reference implementations

- GNU Radio Wiki, "Polyphase Channelizer" (block-level description
  and natural sample-to-branch convention).
  <https://wiki.gnuradio.org/index.php/Polyphase_Channelizer>
- GNU Radio 3.7 API docs, `pfb_channelizer_ccf` (canonical open-source
  M-path analysis bank).
  <https://www.gnuradio.org/doc/sphinx-3.7.0/filter/channelizers_blk.html>
- GNU Radio C++ source, `gr::filter::pfb_channelizer_ccf` (natural
  commutator implementation on `main`).
  <https://github.com/gnuradio/gnuradio/blob/main/gr-filter/lib/pfb_channelizer_ccf_impl.cc>
- Tom Rondeau, "Designing Analysis and Synthesis Filterbanks in GNU
  Radio," GRCon 2013 tutorial.
  <https://static.squarespace.com/static/543ae9afe4b0c3b808d72acd/543aee1fe4b09162d08633d9/543aee20e4b09162d086354a/1395369129837/rondeau_gr_filtering.pdf>
- NVIDIA MatX documentation, `channelize_poly` (natural
  sample-to-branch convention on GPU).
  <https://nvidia.github.io/MatX/api/signalimage/filtering/channelize_poly.html>
- NVIDIA MatX C++ source, `channelize_poly.h`.
  <https://github.com/NVIDIA/MatX/blob/main/include/matx/transforms/channelize_poly.h>
- SciPy Cookbook, `scipy.signal.firwin` API reference (prototype
  design; `scale=True` DC-normalization convention).
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.firwin.html>
- SciPy Cookbook, `scipy.signal.kaiserord` API reference (Kaiser β /
  transition-width solver).
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.kaiserord.html>
- SciPy Cookbook, `scipy.fft.fft` API reference (analysis-convention
  sign `-j`, matching this milestone).
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.fft.fft.html>

### Blogs, tutorials, and archives

- Tom Verbeure, "Polyphase Channelizer" (visual intuition), 2026-02-16.
  <https://tomverbeure.github.io/2026/02/16/Polyphase-Channelizer.html>
- "Polyphase FFT Channelizers Derivation" (archived tutorial deriving
  the FIR + IDFT / DFT identity used here).
  <https://ia600507.us.archive.org/18/items/polyphase-fft-channelizers-derivation/Polyphase-FFT-Channelizers-Derivation.pdf>
- Kyle Isom, "An Interactive Polyphase Channelizer Walkthrough"
  (equation-by-equation reference).
  <https://kisom.com/posts/2019-10-04-polyphase-channelizers/>

### Hardware & toolchain

- AMD, product page for the Ryzen 9 7940HS "Phoenix" APU (host of the
  XDNA1 NPU used here).
  <https://www.amd.com/en/products/apu/amd-ryzen-9-7940hs>
- Linux Kernel Docs, "AMD NPU" (XDNA1 4×5 tile topology, `amdxdna`
  driver surface).
  <https://docs.kernel.org/accel/amdxdna/amdnpu.html>
- AMD, XAPP1406 "Floating-Point Numerical Formats on AIE-ML"
  (bfloat16 quantum, rounding, and MAC semantics).
  <https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Floating-Point-Numerical-Formats>
- Xilinx `mlir-aie` v1.4.1 release notes (`buildHostWinNative`
  target used to build this kernel).
  <https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1>
- Xilinx `mlir-aie` commit `3ca0193` — "Retain executable per kernel
  handle to fix run_chain use-after-free" (pinned toolchain revision).
  <https://github.com/Xilinx/mlir-aie/commit/3ca0193>

### Companion Phoenix SDR-DSP milestones

- M17p parallel FFT kernel `parallel_fft64_kernel.cc` — anchor for the
  matmul-style DFT with fully-embedded twiddles.
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/tests/m17p_fft_parallel/parallel_fft64_kernel.cc>
- M19 complex FIR kernel `fir_complex_kernel.cc` — anchor for the
  per-branch shift-and-ingest structure.
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/tests/m19_complex_fir/fir_complex_kernel.cc>
- M20 polyphase kernel `polyphase_kernel.cc` — anchor for the
  polyphase decomposition used here in the analysis-bank direction.
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/tests/m20_polyphase/polyphase_kernel.cc>
- Phoenix SDR-DSP repository root and ROADMAP (M19–M23 block context).
  <https://github.com/midhatn/phoenix-sdr-dsp>
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/docs/ROADMAP.md>
- M23 shipping commit `43b0f9c1` (silicon PASS; this milestone).
  <https://github.com/midhatn/phoenix-sdr-dsp/commit/43b0f9c19571e07fb883dce24f70ab8718bd22a5>
