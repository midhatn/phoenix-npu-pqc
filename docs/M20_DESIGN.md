# Milestone 20 — Polyphase Decimation and Interpolation on Phoenix NPU1

Status: shipped (silicon PASS on Phoenix NPU1, 2026-08-15, kernel revision v2 loopy).
Silicon result: 18/18 regression suite, max abs error `0.003906` at `atol = 0.01` on seed-789 random I/Q, wall clock 1.07 s under `run_all_silicon_tests.py`.
Design owner: MIDHAT NASHAR ([`35053211+midhatn`](https://github.com/midhatn)).
Related: [M5](../tests/m5_fir/) (real FIR), [M6](../tests/m6_mixer/) (complex mixer), [M8](../tests/m8_pipeline/) (streaming shift-and-ingest pattern), [M17](../tests/m17_radix2_fft/) (`stack_size` override), [M19](M19_DESIGN.md) (complex FIR).
Roadmap row: [M20](ROADMAP.md), filtering & resampling section.

## 1. Purpose

Add polyphase multirate resampling to the Phoenix NPU1 test suite:

- **Decimator (stage 1)**: reduces the sample rate by `M = 4`. Input `2048` complex I/Q pairs (bfloat16 interleaved), intermediate `2048 / M = 512` complex I/Q pairs.
- **Interpolator (stage 2)**: increases the sample rate by `L = 4`. Input `512` complex I/Q pairs (the decim output), output `512 · L = 2048` complex I/Q pairs.

Both stages use the same 16-tap Kaiser-window prototype low-pass filter, decomposed into `M = L = 4` polyphase branches of 4 taps each.

Both stages are **fused into a single kernel** running on one AIE2 core with one Worker, following the [M8 pattern](../tests/m8_pipeline/pipeline_kernel.cc) (mixer + FIR + power fused into one worker; not two chained workers). Host contract: 4096 bfloat16 in → 4096 bfloat16 out, same shape as [M19](M19_DESIGN.md), same shape as M8. Silicon gate is the end-to-end response of the fused pipeline against a NumPy reference that walks the same two-stage operand and rounding contract.

## 2. Multirate theory reference

The efficient polyphase decomposition of an FIR resampler is the standard technique for combined filter-and-rate-change; the canonical reference is [Vaidyanathan, *Multirate Systems and Filter Banks*, Prentice Hall (1993), chapter 4](https://www.pearson.com/en-us/subject-catalog/p/multirate-systems-and-filter-banks/P200000003431/9780130349507), extended in [Harris, *Multirate Signal Processing for Communication Systems*, Prentice Hall (2004), chapter 6](https://ieeexplore.ieee.org/book/9448967). The textbook derivation of decimation-by-`M` after a lowpass and interpolation-by-`L` after zero-insertion is in [Oppenheim & Schafer, *Discrete-Time Signal Processing*, 3rd ed., Prentice Hall (2010), §4.6](https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003390/9780131988422).

Let `h[n]`, `0 ≤ n < N` be a prototype low-pass FIR with cutoff `π/max(M, L)`.

### 2.1 Polyphase decomposition (type I)

For decimation by `M`, split `h` into `M` sub-filters `p_k`, `k = 0, …, M − 1`:

```
p_k[r] = h[r · M + k],   r = 0, …, N/M − 1
```

For interpolation by `L`, use exactly the same decomposition with `L` in place of `M`:

```
q_k[r] = h[r · L + k],   r = 0, …, N/L − 1
```

Vaidyanathan Eq. 4.3.4 and Fig. 4.3-4 give the equivalent block diagram.

### 2.2 Decimator: filter-then-downsample noble identity

Downsample-after-filter and filter-branches-then-commutator produce the same output ([Vaidyanathan Eq. 4.3.5, Fig. 4.3-8](https://www.pearson.com/en-us/subject-catalog/p/multirate-systems-and-filter-banks/P200000003431/9780130349507)):

```
y[m] = sum_{k=0}^{M-1} sum_{r=0}^{N/M - 1} p_k[r] · x[m · M − r · M − k]
     = sum_{k=0}^{M-1} sum_{r=0}^{N/M - 1} p_k[r] · x[(m − r) · M − k]
```

For output sample `m`, each of the `M` polyphase branches processes the sample sequence `{x[m · M − k], x[(m − 1) · M − k], …, x[(m − (N/M − 1)) · M − k]}` through its 4-tap branch filter, and the branch outputs are summed. The complex-valued input case has this repeated on the I and Q channels independently (the taps are real, so no cross-terms — this is *not* the M19 complex-taps case).

### 2.3 Interpolator: upsample-then-filter noble identity

Upsample-then-filter and commutator-then-filter-branches produce the same output ([Vaidyanathan Eq. 4.3.13, Fig. 4.3-11](https://www.pearson.com/en-us/subject-catalog/p/multirate-systems-and-filter-banks/P200000003431/9780130349507)):

```
y[m · L + k] = sum_{r=0}^{N/L - 1} q_k[r] · x[m − r],   k = 0, …, L − 1
```

For each input sample `x[m]`, the interpolator produces `L` output samples by running the `L` polyphase branches in parallel on the same input stream `{x[m], x[m − 1], …, x[m − (N/L − 1)]}` and reading branch outputs off in sequence. This is the standard "commutator model" ([Harris, Fig. 6.7](https://ieeexplore.ieee.org/book/9448967)).

### 2.4 Complex I/Q handling

The prototype filter is real. The complex I/Q input is filtered on each channel independently:

```
Iy[m] = sum_k p_k · Ix{...}
Qy[m] = sum_k p_k · Qx{...}
```

No complex-multiply identity is needed and the four-term expansion from [M19](M19_DESIGN.md) does not apply. The M6 complex mixer identity ([NIST DLMF §1.9](https://dlmf.nist.gov/1.9)) is unrelated to M20; if a future milestone applies polyphase to complex-valued taps that would be a separate design.

### 2.5 Reference implementation (don't reinvent)

The canonical open-source polyphase resampler is [`scipy.signal.resample_poly`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html) (source: [`scipy/signal/_signaltools.py`](https://github.com/scipy/scipy/blob/main/scipy/signal/_signaltools.py)), which internally calls [`scipy.signal.upfirdn`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.upfirdn.html). This is the reference every SDR practitioner (cusignal, librosa, GNU Radio's [`Rational Resampler`](https://wiki.gnuradio.org/index.php/Rational_Resampler)) is calibrated against.

We adopt scipy's tap-scaling convention verbatim:

- **Decimator taps** `h_d`: prototype `h` with `sum(h_d) = 1` (unity DC gain).
- **Interpolator taps** `h_i`: prototype `h` scaled by `L`, giving `sum(h_i) = L`. This compensates the 1/L amplitude loss from zero-insertion upsampling (scipy `signaltools._resample_poly` applies `taps *= up` for exactly this reason).

With both stages sharing the same prototype but the interp side L-compensated, the combined end-to-end DC gain of decim → interp is `1 · L / L = 1`, and the passband is flat and unity, bit-comparable to `scipy.signal.upfirdn(h_i, upfirdn(h_d, x, up=1, down=M), up=L, down=1)` up to bfloat16 rounding.

Other prior-art references consulted (same convention):

- [GNU Radio `pfb_decimator_ccf` / `pfb_interpolator_ccf`](https://github.com/gnuradio/gnuradio/tree/main/gr-filter/lib) with docs at https://www.gnuradio.org/doc/doxygen-3.7/page_pfb.html.
- [liquid-dsp `firdecim_crcf` / `firinterp_crcf`](https://github.com/jgaeddert/liquid-dsp) (Joseph Gaeddert, MIT license). liquid-dsp exposes both a bare-prototype and an L-scaled interp API; the standard flow uses the L-scaled convention.
- [AMD Vitis DSP Library `fir_resampler`](https://github.com/Xilinx/Vitis_Libraries/tree/main/dsp/L1/include/aie) (AIE-targeted implementation on Versal — architecturally different from AIE2 Phoenix but confirms the polyphase-fused kernel pattern is the standard hardware layout).

What this milestone contributes on top of the reference: the fused decim → interp kernel scheduled inside **one** AIE2 core with a single Worker and a single xclbin, sharing the two 16-tap dot products through a float32 intermediate buffer. That AIE2 layout is not something scipy or liquid-dsp provide out of the box.

## 3. Prototype filter design

The prototype low-pass FIR is designed by the [Kaiser window method](https://ieeexplore.ieee.org/document/1451724) ([J. F. Kaiser, "Nonrecursive digital filter design using the `I_0`-sinh window function", IEEE ISCAS 1974](https://ieeexplore.ieee.org/document/1451724); [Oppenheim & Schafer 3e, §7.5](https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003390/9780131988422)):

```
h_ideal[n] = sinc((n − (N − 1)/2) / M)              (ideal LPF, cutoff π/M)
w[n]       = I_0(β · sqrt(1 − ((n − (N − 1)/2)/((N − 1)/2))^2)) / I_0(β)
h[n]       = h_ideal[n] · w[n]                       (windowed FIR)
h[n]       = h[n] / sum_n h[n]                       (normalize to unity DC gain)
```

with `N = 16`, `M = 4`, `β = 6.0`, and coefficient truncation through bfloat16. `I_0` is the [modified Bessel function of the first kind, order zero](https://dlmf.nist.gov/10.25#i) ([NIST DLMF §10.25](https://dlmf.nist.gov/10.25#i)). This matches scipy's default filter design in `resample_poly` (which uses `scipy.signal.firwin` with a Kaiser window internally), with a shorter length chosen to fit one AIE2 core's schedule (see §3.2).

### 3.1 Baked coefficients

Symmetric, unity DC gain to bfloat16 precision. Two tables, both derived from the same prototype `h`:

**Decimator taps `h_d = h`, `sum(h_d) = 0.999424`:**

```
hd[ 0] = -0.000242f;   hd[ 8] = +0.241211f;
hd[ 1] = -0.003281f;   hd[ 9] = +0.175781f;
hd[ 2] = -0.009644f;   hd[10] = +0.086426f;
hd[ 3] = -0.009216f;   hd[11] = +0.018677f;
hd[ 4] = +0.018677f;   hd[12] = -0.009216f;
hd[ 5] = +0.086426f;   hd[13] = -0.009644f;
hd[ 6] = +0.175781f;   hd[14] = -0.003281f;
hd[ 7] = +0.241211f;   hd[15] = -0.000242f;
```

**Interpolator taps `h_i = L · h` (scipy convention), `sum(h_i) = 3.997696`:**

```
hi[ 0] = -0.000969f;   hi[ 8] = +0.964844f;
hi[ 1] = -0.013123f;   hi[ 9] = +0.703125f;
hi[ 2] = -0.038574f;   hi[10] = +0.345703f;
hi[ 3] = -0.036865f;   hi[11] = +0.074707f;
hi[ 4] = +0.074707f;   hi[12] = -0.036865f;
hi[ 5] = +0.345703f;   hi[13] = -0.038574f;
hi[ 6] = +0.703125f;   hi[14] = -0.013123f;
hi[ 7] = +0.964844f;   hi[15] = -0.000969f;
```

Combined end-to-end DC gain: `sum(h_d) · sum(h_i) / L ≈ 0.9986` (unity to −60 dB), bit-comparable to `scipy.signal.upfirdn` on the same tap arrays.

### 3.2 Filter response and known limitation

At `N = 16`, `M = 4`, `β = 6` the stopband attenuation is about **−19 dB** at `w = 1.5 · π/M` (from the sandbox design script). That is acceptable for a first-silicon polyphase gate but **shallower than a shipping SDR decimator would use** — a typical M20 SDR filter would be `N = 32` or `N = 64` with `β = 8..10` for `−60 dB` stopbands ([Harris §3.1](https://ieeexplore.ieee.org/book/9448967)). The 16-tap length is chosen because it gives exactly 4 taps per polyphase branch, which keeps the kernel body inside a single AIE2 core's viable schedule (M19's 8-tap silicon-timeout debug informed this sizing — see [M19 §5.3](M19_DESIGN.md)).

A future milestone could ship a longer prototype filter as a separate variant.

### 3.3 Polyphase branches (M = L = 4)

Row `k` is branch `k`; columns are `p_k[0], p_k[1], p_k[2], p_k[3]`:

```
branch 0: h[ 0], h[ 4], h[ 8], h[12]  =  -0.000242, +0.018677, +0.241211, -0.009216
branch 1: h[ 1], h[ 5], h[ 9], h[13]  =  -0.003281, +0.086426, +0.175781, -0.009644
branch 2: h[ 2], h[ 6], h[10], h[14]  =  -0.009644, +0.175781, +0.086426, -0.003281
branch 3: h[ 3], h[ 7], h[11], h[15]  =  -0.009216, +0.241211, +0.018677, -0.000242
```

Branch 1 is the reverse of branch 2 (a property of symmetric prototype filters under the type-I decomposition — see [Vaidyanathan §4.3.2](https://www.pearson.com/en-us/subject-catalog/p/multirate-systems-and-filter-banks/P200000003431/9780130349507)).

## 4. Reference contract

The NumPy host reference in `test_polyphase_m20.py` performs:

### 4.1 Decimator reference

```python
Iy[m], Qy[m] = 0, 0
for k in range(M):        # over polyphase branches
    for r in range(4):    # over branch taps
        idx = m * M - r * M - k
        if idx >= 0:
            Iy[m] += pk[k, r] * Ix[idx]
            Qy[m] += pk[k, r] * Qx[idx]
```

with `x[n] = 0` for `n < 0` (zero-history warmup, same convention as [M8 pipeline_kernel.cc](../tests/m8_pipeline/pipeline_kernel.cc)). Output length `M_out = 2048 / M = 512`.

### 4.2 Interpolator reference

```python
Iy[m * L + k], Qy[m * L + k] = 0, 0
for r in range(4):        # over branch taps
    idx = m - r
    if idx >= 0:
        Iy[m * L + k] += qk[k, r] * Ix[idx]
        Qy[m * L + k] += qk[k, r] * Qx[idx]
```

for each `k = 0, …, L − 1` and each input index `m = 0, …, 511`. Output length `M_out = 512 · L = 2048`.

Both references cast tap constants through bfloat16 → float32 (same convention as [M5 test_fir_m5.py:104-105](../tests/m5_fir/test_fir_m5.py)) so the reference matches the kernel operand contract term-for-term.

## 5. Kernel implementation

Both kernel bodies follow the [M8 shift-and-ingest style](../tests/m8_pipeline/pipeline_kernel.cc), sized for a single AIE2 core with a `stack_size=0x4000` (16 KB) override on the Worker matching [M17 test_fft_m17_v3.py line 76](../tests/m17_radix2_fft/test_fft_m17_v3.py) — [M19 §5.3](M19_DESIGN.md) established that the default IRON stack size is insufficient for kernels with multiple hand-unrolled dot products, and although the shipped M20 kernel is loop-rolled per §8.1, the same 16 KB stack override is retained for its `hist_i[16]` / `hist_q[16]` shift registers plus scalar accumulators.

### 5.1 Decimator stage (inside `polyphase_kernel.cc`)

Body (as shipped in kernel revision v2, compact `for`-loop form):

```
const float hd[16] = { ... };            // baked Kaiser prototype, unity DC gain
for m in 0 .. 511:
  base = m * 4                            # input index of "phase 0" tap
  Iacc, Qacc = 0, 0
  for k in 0..15:                         # full 16-tap dot product
    idx = base - k
    if idx >= 0:
      Iacc += hd[k] * Ix[idx]
      Qacc += hd[k] * Qx[idx]
  Iy[m], Qy[m] = Iacc, Qacc
```

The body is expressed as a plain 16-iteration inner `for` loop with **no `#pragma clang loop unroll_count(...)` hint**. The polyphase decomposition `p_k[r] = hd[r*M + k]` is used to derive the tap layout and DC-gain contract but not to factor the hardware loop — the kernel evaluates the full 16-tap dot product per output. This is a deliberate code-size trade-off documented in §8.1.

### 5.2 Interpolator stage (inside `polyphase_kernel.cc`)

Body (as shipped, compact `for`-loop form):

```
const float hi[16] = { ... };            // baked Kaiser prototype * L (unity end-to-end gain)
for m in 0 .. 511:
  Ix_hist = shift-register of last 4 Ix samples ending at Ix[m]
  Qx_hist = shift-register of last 4 Qx samples ending at Qx[m]
  for k in 0..3:                          # commutator phase = output phase
    Iacc, Qacc = 0, 0
    for r in 0..3:                        # 4 taps per phase = 16/L
      Iacc += hi[r*L + k] * Ix_hist[3 - r]
      Qacc += hi[r*L + k] * Qx_hist[3 - r]
    Iy[m * L + k], Qy[m * L + k] = Iacc, Qacc
```

512 outer iterations × 4 output phases × 4 taps = 8192 output samples total. Both inner loops are plain `for` loops with no unroll hints (see §8.1).

### 5.3 Fused dispatch (M8 pattern)

The host script `test_polyphase_m20.py` creates a **single** `@iron.jit` function — `polyphase_resample` — that dispatches a single fused kernel `polyphase_kernel.cc` running on one Worker. Inside the kernel:

1. Decim stage reads all 2048 complex I/Q pairs and writes 512 pairs to a local float32 intermediate buffer (`inter_i[512]`, `inter_q[512]` — 4 KiB stack).
2. Interp stage reads those 512 pairs from the intermediate buffer and writes 2048 pairs to the output.

This matches the [M8 fused-pipeline pattern](../tests/m8_pipeline/pipeline_kernel.cc): one Worker, one xclbin, no intermediate ObjectFifo. Host contract: `input_iq[4096] → output_iq[4096]`, same shape as M8 and M19.

Numerical fixed points:

- **DC**: any constant input passes through both stages with gain `sum(h_d) · sum(h_i) / L ≈ 1.0`, matching scipy's convention (bit-comparable to `scipy.signal.upfirdn` up to bfloat16 rounding).
- **Impulse at input index 0**: decim output has an impulse response of `p_0` (branch 0 of `h_d` = `[hd[0], hd[4], hd[8], hd[12]]`); interp on that yields a scaled and delayed version of `h_i`.
- **M19-degeneracy sanity**: with `L = 1` and `M = 1` the entire pipeline degenerates to a real FIR by the appropriate stage's tap array; not run as a silicon test but noted here so the reference contract stays honest.

## 6. Test plan

`test_polyphase_m20.py` runs, in order:

| # | Test | Description | Expected |
|---|------|-------------|----------|
| 1 | **Kaiser tap generation** | Regenerate the 16 taps in Python and diff against the baked `h[0..15]` constants in both kernels | Bit-exact after bfloat16 round-trip |
| 2 | **Impulse at index 0 (decim)** | `Ix[0] = 1`, all else 0 → decim output `Iy[m] = p_0[m]` for m in 0..3, zero after | Match under atol=1e-6 |
| 3 | **DC (decim + interp)** | `Ix ≡ 1`, `Qx ≡ 0`, run both stages | Steady-state samples ≈ `sum(h_d) · sum(h_i) / L ≈ 1.0` within atol=0.02 (scipy convention) |
| 4 | **Complex tone below cutoff** | `x[n] = e^{j·2π·f·n/2048}`, `f = 4` (below π/4 rad/sample), run both stages | Recovered tone at `f` matches input at unity gain within atol=0.05 (scipy convention) |
| 5 | **Random I/Q silicon gate** | Seed 789 uniform in `[−1, 1]`, run decim → interp | `max_err ≤ atol = 0.01` against reference |
| 6 | **Length check** | assert decim out length = 512, interp out length = 2048 | pass |

## 7. Host driver

Same shape as [M19 test_fir_complex_m19.py](../tests/m19_complex_fir/test_fir_complex_m19.py):

- `@iron.jit` decorator on `polyphase_decim(input_iq, output_iq)` and `polyphase_interp(input_iq, output_iq)`.
- `Worker(core_body, fn_args=[...], stack_size=0x4000)` on each.
- Sequence: `in_prod.fill(a_in)` then `out_cons.drain(c_out, wait=True)`.
- XRTTensor bfloat16 buffers.
- Pre-silicon host reference checks 1–4 above, then Test 5 as the silicon PASS gate.
- Final `SUCCESS: Phoenix NPU executed 4:1 Decimator + 1:4 Interpolator Polyphase Filter on physical silicon!` and `PASS!` markers for the runner grep.

## 8. Stack, load, and schedule sizing

- **Iterations**: 512 for decim, 512 for interp — both well under M8's 2048 and M17's 64-point FFT.
- **Local state**: `hist_i[16]`, `hist_q[16]` per kernel = 128 bytes of float per shift register × 2 = 256 bytes stack. Plus scalar accumulators. Well inside the 16 KB requested `stack_size`.
- **Load traffic per output**: 8 fresh bfloat16 loads for decim (before shift-register reuse), 2 for interp — both below M19's 2-load steady-state and safely below the observed timeout threshold.

### 8.1 Program-memory sizing lesson (v1 → v2 kernel revision)

The first-cut v1 kernel expressed each 16-tap dot product as a hand-flat 16-term expression with `#pragma clang loop unroll_count(4)`, matching the [M8 / M19 convention](M19_DESIGN.md) ([LLVM/Clang loop-hint pragma](https://clang.llvm.org/docs/LanguageExtensions.html#extensions-for-loop-hint-optimizations)). Two 16-tap dot products (decim + interp) fused into one core overflowed the AIE2 core's 16 KB program memory, with the loader reporting:

```
[AIE ERROR] _XAie_LoadProgMemSection():231: Overflow of program memory
XAie_LoadElf failed with XAIE_INVALID_ELF
```

See the [AI Engine System Software Driver `xaie_elfloader.c`](https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/aienginev2/src/global/xaie_elfloader.c) for the check site (`_XAie_LoadProgMemSection` returns `XAIE_INVALID_ELF` when the ELF program segment exceeds a tile's program-memory capacity). Program-memory sizing on AIE2 is documented in the [AI Engine ML Architecture Manual (AM020)](https://docs.amd.com/r/en-US/am020-versal-aie-ml) and in the general [XDNA / Phoenix NPU programming discussion](https://docs.kernel.org/accel/amdxdna/amdnpu.html); each AIE2 tile has a fixed 16 KB of program memory that must hold the entire kernel body.

Kernel revision v2 rewrites both dot products as compact `for` loops and **removes the `#pragma clang loop unroll_count(...)` hint on the taps inner loop**. Peano then compiles a rolled loop that fits comfortably, and silicon accuracy is unchanged (schedule stays bit-exact against the reference at `atol = 0.01`). The general lesson, applicable to future fused kernels:

> If AIE2 hits `_XAie_LoadProgMemSection() ... Overflow of program memory` / `XAIE_INVALID_ELF`, replace hand-flat N-term dot products with compact `for` loops and drop the `#pragma clang loop unroll_count(N)`. Same schedule, smaller program image.

## 9. Wiring after silicon PASS (delivered)

Silicon PASSed on Phoenix NPU1 2026-08-15 at kernel revision v2 (see §8.1). Post-PASS wiring, applied in the same session:

- Added M20 as the 18th row in `run_all_silicon_tests.py` after M19 (new history block `v0.4.0+M20`).
- Updated `docs/ROADMAP.md` M20 row: 🚧 → ✅, with citations to [Kaiser 1974](https://ieeexplore.ieee.org/document/1451724), [Vaidyanathan 1993 ch. 4](https://www.pearson.com/en-us/subject-catalog/p/multirate-systems-and-filter-banks/P200000003431/9780130349507), [Harris 2004 ch. 6](https://ieeexplore.ieee.org/book/9448967), [`scipy.signal.resample_poly`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html), and [GNU Radio pfb](https://www.gnuradio.org/doc/doxygen-3.7/page_pfb.html).
- Added M19 and M20 sections to `docs/MILESTONES_AND_MATHEMATICS.md`, extended the regression-coverage list from 16 to 18 entries, and added new References for Vaidyanathan 1993, Harris 2004, Oppenheim & Schafer 2010, Kaiser 1974, SciPy `resample_poly` / `upfirdn` / `_signaltools.py`, GNU Radio pfb + `gr-filter` source, liquid-dsp, AMD Vitis DSP Library, and NIST DLMF §10.25.
- Contract moved from 17/17 to **18/18** silicon-validated milestones (regression suite 15.76 s wall clock).
- No new tag, no v0.4.0 bump, no new release, no touching `third_party/mlir-aie/` or installer pins.

## References

Primary sources cited above, with full URLs:

- Xilinx MLIR-AIE v1.4.1: https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1
- Xilinx MLIR-AIE commit `3ca0193` (installer pin): https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22
- IRON native-Windows build guide: https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
- Xilinx XRT ERT return codes: https://github.com/Xilinx/XRT/blob/master/src/runtime_src/core/include/ert.h
- LLVM/Clang loop-hint pragma: https://clang.llvm.org/docs/LanguageExtensions.html#extensions-for-loop-hint-optimizations
- AI Engine System Software Driver, `xaie_elfloader.c` (`_XAie_LoadProgMemSection` overflow check site): https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/aienginev2/src/global/xaie_elfloader.c
- AMD AI Engine ML Architecture Manual (AM020) — AIE2 core memory map (program + data memory sizing): https://docs.amd.com/r/en-US/am020-versal-aie-ml
- LLVM Peano (llvm-aie) releases: https://github.com/Xilinx/llvm-aie/releases
- Linux `amdxdna` Phoenix topology (4×5): https://docs.kernel.org/accel/amdxdna/amdnpu.html
- P. P. Vaidyanathan, *Multirate Systems and Filter Banks*, Prentice Hall (1993): https://www.pearson.com/en-us/subject-catalog/p/multirate-systems-and-filter-banks/P200000003431/9780130349507
- F. J. Harris, *Multirate Signal Processing for Communication Systems*, Prentice Hall (2004): https://ieeexplore.ieee.org/book/9448967
- A. V. Oppenheim and R. W. Schafer, *Discrete-Time Signal Processing*, 3rd ed., Prentice Hall (2010): https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003390/9780131988422
- J. F. Kaiser, "Nonrecursive digital filter design using the I_0-sinh window function", IEEE ISCAS (1974): https://ieeexplore.ieee.org/document/1451724
- NIST DLMF §10.25 (modified Bessel functions): https://dlmf.nist.gov/10.25#i
- NIST DLMF §1.9 (complex arithmetic): https://dlmf.nist.gov/1.9
- ml_dtypes bfloat16: https://github.com/jax-ml/ml_dtypes
- SciPy `resample_poly` docs: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html
- SciPy `upfirdn` docs: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.upfirdn.html
- SciPy `_signaltools.py` source (implementation of `resample_poly`, `taps *= up` convention): https://github.com/scipy/scipy/blob/main/scipy/signal/_signaltools.py
- GNU Radio `pfb_decimator_ccf` / `pfb_interpolator_ccf` source: https://github.com/gnuradio/gnuradio/tree/main/gr-filter/lib
- GNU Radio pfb overview: https://www.gnuradio.org/doc/doxygen-3.7/page_pfb.html
- GNU Radio Rational Resampler wiki: https://wiki.gnuradio.org/index.php/Rational_Resampler
- liquid-dsp `firdecim_crcf` / `firinterp_crcf` (Joseph Gaeddert): https://github.com/jgaeddert/liquid-dsp
- AMD Vitis DSP Library (AIE-targeted `fir_resampler`, Versal): https://github.com/Xilinx/Vitis_Libraries/tree/main/dsp/L1/include/aie
- M19 design document (this repo): [docs/M19_DESIGN.md](M19_DESIGN.md)
- M17 v3 design document (this repo): [docs/M17_V3_DESIGN.md](M17_V3_DESIGN.md)
