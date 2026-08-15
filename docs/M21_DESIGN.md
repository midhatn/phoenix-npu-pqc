# M21 — Digital Down-Converter (DDC) Design

Status: shipped (silicon PASS on Phoenix NPU1, 2026-08-15, max err 0.003906 on seed-789 random I/Q at atol = 0.01).
Owner: Phoenix SDR-DSP team.
Target hardware: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2 (one core).
Target OS: Windows 11 Pro 25H2, Clang / Peano AIE2, IRON 1.4.1.
Related files:

- `tests/m21_ddc/ddc_kernel.cc` — fused AIE2 kernel (Mix + LPF + Decim).
- `tests/m21_ddc/test_ddc_m21.py` — host driver, NumPy reference, silicon gate.
- `include/sdr_dsp/sdr_dsp_common.hpp` — shared AIE2 vector definitions.

## 1. Purpose

A Digital Down-Converter (DDC) shifts a real-world radio signal that lives at
an intermediate frequency (IF) down to complex baseband, then reduces the
sample rate. It is the workhorse block that turns a wideband ADC stream into
a narrowband channel a demodulator can process. In one sentence:

> `y[m] = decimate_M { LPF { x[n] · e^(-j 2π f_c n / f_s) } }`

Milestone 21 delivers a **single fused AIE2 kernel** that runs all three
stages on one core:

1. Complex mix by a numerically-controlled oscillator (NCO) at `f_c = -f_s/8`.
2. 16-tap real-tap Kaiser low-pass filter (unity DC gain, cutoff `π/M = π/4`).
3. Decimate by `M = 4`.

The design deliberately reuses shipped Phoenix SDR-DSP building blocks: the
complex mixer identity from M6, the shift-and-ingest complex FIR from M19,
and the fused-loop decimator pattern from M20.

## 2. Signal-chain math

### 2.1 Downconversion

For an input stream `x[n] = I_x[n] + j Q_x[n]` sampled at `f_s`, the DDC's
first stage is a complex multiply against a locally generated oscillator
tuned to `-f_c`:

```
y_mix[n] = x[n] · e^(-j 2π f_c n / f_s)
        = x[n] · (cos_lo[n] + j sin_lo[n])
```

with `cos_lo[n] = cos(-2π f_c n / f_s)` and `sin_lo[n] = sin(-2π f_c n / f_s)`.

Expanding the complex multiply gives the operand order the kernel uses
([Oppenheim & Schafer, DTSP 3e, §2.2](https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003374/9780132146357);
[NIST DLMF §1.9](https://dlmf.nist.gov/1.9)):

```
I_mix[n] = I_x[n] · cos_lo[n] - Q_x[n] · sin_lo[n]
Q_mix[n] = I_x[n] · sin_lo[n] + Q_x[n] · cos_lo[n]
```

### 2.2 LO look-up table

With `f_c = f_s / 8`, `cos_lo[n]` and `sin_lo[n]` are periodic with period 8,
so only **8 unique LO samples** exist. The kernel stores them as a `const
float[8]` LUT indexed by `(n & 7)`. This is the standard "cordic-free"
quarter-wave DDS trick documented in
[Analog Devices MT-085 "Fundamentals of Direct Digital Synthesis (DDS)"
Table 1](https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf).
The eight closed-form values are the union of `{±1, ±√2/2, 0}`; the kernel
bakes their bfloat16 quantisations so the reference and silicon see exactly
the same operands (matches the M20 tap-bake convention documented in
[`docs/M20_DESIGN.md` §3.1](./M20_DESIGN.md)).

```
lo_cos = [ +1.0000,  +0.7070,   0.0000,  -0.7070,
           -1.0000,  -0.7070,   0.0000,  +0.7070 ]
lo_sin = [  0.0000,  -0.7070,  -1.0000,  -0.7070,
            0.0000,  +0.7070,  +1.0000,  +0.7070 ]
```

Sandbox regeneration from the closed-form formula matches the baked LUT
term-for-term to floating-point epsilon (Test 1 in the host driver).

### 2.3 Low-pass filter

After mixing, we run a 16-tap real-tap FIR on each of `I_mix` and `Q_mix`.
Because the taps are real and the signal is complex, the pass and stop
bands are identical for I and Q — we get away with **one prototype filter
applied twice**, not a full complex-tap filter (this is precisely the
["frequency-xlating FIR filter"](https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter)
structure GNU Radio ships as its canonical DDC block).

The 16-tap Kaiser prototype is the identical filter shipped as the M20
decimator prototype ([`docs/M20_DESIGN.md` §3.1](./M20_DESIGN.md)):

- Window: Kaiser, β = 6 (~68 dB peak sidelobe attenuation per
  [Kaiser 1974](https://ieeexplore.ieee.org/document/1451724)).
- Cutoff: `π/M = π/4` (the passband must not extend past the new Nyquist
  after `M = 4` decimation; see Harris 2004 §7.1 "Sampling Rate Change").
- Unity DC gain: `sum(h) ≈ 0.999` after bfloat16 quantisation.

Reusing the exact tap array from M20 means Test 3 (on-carrier tone → DC →
LPF passband) inherits M20's proven passband flatness and Test 4 (image
tone → −f_s/4 → LPF stopband) inherits M20's stopband depth.

### 2.4 Decimation by fused polyphase evaluation

Naïvely one would filter first at full rate then throw away 3 out of every
4 outputs. The fused kernel instead evaluates the FIR **only at the
decimated rate**, which is a factor-of-M compute win. The shift register
still ingests M samples per output cycle (Harris 2004 §8.3
"The Digital Down-Converter";
[Vaidyanathan 1993 §4.3
"Efficient Structures"](https://dl.acm.org/doi/10.5555/151045)):

```
for m in 0 .. N_out-1:
    hist[0..11]  = hist[4..15]            # shift left by M
    hist[12..15] = mix_pairs[m*M .. m*M+3]  # ingest 4 mixed pairs
    y[m] = sum_{k=0..15} h[k] · hist[15-k]  # 16-tap dot product
```

This is the same schedule M20's decimation stage uses; M21 differs only in
that the ingest step also runs the complex mixer, and the newest slot is a
mixed pair rather than a raw input pair.

## 3. Dataflow shape

| Item | Value | Rationale |
| --- | --- | --- |
| Input length | 4096 bfloat16 (= 2048 complex pairs) | Matches M6/M8/M19/M20 XRT plumbing. |
| Output length | 4096 bfloat16 total (512 populated pairs + 3072 zero tail) | Same buffer size as input — no XRT changes. |
| `f_c` | `-f_s/8` | Enables cordic-free 8-entry LO LUT. |
| Filter length | 16 taps | Reuses M20 prototype; ~19 dB @ passband edge, deeper further out. |
| Decimation M | 4 | Matches M20 decim stage; sample-rate matches receiver channelizer. |

## 4. AIE2 kernel implementation

Filed at [`tests/m21_ddc/ddc_kernel.cc`](../tests/m21_ddc/ddc_kernel.cc).

### 4.1 One core, one Worker, one xclbin

The whole pipeline fits in a single AIE2 core:

- Local state: `hist_i[16]`, `hist_q[16]`, `lo_cos[8]`, `lo_sin[8]`,
  `h[16]` — all `float` — totalling ~ 224 bytes on stack. Comfortably
  below the 16 KB `stack_size = 0x4000` override retained from the M19/M20
  envelope
  ([`docs/M19_DESIGN.md` §5.3](./M19_DESIGN.md)).
- No ObjectFifo between mix and FIR: the mixed pair is written directly
  into the FIR's shift register in the same iteration where it is
  produced, so the mix stage never materialises a full mixed buffer in
  memory. This is the M8 fused-pipeline pattern ([`tests/m8_pipeline/pipeline_kernel.cc`](../tests/m8_pipeline/pipeline_kernel.cc)).
- Output buffer is zero-filled in slots 1024..4095 by the kernel so the
  host reference and silicon output have identical shape.

### 4.2 Program-memory sizing

The kernel follows the M20 revision-2 lesson
([`docs/M20_DESIGN.md` §8.1](./M20_DESIGN.md)): all dot products are
compact `for (int k = 0; k < 16; ++k)` loops with **no
`#pragma clang loop unroll_count`** hints. This keeps the program image
comfortably below the AIE2 core's 16 KB program memory even with the
16-tap LPF, 8-entry LO LUT, and 16-slot shift-register logic baked in.

## 5. Host driver

Filed at [`tests/m21_ddc/test_ddc_m21.py`](../tests/m21_ddc/test_ddc_m21.py).

### 5.1 Four host-side reference checks before silicon dispatch

1. **LO LUT regeneration.** Recompute `cos(-2π k / 8)` and `sin(-2π k / 8)`
   from NumPy at bfloat16 precision, diff against the baked LUT. Max diff
   must be `< 1e-6`.
2. **Impulse response.** Drive Ix[0]=1, everything else 0. Because LO[0] =
   (1, 0), the impulse passes into the LPF unrotated; the LPF then emits
   its decimated impulse response, which for a 16-tap filter at M=4 is
   exactly 4 non-zero output samples (h[0], h[4], h[8], h[12]). Assertion:
   ≤ 8 non-zero output-I samples.
3. **On-carrier tone at +f_s/8.** Drive `x[n] = e^(+j 2π n / 8)`. After
   mixing by `-f_s/8` this lands at DC; deep-tail complex magnitude must
   be in `[0.95, 1.05]` (unity passband gain), magnitude std `< 0.02`
   (flat), phase `|φ| < 0.05` rad.
4. **Image tone at −f_s/8.** Drive `x[n] = e^(-j 2π n / 8)`. After mixing
   this lands at `−f_s/4`, deep in the LPF stopband; deep-tail magnitude
   must be `< 0.05` (better than 26 dB rejection; sandbox measured
   55.8 dB).

### 5.2 Silicon gate

Random complex I/Q, `np.random.seed(789)`, 2048 pairs, values in
`[−1, +1]`. The kernel output must match the NumPy reference at
`atol = 0.01` — the tolerance used by M8/M19/M20 to accept bfloat16 vs
float32 rounding on the AIE2 float MAC pipeline.

## 6. Sandbox verification (pre-silicon)

Before hand-off to the laptop, three pipeline correctness checks passed
inside the sandbox:

| Check | Result |
| --- | --- |
| Four host reference checks | All pass in isolation (LO regen ≤ 2e-16, impulse = 4 nz, on-carrier mag = 1.0000, image rejection = 55.8 dB) |
| NumPy reference vs Python transliteration of the .cc kernel on the silicon-gate seed-789 vector | Bit-exact, max diff = 0.000000 |
| Output shape | 1024 populated bfloat16 + 3072 zero tail, matching M8/M19/M20 XRT plumbing |

## 7. Wiring after silicon PASS (delivered)

All wiring completed 2026-08-15 in the same session as the silicon PASS:

- M21 wired as the 19th silicon-suite entry in `run_all_silicon_tests.py`.
- `docs/ROADMAP.md` M21 row flipped from 🚧 to ✅ with References column.
- `## M21` section appended to `docs/MILESTONES_AND_MATHEMATICS.md` with
  the DDC math, LO-LUT rationale, and reference-check summary.
- Silicon regression contract advanced from 18/18 to 19/19; laptop
  regression re-run confirms no regressions in M3 through M20.
- References list extended with Harris 2004 §8.3, Analog Devices MT-085,
  and GNU Radio Frequency Xlating FIR Filter.

## 8. References

- Harris, F.J. 2004. *Multirate Signal Processing for Communication
  Systems*. Prentice Hall. Chapter 8 "The Digital Down-Converter".
  <https://ieeexplore.ieee.org/book/9448967>
- Vaidyanathan, P.P. 1993. *Multirate Systems and Filter Banks*. Prentice
  Hall. Section 4.3 "Efficient Structures".
  <https://dl.acm.org/doi/10.5555/151045>
- Oppenheim, A.V. and Schafer, R.W. 2010. *Discrete-Time Signal
  Processing*, 3e. Pearson. Section 2.2 "Discrete-Time Signals".
  <https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003374/9780132146357>
- Kaiser, J.F. 1974. "Nonrecursive digital filter design using I_0-sinh
  window function." *Proc. IEEE ISCAS*.
  <https://ieeexplore.ieee.org/document/1451724>
- NIST Digital Library of Mathematical Functions §1.9 "Calculus of a
  Complex Variable". <https://dlmf.nist.gov/1.9>
- NIST DLMF §10.25 "Modified Bessel Functions (definitions and basic
  properties)". <https://dlmf.nist.gov/10.25>
- Analog Devices Inc. Tutorial MT-085, "Fundamentals of Direct Digital
  Synthesis (DDS)".
  <https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf>
- GNU Radio Project. "Frequency Xlating FIR Filter" block reference.
  <https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter>
- SciPy Developers. `scipy.signal.resample_poly` — reference for the
  real-tap × complex-signal decimation convention.
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html>
- AMD Xilinx. "AI Engine (AIE) API User Guide" (aie_api / bfloat16
  operand contract). <https://docs.amd.com/r/en-US/ug1076-ai-engine-environment>
- AMD Xilinx. "AI Engine Architecture Manual" (AM020) — program-memory
  sizing constraint referenced by
  [`docs/M20_DESIGN.md` §8.1](./M20_DESIGN.md).
  <https://docs.amd.com/r/en-US/am020-versal-aie>
- Prior milestone docs and kernels in this repository:
  [`docs/M20_DESIGN.md`](./M20_DESIGN.md),
  [`docs/M19_DESIGN.md`](./M19_DESIGN.md),
  [`tests/m6_mixer/mixer_kernel.cc`](../tests/m6_mixer/mixer_kernel.cc),
  [`tests/m8_pipeline/pipeline_kernel.cc`](../tests/m8_pipeline/pipeline_kernel.cc),
  [`tests/m19_complex_fir/fir_complex_kernel.cc`](../tests/m19_complex_fir/fir_complex_kernel.cc),
  [`tests/m20_polyphase/polyphase_kernel.cc`](../tests/m20_polyphase/polyphase_kernel.cc).
