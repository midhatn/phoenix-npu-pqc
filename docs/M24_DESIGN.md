# M24 — Correlator, Preamble Detection & Packet Sync Design

Status: implementation complete (host reference + kernel bit-exact match on seed-794 silicon-gate vector, silicon gate pending laptop run).
Owner: Phoenix SDR-DSP team.
Target hardware: [AMD Ryzen 9 7940HS "Phoenix"](https://www.amd.com/en/products/apu/amd-ryzen-9-7940hs) / [XDNA1 NPU](https://docs.kernel.org/accel/amdxdna/amdnpu.html) / AIE2 (one core, 4×5 tile array).
Target OS: Windows 11 Pro 25H2, Clang / Peano AIE2, [IRON MLIR-AIE 1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1).
Opens the **Modulation & synchronization** track (M24–M27). This milestone
is the DSP building block that gates M25 (BPSK/QPSK RX pipeline).

Related files:

- `tests/m24_correlator/correlator_kernel.cc` — fused AIE2 kernel (complex conjugate matched filter against real-valued Barker-13 preamble).
- `tests/m24_correlator/test_correlator_m24.py` — host driver, NumPy reference, 4 sanity gates, silicon gate.
- `run_all_silicon_tests.py` — regression runner (M24 will slot in as the 22nd entry after silicon PASS).

## 1. Problem statement

Packet-based radios (WiFi, Zigbee, LoRa, ADS-B, custom SDR link
layers) begin every burst with a fixed **preamble** — a known symbol
sequence chosen for its sharp autocorrelation. The receiver runs a
sliding correlation between the incoming complex I/Q stream and a
locally-stored copy of the preamble. When the correlation magnitude
crosses a threshold, the receiver declares "packet detected" and
hands the sample index to downstream timing- and carrier-recovery
blocks ([Harris 2004 ch. 15](https://ieeexplore.ieee.org/book/9448967);
[GNU Radio Correlation Estimator](https://wiki.gnuradio.org/index.php/Correlation_Estimator)).

M24 implements the sliding **complex conjugate matched-filter
correlator** — the arithmetic core that produces the correlation
stream. Threshold decision and stream tagging happen on the host
after the kernel returns.

## 2. Signal model

The received sample stream is complex baseband at rate `f_s`:
`x[n] ∈ ℂ` for `n = 0, 1, …, 2047` (2048 complex pairs).

The known preamble is the [length-13 Barker
sequence](https://en.wikipedia.org/wiki/Barker_code):

\[
s = (+1, +1, +1, +1, +1, -1, -1, +1, +1, -1, +1, -1, +1) \in \{-1, +1\}^{13}
\]

Barker-13 has the maximum possible peak sidelobe level for real
binary sequences of length ≤ 13: aperiodic autocorrelation `13`
at zero lag, `|c_v| ≤ 1` for all `1 ≤ v < 13` — a **13.24 dB
peak-to-sidelobe ratio** ([Barker 1953](https://ieeexplore.ieee.org/document/6773685);
[Wikipedia Barker code](https://en.wikipedia.org/wiki/Barker_code)).
This is why it is used as the sync sequence in IEEE 802.11 DSSS
1 Mbps and 2 Mbps PHY modes ([IEEE Std 802.11-2020 §17.4.6.5](https://standards.ieee.org/ieee/802.11/7028/))
and remains the canonical teaching example for radar
pulse-compression ([Skolnik, *Radar Handbook*, 3e, ch. 8](https://www.accessengineeringlibrary.com/content/book/9780071485470)).

## 3. Correlator equation

The complex matched filter for preamble `s` is defined as:

\[
y[n] \;=\; \sum_{k=0}^{L-1} \overline{s[k]} \cdot x[n+k], \qquad L = 13
\]

([Proakis & Salehi, *Digital Communications*, 5e §5.1.5](https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html);
[GNU Radio `corr_est_cc`](https://www.gnuradio.org/doc/doxygen-v3.7.10/corr__est__cc_8h_source.html);
[liquid-dsp `detector_cccf`](https://liquidsdr.org/doc/detector/)).

Because `s ∈ {-1, +1}` is real-valued, the conjugate collapses:

\[
I_y[n] = \sum_{k=0}^{L-1} s[k] \cdot I_x[n+k], \quad
Q_y[n] = \sum_{k=0}^{L-1} s[k] \cdot Q_x[n+k]
\]

**Correlator-as-reverse-FIR identity.** A sliding correlator with
taps `s[k]` and forward indexing `x[n+k]` produces an output stream
that is identical, sample-for-sample, to a **causal FIR filter**
with reversed taps `h[k] = s[L-1-k]` applied to the same input
([Oppenheim & Schafer, *DTSP*, 3e §2.6.2](https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003543)):

\[
y_{\text{corr}}[n] = \sum_{k=0}^{L-1} s[k] \cdot x[n+k]
                    = \sum_{k=0}^{L-1} s[L-1-k] \cdot x[n+k] \big|_{\text{reversed}}
                    = (h \ast x)[n + (L-1)]
\]

with delay `L-1`. This lets the kernel reuse the shift-and-ingest
FIR schedule of [M8](../tests/m8_pipeline/pipeline_kernel.cc) and
[M19](../tests/m19_complex_fir/fir_complex_kernel.cc)
line-for-line, with no forward buffering. The `L-1 = 12` sample
delay is a fixed group delay that the host reference walks
identically.

## 4. Kernel design

The correlator kernel runs on **one AIE2 core** and consumes 4096
bfloat16 samples (2048 complex I/Q pairs) per invocation, producing
4096 bfloat16 output samples (2048 correlator I/Q pairs) at the same
rate.

### 4.1 Taps

The 13 Barker taps are stored in the kernel in **reversed order**
(FIR convention) as `const float` constants — no bfloat16
quantization is needed because ±1 is exactly representable in
bfloat16 ([AMD XAPP1406 §Numerical Formats](https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Floating-Point-Numerical-Formats)):

```cpp
// Barker-13 reversed: s[12], s[11], ..., s[0]
// = (+1, -1, +1, -1, +1, +1, -1, -1, +1, +1, +1, +1, +1)
```

### 4.2 Loop schedule

Each iteration `i ∈ [0, 2048)`:

1. Read one `(Ix, Qx)` pair from `in_iq[2i], in_iq[2i+1]`.
2. Left-shift 13-slot `hist_i` and `hist_q` shift registers.
3. Ingest new sample into `hist_i[L-1]`, `hist_q[L-1]`.
4. Compute two 13-term dot products in float32 with reversed Barker
   taps (`hist[L-1]` pairs with `s[L-1]`, i.e. tap 0 of the reversed
   sequence).
5. Store `(Iy, Qy)` bfloat16 pair to `out_iq[2i], out_iq[2i+1]` with
   a single truncation on store (same convention as M5/M6/M19).

This matches the [M19 complex FIR
kernel](../tests/m19_complex_fir/fir_complex_kernel.cc) shape
one-for-one; the only differences are (a) 13-tap window instead of
8-tap and (b) real-valued taps so the four-term complex multiply
collapses to two independent real FIRs.

### 4.3 Zero-history warmup

For `n < L-1 = 12`, some shift-register slots are still zero
(startup transient). The host reference walks the identical
schedule, so silicon and host produce term-for-term matching output
including the transient. This is the same convention used by M5,
M8, M19 and M20.

## 5. Host reference & sanity gates

`test_correlator_m24.py` runs four host-side reference gates before
dispatching to silicon:

1. **Preamble self-check.** Drive `x[n]` = zero-padded Barker-13
   (i.e. Barker-13 at offset 100, zeros elsewhere, `Qx = 0`).
   Expect a correlation peak of magnitude **13.0** at sample
   `100` (Barker peak) and no sidelobe ≥ 2.
2. **DC input.** `x[n] = 1 + 0j`. Barker-13 has `sum(s) = +5`, so
   the steady-state I-channel output equals **5.0** and the Q-channel
   is zero. This confirms the reversed-tap convention is correct.
3. **Complex preamble at 45°.** Drive `x[n]` = Barker-13 at offset
   200, rotated by `exp(j π/4)`. Expect `|y[200]| = 13.0` with
   phase `π/4`. This confirms the correlator is phase-preserving.
4. **Negated preamble.** Drive `x[n]` = `-Barker-13` at offset 300.
   Expect `y[300] = -13`. This confirms sign fidelity.

### 5.1 Silicon gate

Random complex I/Q at seed 794, `atol = 0.05`. Barker-13 output can
reach `|y| = 13` on aligned patterns; sums of 13 bfloat16 MAC
roundings give a wider absolute-error budget than M23 (which had 8
FIR roundings + 8 DFT roundings but with tap magnitudes ≪ 1). Since
the taps are ±1 and the input is uniform on [-1, 1], each MAC
result has magnitude ≤ 1 and 13 of them accumulate; a bf16-quantum
per MAC × 13 gives an expected ~0.04 error floor, so `atol = 0.05`
is comfortable.

### 5.2 Bit-exactness discipline

Unlike M23, no special quantization discipline is required:

1. **Taps are ±1** — exactly representable in bfloat16 and float32,
   no double-truncation issue.
2. **No transcendentals** in the kernel (no DFT twiddles) — no
   `sin`/`cos` residuals to hard-zero.
3. **C++ associativity** is a non-issue because all 13 MACs share
   the same sign convention and there is no `y = y + (a - b)`
   pattern. But we still force `y = y + np.float32(s[k] * x[k])`
   in the host reference to match the natural left-to-right
   accumulation order the compiler emits.

Sandbox transliteration of the .cc constants and loop schedule is
`np.array_equal` bit-exact to the host reference on the seed-794
vector (0/4096 slots differ, max diff 0.0).

### 5.3 Bring-up incident — missing @iron.jit decorator

The M24 kernel produced all-zero silicon output for three consecutive
bring-up attempts. The failure signature was identical each run:
`Actual Out [0..4] = [0, 0, 0, 0]`, `Maximum absolute error = 7.53`
(= reference peak on the seed-794 random vector), and the ENTIRE
4096-slot output buffer read back as zeros.

| Draft | Change under test | Silicon result |
|-------|-------------------|----------------|
| 1 | Compact tap loop + `#pragma clang loop unroll_count(4)` | All zeros |
| 2 | Compact tap loop, no pragma | All zeros |
| 3 | Hand-unrolled 13-term dot product, literal `hist_i[N]` indices | All zeros |

Instrumenting `$HOME/.npu/cache` between runs revealed the real cause:
after clearing the cache and running the M24 test, `$HOME/.npu/cache`
remained EMPTY. A control run of the sibling M22 test with the same
fresh cache populated the expected per-design directory
(`$HOME/.npu/cache/<recipe_hash>/`) with the full artifact set
(`final.xclbin`, `insts.bin`, `main_core_0_2.elf`, `duc_kernel.o`,
`opted_main_core_0_2.ll`, etc.). M22 also returned a
`(CachedXRTKernelHandle, XRTKernelResult)` tuple as the "Kernel
execution result" print, while M24 returned raw MLIR module text.

Root cause: the M24 driver's program-builder function was defined as
a plain function, missing the `@iron.jit` decorator, and its
tensor/kwarg parameters were missing the `In`/`Out`/`CompileTime`
type annotations. Without those, `Program.resolve_program()` returns
the resolved MLIR module and IRON never invokes `aiecc`; there is no
compile step, no cache write, and no NPU dispatch. The silicon
buffer stays at its initial zero fill and the resulting max error
equals the reference peak.

Fix: match the M22/M23 driver template verbatim:

```python
@iron.jit
def correlator_program(
    input_iq: In,
    output_iq: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type],
):
    ...
    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()
```

The hand-unrolled 13-term FIR kernel from draft 3 is retained
unchanged. It matches the M22 shape (literal-index MACs, explicit
shift-and-ingest) and is bit-exact to the host reference in the
sandbox transliteration (0/4096 slots differ, max diff 0.0). All
three earlier drafts would also have produced correct silicon output
with the correct decorator; the loop shape was not the failure mode.

References:
- Xilinx `mlir-aie` IRON API overview — `@iron.jit` decorator and
  `In`/`Out`/`CompileTime` markers on driver functions.
  <https://xilinx.github.io/mlir-aie/1.4.1/api/iron/>
- Xilinx `mlir-aie` compilation stages guide — `NPU_CACHE_HOME`,
  `recipe_hash`, `artifact_hash`, `use_cache` semantics.
  <https://xilinx.github.io/mlir-aie/1.4.1/programming_guide/compilation_stages/>
- Xilinx `mlir-aie` getting-started tutorial — `@iron.jit` caching
  keyed by `(MLIR bytecode + compile-time kwargs)`.
  <https://deepwiki.com/Xilinx/mlir-aie/7.1-getting-started-with-iron>

## 6. References

### Primary literature

- R. H. Barker, "Group synchronizing of binary digital systems,"
  in W. Jackson (ed.), *Communication Theory*, Butterworth, 1953,
  pp. 273–287 (original Barker sequences paper).
  <https://ieeexplore.ieee.org/document/6773685>
- J. G. Proakis and M. Salehi, *Digital Communications*, 5th ed.,
  McGraw-Hill, 2008; §5.1.5 matched-filter receiver.
  <https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html>
- A. V. Oppenheim and R. W. Schafer, *Discrete-Time Signal
  Processing*, 3rd ed., Pearson, 2010; §2.6.2 correlation as
  reversed-FIR convolution.
  <https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003543>
- fred harris, *Multirate Signal Processing for Communication
  Systems*, Prentice Hall / IEEE, 2004; ch. 15 (frame
  synchronization and correlator design).
  <https://ieeexplore.ieee.org/book/9448967>
- M. I. Skolnik (ed.), *Radar Handbook*, 3rd ed., McGraw-Hill, 2008;
  ch. 8 (pulse-compression radar, canonical Barker application).
  <https://www.accessengineeringlibrary.com/content/book/9780071485470>
- J. L. Massey, "Optimum Frame Synchronization,"
  *IEEE Trans. Communications*, 20(2):115–119, 1972 (foundational
  frame-sync detector paper).
  <https://ieeexplore.ieee.org/document/1091459>

### Reference implementations

- GNU Radio wiki, "Correlation Estimator" (block-level description
  and matched-filter tags).
  <https://wiki.gnuradio.org/index.php/Correlation_Estimator>
- GNU Radio C++ header, `corr_est_cc.h` (matched-filter
  correlator against a symbol sequence).
  <https://www.gnuradio.org/doc/doxygen-v3.7.10/corr__est__cc_8h_source.html>
- GNU Radio C++ source, `corr_est_cc_impl.cc` on `main`.
  <https://github.com/gnuradio/gnuradio/blob/main/gr-digital/lib/corr_est_cc_impl.cc>
- liquid-dsp `detector_cccf` (streaming complex preamble detector).
  <https://liquidsdr.org/doc/detector/>
- liquid-dsp source, `src/framing/src/detector_cccf.c`.
  <https://github.com/jgaeddert/liquid-dsp/blob/master/src/framing/src/detector_cccf.c>
- NumPy `numpy.correlate` (host reference for aperiodic
  cross-correlation).
  <https://numpy.org/doc/stable/reference/generated/numpy.correlate.html>
- SciPy `scipy.signal.correlate` (canonical DSP correlator; docs
  give the same `conj(s[k]) * x[n+k]` convention used here).
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html>

### Sequences and standards

- Wikipedia, "Barker code" (Barker-13 sequence, autocorrelation,
  PSL bounds).
  <https://en.wikipedia.org/wiki/Barker_code>
- IEEE Std 802.11-2020 §17.4.6.5 "Long PLCP PPDU format" (Barker-11
  DSSS spreading sequence).
  <https://standards.ieee.org/ieee/802.11/7028/>
- Wikipedia, "Zadoff–Chu sequence" (constant-amplitude
  zero-autocorrelation alternative used in LTE PSS; not used here
  but referenced for M27).
  <https://en.wikipedia.org/wiki/Zadoff%E2%80%93Chu_sequence>

### Hardware & toolchain

- AMD, product page for the Ryzen 9 7940HS "Phoenix" APU.
  <https://www.amd.com/en/products/apu/amd-ryzen-9-7940hs>
- Linux Kernel Docs, "AMD NPU" (XDNA1 4×5 tile topology).
  <https://docs.kernel.org/accel/amdxdna/amdnpu.html>
- AMD, XAPP1406 "Floating-Point Numerical Formats on AIE-ML"
  (bfloat16 semantics; ±1 is exactly representable).
  <https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Floating-Point-Numerical-Formats>
- AMD, UG1603 *AI Engine Kernel Coding for Ryzen™ AI*,
  "Floating-Point Operations" (scalar float is emulated; kernel
  authors should prefer literal-index FIR bodies).
  <https://docs.amd.com/r/2023.2-English/ug1603-ai-engine-ml-kernel-graph/Floating-Point-Operations>
- Xilinx `mlir-aie` v1.4.1 release (`buildHostWinNative` target).
  <https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1>
- Xilinx `mlir-aie` compilation-stages guide (NPU_CACHE_HOME,
  `recipe_hash`, `artifact_hash`, `use_cache=False`).
  <https://xilinx.github.io/mlir-aie/1.4.1/programming_guide/compilation_stages/>

### Companion Phoenix SDR-DSP milestones

- M8 fused pipeline kernel `pipeline_kernel.cc` — anchor for the
  shift-and-ingest FIR schedule.
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/tests/m8_pipeline/pipeline_kernel.cc>
- M19 complex FIR kernel `fir_complex_kernel.cc` — anchor for the
  I/Q shift-register organization reused here.
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/tests/m19_complex_fir/fir_complex_kernel.cc>
- M23 polyphase channelizer `channelizer_kernel.cc` — anchor for
  the IRON JIT plumbing (`ExternalFunction`, `Worker`,
  `stack_size` override) reused here.
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/tests/m23_channelizer/channelizer_kernel.cc>
- Phoenix SDR-DSP repository root and ROADMAP.
  <https://github.com/midhatn/phoenix-sdr-dsp>
  <https://github.com/midhatn/phoenix-sdr-dsp/blob/main/docs/ROADMAP.md>
