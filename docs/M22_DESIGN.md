# M22 — Digital Up-Converter (DUC) Design

Status: in review (pre-silicon).
Owner: Phoenix SDR-DSP team.
Target hardware: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2 (one core).
Target OS: Windows 11 Pro 25H2, Clang / Peano AIE2, IRON 1.4.1.
Related files:

- `tests/m22_duc/duc_kernel.cc` — fused AIE2 kernel (Interp + LPF + Mix).
- `tests/m22_duc/test_duc_m22.py` — host driver, NumPy reference, silicon gate.
- `include/sdr_dsp/sdr_dsp_common.hpp` — shared AIE2 vector definitions.

## 1. Purpose

A Digital Up-Converter (DUC) is the mathematical inverse of a DDC. It
takes a narrowband complex baseband signal, raises its sample rate,
and shifts it up to an intermediate frequency where a DAC can play
it out. In one sentence:

> `x_if[n] = { LPF { upsample_L { x_bb[m] } } } · e^(+j 2π f_c n / f_s)`

Milestone 22 delivers a **single fused AIE2 kernel** that runs all three
stages on one core:

1. Zero-stuff interpolation by `L = 4` fused with a 16-tap Kaiser LPF,
   expressed as an `L`-branch polyphase filter (reuses M20 stage-2 exactly).
2. Complex mix by a numerically-controlled oscillator (NCO) at
   `f_c = +f_s/8` (positive-frequency, opposite sign to M21 DDC).

The design is a near-perfect mirror of M21: same 8-entry cordic-free LO
LUT, same 16-tap Kaiser prototype, same one-core one-Worker one-xclbin
fusion pattern. The differences are just the sign of the LO
(`sin_lo` negated to upconvert instead of downconvert) and the direction
of the multirate stage (interp instead of decim).

## 2. Signal-chain math

### 2.1 Zero-stuff interpolation with polyphase LPF

The classical L-fold interpolator zero-stuffs `L-1` samples between each
input sample and low-pass filters the result to remove the periodic
spectral images introduced by the zero-insertion (Oppenheim & Schafer 3e
§4.6.2; Harris 2004 §7.1). Rather than materialise the zero-stuffed
stream and run the full-rate filter, the kernel evaluates only the
non-zero taps for each output phase using the polyphase decomposition
([Vaidyanathan 1993 §4.3, Eq. 4.3.13](https://dl.acm.org/doi/10.5555/151045);
[Harris 2004 §7.3](https://ieeexplore.ieee.org/book/9448967)):

```
for m in 0 .. N_bb - 1:
    xi[0..3] <- xi[1..3], x_bb[m]           # shift-and-ingest baseband
    for k in 0 .. L-1:
        y_bb[m*L + k] = sum_{r=0..3} hi[r*L + k] * xi[3-r]
```

The 16-tap prototype is decomposed into `L = 4` branches of 4 taps each.
Each output phase picks a different tap subset (`k, k+4, k+8, k+12`)
from the same 4-slot baseband shift register.

### 2.2 Interpolator tap scaling

The prototype filter is scaled by `L = 4` to compensate the `1/L`
amplitude loss that zero-stuffing introduces (the "`taps *= up`"
convention from
[`scipy.signal.resample_poly`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html)).
End-to-end DC gain therefore comes out to exactly 1:

\[
\text{gain}_{\text{DC}} = \frac{\sum h_i}{L} = \frac{L \cdot \sum h}{L} = \sum h \approx 1
\]

This is the same `hi[16]` array M20 stage-2 already ships in
[`tests/m20_polyphase/polyphase_kernel.cc`](../tests/m20_polyphase/polyphase_kernel.cc);
reusing it byte-for-byte keeps M22 aligned with the M20-shipped filter
design and its silicon-validated passband and stopband behaviour
([`docs/M20_DESIGN.md` §3.1](./M20_DESIGN.md)).

### 2.3 Upconversion mix

After interpolation the baseband spectrum sits centred at DC on the
new full-rate grid. A complex mix by `+f_c` translates it up to `+f_c`
(Harris 2004 §8.4 "The Digital Up-Converter"):

```
x_if[n] = y_bb[n] · e^{+j 2π f_c n / f_s}
        = y_bb[n] · (cos_lo[n] + j sin_lo[n])
```

Expanding the complex multiply gives the operand order the kernel uses
([Oppenheim & Schafer 3e §2.2](https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003390/9780131988422);
[NIST DLMF §1.9](https://dlmf.nist.gov/1.9)):

```
I_if[n] = I_y[n] · cos_lo[n] - Q_y[n] · sin_lo[n]
Q_if[n] = I_y[n] · sin_lo[n] + Q_y[n] · cos_lo[n]
```

### 2.4 LO look-up table

With `f_c = f_s / 8` the LO is periodic with period 8 output samples,
so only **8 unique LO samples** exist. The kernel stores them as a
`const float[8]` LUT indexed by `(n_out & 7)`. This is the standard
cordic-free DDS trick documented in
[Analog Devices MT-085 "Fundamentals of Direct Digital Synthesis (DDS)"
Table 1](https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf).

Concretely M22 is **the M21 LO with `sin_lo` negated** (positive-
frequency mix versus M21's negative-frequency mix). Values are the
bfloat16 quantisations of `{±1, ±√2/2, 0}`:

```
lo_cos = [ +1.0000,  +0.7070,   0.0000,  -0.7070,
           -1.0000,  -0.7070,   0.0000,  +0.7070 ]
lo_sin = [  0.0000,  +0.7070,  +1.0000,  +0.7070,
            0.0000,  -0.7070,  -1.0000,  -0.7070 ]
```

Sandbox regeneration from the closed-form formula matches the baked LUT
term-for-term to floating-point epsilon (Test 1 in the host driver).

## 3. Dataflow shape

| Item | Value | Rationale |
| --- | --- | --- |
| Input length | 4096 bfloat16 slots; first 1024 = 512 complex baseband pairs | Matches M20/M21 XRT plumbing; extra slots kept zero. |
| Output length | 4096 bfloat16 = 2048 complex pairs @ `f_s`, all populated | Interp-by-4 fills the whole buffer; no zero-tail. |
| Interpolation `L` | 4 | Matches M20 stage-2; same shift register and tap subsets. |
| `f_c` | `+f_s/8` | Enables cordic-free 8-entry LO LUT; mirror of M21. |
| Filter length | 16 taps | Reuses M20 Kaiser prototype × L. |

## 4. AIE2 kernel implementation

Filed at [`tests/m22_duc/duc_kernel.cc`](../tests/m22_duc/duc_kernel.cc).

### 4.1 One core, one Worker, one xclbin

The whole pipeline fits in a single AIE2 core:

- Local state: `xi[4]`, `xq[4]`, `lo_cos[8]`, `lo_sin[8]`, `hi[16]` —
  all `float` — totalling ~ 130 bytes on stack. Comfortably below the
  16 KB `stack_size = 0x4000` override retained from the M19/M20/M21
  envelope
  ([`docs/M19_DESIGN.md` §5.3](./M19_DESIGN.md)).
- No ObjectFifo between interp and mix: each interpolated pair is
  multiplied by the LO in the same iteration where it is produced, so
  the interp stage never materialises a full 2048-pair intermediate
  buffer in memory. This is the M8 / M21 fused-pipeline pattern
  ([`tests/m8_pipeline/pipeline_kernel.cc`](../tests/m8_pipeline/pipeline_kernel.cc),
  [`tests/m21_ddc/ddc_kernel.cc`](../tests/m21_ddc/ddc_kernel.cc)).
- No zero-fill on the output buffer: unlike M21, every output pair is
  populated by the loop (interp expands the sample rate, so 512 baseband
  pairs → 2048 IF pairs fills the same 4096-slot buffer completely).

### 4.2 Program-memory sizing

The kernel follows the M20 revision-2 lesson
([`docs/M20_DESIGN.md` §8.1](./M20_DESIGN.md)) and M21 §4.2 exactly:
all dot products are compact `for` loops with **no
`#pragma clang loop unroll_count`** hints. This keeps the program
image comfortably below the AIE2 core's 16 KB program memory even with
the 16-tap Kaiser×L LPF and 8-entry LO LUT baked in.

## 5. Host driver

Filed at [`tests/m22_duc/test_duc_m22.py`](../tests/m22_duc/test_duc_m22.py).

### 5.1 Four host-side reference checks before silicon dispatch

1. **LO LUT regeneration.** Recompute `cos(+2π k / 8)` and `sin(+2π k / 8)`
   from NumPy at bfloat16 precision, diff against the baked LUT. Max diff
   must be `< 1e-6`.
2. **Impulse response.** Drive `Ix[0]=1`, everything else 0. After the
   16-tap LPF the pipeline emits 16 non-zero output samples multiplied
   by the LO, which zeros a subset of slots (four LO slots have either
   `cos=0` or `sin=0`). Assertion: 8 ≤ non-zero complex samples ≤ 20.
3. **DC baseband → +f_s/8 tone.** Drive `x_bb[m] = 1`. The LPF passes DC
   at unity gain end-to-end and the mix by `+f_s/8` translates DC up
   to `+f_s/8`. Deep-tail complex magnitude must be in `[0.95, 1.05]`,
   magnitude std `< 0.02`, and FFT peak must land at bin
   `len(tail) / 8`.
4. **Baseband tone at `-f_bb/8` → `+3 f_s/32`.** Drive
   `x_bb[m] = e^{-j 2π m / 8}`. In output-rate terms the baseband tone
   sits at `-f_s/32`; after mixing by `+f_s/8` it lands at
   `+f_s/8 - f_s/32 = +3 f_s/32`. FFT peak of the tail should be at
   bin `round(tail_len · 3 / 32)`.

### 5.2 Silicon gate

Random complex baseband, `np.random.seed(792)`, 512 pairs, values in
`[-1, +1]`. The kernel output must match the NumPy reference at
`atol = 0.01` — the tolerance used by M8/M19/M20/M21 to accept
bfloat16 vs float32 rounding on the AIE2 float MAC pipeline.

## 6. Sandbox verification (pre-silicon)

Before hand-off to the laptop, three pipeline correctness checks passed
inside the sandbox:

| Check | Result |
| --- | --- |
| Four host reference checks | All pass in isolation (LO regen ≤ 2e-16, impulse = 16 nz, DC→tone mag = 0.9976 at bin 192 = f_s/8, shift check peak at bin 144 = 3 f_s/32) |
| NumPy reference vs Python transliteration of the .cc kernel on the silicon-gate seed-792 vector | Bit-exact, max diff = 0.000000 |
| Output shape | Full 4096 bfloat16 slots populated (no zero-tail); all 2048 complex pairs non-zero |

## 7. Wiring after silicon PASS

To be performed only after the laptop reports `PASS!` on
`test_duc_m22.py`.

- Add M22 as the 20th silicon-suite entry in `run_all_silicon_tests.py`.
- Flip `docs/ROADMAP.md` M22 row from 🚧 to ✅ with References column.
- Add a `## M22` section to `docs/MILESTONES_AND_MATHEMATICS.md`.
- Update this document's status line to `shipped (silicon PASS on Phoenix
  NPU1, YYYY-MM-DD)`.
- Add References for any citations introduced here that were not already
  in the milestones doc.

## 8. References

- Harris, F.J. 2004. *Multirate Signal Processing for Communication
  Systems*. Prentice Hall. Chapter 7 "Polyphase Filter Banks" and
  Chapter 8 §8.4 "The Digital Up-Converter".
  <https://ieeexplore.ieee.org/book/9448967>
- Vaidyanathan, P.P. 1993. *Multirate Systems and Filter Banks*.
  Prentice Hall. §4.3 (Eq. 4.3.13, commutator model).
  <https://dl.acm.org/doi/10.5555/151045>
- Oppenheim, A.V. and Schafer, R.W. 2010. *Discrete-Time Signal
  Processing*, 3rd ed. Pearson. §2.2 (complex multiply) and §4.6
  (multirate interpolation).
  <https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003390/9780131988422>
- Kaiser, J.F. 1974. "Nonrecursive digital filter design using I_0-sinh
  window function." *Proc. IEEE ISCAS*.
  <https://ieeexplore.ieee.org/document/1451724>
- NIST Digital Library of Mathematical Functions §1.9 "Calculus of a
  Complex Variable". <https://dlmf.nist.gov/1.9>
- NIST DLMF §10.25 "Modified Bessel Functions".
  <https://dlmf.nist.gov/10.25>
- Analog Devices Inc. Tutorial MT-085 "Fundamentals of Direct Digital
  Synthesis (DDS)".
  <https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf>
- GNU Radio Project. "Frequency Xlating FIR Filter" — canonical fused
  NCO + FIR + rate-change block; DUC is the negative-decimation case
  of the same topology.
  <https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter>
- GNU Radio Project. "Polyphase Filter Bank" documentation.
  <https://www.gnuradio.org/doc/doxygen-3.7/page_pfb.html>
- SciPy Developers. `scipy.signal.resample_poly` — interpolator tap
  scaling convention (`taps *= up`).
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html>
- AMD Xilinx. "AI Engine (AIE) API User Guide" — `aie_api` /
  bfloat16 operand contract.
  <https://docs.amd.com/r/en-US/ug1076-ai-engine-environment>
- Prior milestone docs and kernels in this repository:
  [`docs/M21_DESIGN.md`](./M21_DESIGN.md),
  [`docs/M20_DESIGN.md`](./M20_DESIGN.md),
  [`docs/M19_DESIGN.md`](./M19_DESIGN.md),
  [`tests/m6_mixer/mixer_kernel.cc`](../tests/m6_mixer/mixer_kernel.cc),
  [`tests/m8_pipeline/pipeline_kernel.cc`](../tests/m8_pipeline/pipeline_kernel.cc),
  [`tests/m20_polyphase/polyphase_kernel.cc`](../tests/m20_polyphase/polyphase_kernel.cc),
  [`tests/m21_ddc/ddc_kernel.cc`](../tests/m21_ddc/ddc_kernel.cc).
