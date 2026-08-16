# M27 — OFDM: FFT + CP + Pilots + Channel Estimation + Equalization

**Status:** ⏸️ In bring-up (kernel written, awaiting silicon PASS on laptop)
**Depends on:** M17 (64-pt radix-4 Stockham FFT), M25/M26 (fused receiver kernel discipline)
**Deliverables:** `tests/m27_ofdm/`, `tools/m27_kernel_transliteration_check.py`, this document

---

## 1. Purpose

M27 delivers a fused OFDM loopback (TX + on-tile channel + RX) on a single AIE2 core on the AMD Phoenix NPU. The kernel executes the full physical-layer chain of an 802.11a-style OFDM burst — Gray-labelled QAM-16 payload mapped onto 48 data subcarriers, 4 BPSK pilots inserted at `k ∈ {−21, −7, +7, +21}`, IFFT to time domain, cyclic-prefix prepending, propagation through a compiled-in 4-tap complex FIR channel, CP stripping at RX, forward FFT, least-squares (LS) channel estimation on the pilot subcarriers, linear interpolation across the 48 data-carrying subcarriers, and per-subcarrier zero-forcing (ZF) equalization ([IEEE 802.11-2020 §17](https://standards.ieee.org/ieee/802.11/7028/); [van de Beek et al 1997](https://doi.org/10.1109/78.611176); [Coleri et al 2002](https://ieeexplore.ieee.org/document/1035788)).

This is the first OFDM milestone in the M-suite and the first kernel to textually `#include` the M17 FFT source in-file rather than relying on `@iron.jit`'s `ExternalFunction` composition. M17's own wrapper (`tests/m17_radix2_fft/fft64_r4_wrapper.cc`) documents this pattern: `iron.jit`'s `ExternalFunction` (as of `mlir-aie` 1.4.1) does not expose a first-class way to inject preprocessor defines into a kernel source file, so the wrapper defines `FFT_SIZE 64` and textually includes the kernel. M27 does the same and reuses the FFT twice — once as forward for the RX FFT, once as inverse via the conjugate trick `IFFT(X) = conj(FFT(conj(X))) / N` for the TX IFFT.

## 2. Mathematical background

### 2.1 OFDM signal model

Following [Weinstein & Ebert 1971](https://doi.org/10.1109/TCOM.1971.1090705) (the paper that first proposed DFT-based OFDM implementation) and [Chang 1966](https://ieeexplore.ieee.org/document/6768493) (the parent multicarrier concept), a discrete-time OFDM symbol of `N` subcarriers is

\[
x[n] = \frac{1}{N} \sum_{k=0}^{N-1} X[k]\, e^{j 2\pi k n / N}, \qquad n = 0, 1, \dots, N-1
\]

which is exactly the inverse DFT of the frequency-domain symbol vector `X[k]`. Reception is the forward DFT `Y[k] = \sum_n y[n] e^{-j 2\pi k n / N}`. On our hardware both directions reuse the M17 forward FFT: the inverse is `x = conj(FFT(conj(X))) / N`, an identity from [Oppenheim & Schafer 3e §8.5](https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003543).

### 2.2 Cyclic prefix

Following [Peled & Ruiz 1980](https://doi.org/10.1109/ICASSP.1980.1171076), a length-`Ncp` cyclic prefix `x[N-Ncp], x[N-Ncp+1], …, x[N-1]` is prepended to each `x` before transmit. The mathematical purpose is to convert a linear convolution with the channel `h[n]` into a *circular* convolution modulo `N` — provided the channel impulse response satisfies `L_h ≤ Ncp + 1`. Under that condition, the received frequency-domain vector after CP removal is exactly the per-subcarrier product

\[
Y[k] = H[k] \cdot X[k] + W[k], \qquad k = 0, 1, \dots, N-1
\]

where `H[k]` is the DFT of the channel impulse response and `W[k]` is the DFT of the additive noise. Because there is no inter-carrier crosstalk, one-tap-per-subcarrier equalization is optimal in the zero-forcing sense.

### 2.3 Pilot-based LS channel estimation

Following [Coleri et al 2002](https://ieeexplore.ieee.org/document/1035788) (comb-type pilot arrangement) and [van de Beek et al 1997](https://doi.org/10.1109/78.611176), the least-squares channel estimate on the pilot subcarriers is

\[
\hat H_p[k_p] = \frac{Y[k_p]}{X_p[k_p]}, \qquad k_p \in \{-21, -7, +7, +21\}
\]

with pilots `X_p[k_p] = ±1` (BPSK). Because pilots are BPSK, the division reduces to a signed pass-through of `Y[k_p]`. Estimates on data subcarriers are obtained by piecewise linear interpolation in `k`:

\[
\hat H_d[k] = \hat H_p[k_a] + (k - k_a) \cdot \frac{\hat H_p[k_b] - \hat H_p[k_a]}{k_b - k_a}
\]

where `(k_a, k_b)` is the pair of adjacent pilots bracketing data subcarrier `k`. For data subcarriers outside the outermost pilots — `k < -21` or `k > +21` — the estimate is extrapolated by using the nearest pair of pilots on the interior side (equivalent to holding the linear-interp slope past the boundary). This is the same policy documented in [Rice 2e Ch 8](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544).

### 2.4 Zero-forcing equalization

Per-subcarrier ZF is the elementwise divide `X̂[k] = Y[k] / Ĥ_d[k]`. Its noise-enhancement penalty is well-known ([Proakis & Salehi 5e §13.5](https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html)) — subcarriers where `|Ĥ_d[k]|` is small get their noise amplified — but the alternative (MMSE) requires an SNR estimate that we do not have on-tile. ZF is the standard choice for a first OFDM RX implementation and is what [IEEE 802.11a](https://standards.ieee.org/ieee/802.11/7028/) reference receivers implement.

Divide is written in kernel as `(Y * conj(Ĥ)) / |Ĥ|²`. The division-by-magnitude-squared avoids a complex-divide primitive that Peano NOCPP does not vector-lower cleanly.

## 3. 802.11a subcarrier map

Following [IEEE 802.11-2020 §17.3.5](https://standards.ieee.org/ieee/802.11/7028/), the 64-point IDFT input vector `X[k]` uses subcarrier indices `k ∈ {-32, -31, …, -1, 0, +1, …, +31}` with the following per-index assignment:

| Index `k` | Assignment | Count |
|-----------|-----------|-------|
| `-32` | Guard (zero) | 1 |
| `-31 … -27` | Guard (zero) | 5 |
| `-26 … -22, -20 … -8, -6 … -1` | Data | 24 (of 48) |
| `-21, -7` | Pilot (BPSK) | 2 (of 4) |
| `0` | DC (zero) | 1 |
| `+1 … +6, +8 … +20, +22 … +26` | Data | 24 (of 48) |
| `+7, +21` | Pilot (BPSK) | 2 (of 4) |
| `+27 … +31` | Guard (zero) | 5 |

Total: 48 data + 4 pilot + 11 guard + 1 DC = 64. The IDFT-input buffer follows the standard fftshift layout: DC at index 0, positive frequencies at indices `1..31`, negative frequencies at indices `32..63` (which correspond to `k = -32 .. -1`). All indexing in the kernel and host is done in the "natural" `[0..63]` FFT order after this once-off remap.

Pilot polarity follows the [IEEE 802.11-2020 §17.3.5.10](https://standards.ieee.org/ieee/802.11/7028/) sign convention: `p = (+1, +1, +1, -1)` for pilots at `k ∈ {-21, -7, +7, +21}` on OFDM symbol 0. Higher symbols multiply this vector by a scrambling sequence; for M27's first-bring-up test we hold the pilot pattern constant across all 8 symbols in the burst, which is a valid simplification since we do not exercise frame-level scrambling.

## 4. Fused-kernel architecture

M27 ships as a single `@iron.jit ofdm_loopback` entry on one AIE2 core (compile-time constants: `N_FFT = 64`, `N_CP = 16`, `N_SYM = 8`). The kernel body, from top to bottom:

1. **Pilot / data multiplex.** Load 48 QAM-16 data symbols per OFDM symbol from `in_data`. Insert `±1` pilots at `k ∈ {-21, -7, +7, +21}`. Insert zeros at DC and 11 guard indices. Write to a length-64 complex buffer `X[k]` in natural FFT order.
2. **IFFT via conjugate trick.** Conjugate `X → X*`. Call the M17 forward FFT (`fft_stockham_f32`, textually included at compile time via `#define FFT_SIZE 64` + `#include "../../kernels/fft_stockham_f32.cc"`). Conjugate the output and divide by `N=64` to get `x[n] = IDFT(X)`.
3. **CP-add.** Prepend the last 16 samples of `x[n]` to form `s[n]` of length `N + Ncp = 80`. Concatenate across 8 OFDM symbols to a 640-sample TX stream.
4. **Channel FIR.** Convolve `s[n]` with a compiled-in 4-tap complex FIR whose taps are supplied via a DMA buffer `in_channel` (8 bf16 = 4 complex bf16). Because the channel impulse response is length 4 and the CP is length 16, the linear-to-circular conversion holds.
5. **CP-strip.** Discard the first 16 samples of each 80-sample block, keeping the remaining 64 samples per OFDM symbol.
6. **Forward FFT.** Call `fft_stockham_f32` per OFDM symbol to obtain `Y[k]`.
7. **Pilot LS.** For each of the 4 pilots, compute `Ĥ_p[k_p] = Y[k_p] * X_p[k_p]` (BPSK: `X_p = ±1` so this is a signed pass-through with no real divide).
8. **Linear interpolation.** For each of the 48 data subcarriers, find the bracketing pilot pair (or the nearest edge pair for extrapolation) and compute `Ĥ_d[k]` by linear interpolation in the subcarrier index `k`.
9. **ZF equalization.** For each data subcarrier: `X̂[k] = Y[k] * conj(Ĥ_d[k]) / (Ĥ_d[k].re² + Ĥ_d[k].im²)`.
10. **Emit.** Write 48 equalized complex bf16 slots per OFDM symbol to `out_data`, for a total of 384 equalized data subcarriers across the 8-symbol burst.

Steps 1–3 are the TX side; step 4 is the channel model; steps 5–10 are the RX side. All internal math is `float32`; I/O is `bfloat16`. The kernel uses no shift-registers or state across the outer loop — every OFDM symbol is independent.

### 4.1 Reuse of the M17 FFT

The `#include`-then-call pattern matches M17's own `fft64_r4_wrapper.cc` exactly. Because the M17 kernel file contains its own `extern "C" { void fft_stockham_f32(...) { … } }`, textually including it inside `ofdm_loopback_kernel.cc` produces a per-tile inline instance of `fft_stockham_f32` compiled for `FFT_SIZE 64`. The M27 kernel calls this symbol six times per OFDM burst (2 × 8 = 16 FFTs total: 8 IFFTs on TX, 8 forward FFTs on RX; the 6× / 16× discrepancy in an earlier draft was corrected here).

The FFT kernel is defined once inside the M27 kernel's translation unit. Program-memory budget check: M17's fused radix-4 Stockham at `N=64` compiles to ~5 KB program memory ([M17_DESIGN.md](M17_DESIGN.md) §5). Including it once in M27 gives one copy of the FFT code, not sixteen — the same function is called sixteen times. This fits inside the AIE2 tile's 16 KB program memory budget with the additional pilot LS + linear interp + ZF equalization overhead.

## 5. Why gate (c) is assertable (contrast with M25/M26)

M25 and M26 gate (c) had to become diagnostic because the receiver contained two independent closed-loop control systems (Gardner timing integrator + Costas / decision-directed phase integrator). CPU float32-serial and AIE2 float32-SIMD rounding integrate to different steady-state equilibria after ~1/BW_φ symbols, per [NASA JPL TDA Progress Report 42-130](https://ipnpr.jpl.nasa.gov/progress_report/42-130/130B.pdf) and [Kuznetsov et al 2018](https://arxiv.org/abs/1810.00071). This is a fundamental property of coupled feedback dynamics with different float rounding — no kernel-side fix can restore bit-exact SER.

OFDM RX is **open-loop** given a synchronized frame. There is no timing integrator (frame boundary is known); there is no carrier-tracking integrator (residual CFO is folded into the channel estimate). The whole receiver is a fixed sequence of arithmetic operations: FFT → pilot pass-through → linear interpolation → complex divide. The same input samples produce the same output samples up to bf16 quantization, whether run on CPU or AIE2. Therefore:

- **Gate (a) transliteration** stays asserted — the kernel is deterministic and bit-exact vs the host reference (0/`N` slots differ on ≥2 seeds).
- **Gate (c) SER < 0.01** stays asserted at SNR = 20 dB. Rayleigh-flat + Gaussian noise are injected by the host on the transmitted samples between two dispatches (or as a distinct test case with channel taps = `[1, 0, 0, 0]`), so both silicon and host see the same noisy input and produce the same equalized output.

The two-dispatch pattern for the noise-tolerance gate: dispatch 1 runs the kernel with the identity channel `[1, 0, 0, 0]` and captures the TX output at the CP-add stage; the host then adds Rayleigh × AWGN; dispatch 2 runs the kernel again with identity channel and feeds the noisy samples in via a separate input path. This is described in §6.

## 6. Test plan

Implemented as `tests/m27_ofdm/test_ofdm_m27.py`. The suite has **4 reference-only tests** plus **4 silicon gates**.

### 6.1 Reference tests (host-only)

- **R1** — 64-pt IDFT-then-DFT round-trip on random QAM-16 constellations matches to bf16 precision.
- **R2** — Pilot LS on a synthetic frequency-flat channel `H[k] = c` returns `Ĥ_p = c` on all 4 pilots to `1e-6` relative error.
- **R3** — Linear interpolation across 48 data subcarriers matches `numpy.interp` on the same knots.
- **R4** — ZF equalization on `Y[k] = H[k] X[k]` with known `H` and `X` recovers `X` exactly.

### 6.2 Silicon gates

- **Gate (a) — transliteration bit-exact.** With deterministic seed 827, kernel output on silicon matches host reference bit-for-bit on all 384 equalized data subcarriers (`0/768 bf16 slots differ`).
- **Gate (b) — EVM ≤ 3% on delay-spread channel.** With channel taps `[1.0, 0.4, 0.2, 0.1] + j·[0.0, 0.1, 0.05, 0.02]` (`L_h = 4 ≤ N_cp + 1 = 17`), no noise, EVM on the 384 equalized data subcarriers ≤ 3%.
- **Gate (c) — SER < 0.01 asserted at SNR = 20 dB.** Rayleigh-flat channel + AWGN (host-injected on TX output between two identity-channel dispatches). Hard-slice each equalized data subcarrier to nearest QAM-16 constellation point. Assert `SER < 0.01`.
- **Gate (c-diag) — EVM_dB printout.** Same test as (c), diagnostic-only, target `EVM_dB ≥ 25 dB` per [IEEE 802.11-2020 §17.3.9.7.3](https://standards.ieee.org/ieee/802.11/7028/) minimum for QAM-16.
- **Gate (d) — pilot-only sanity.** Channel taps `[1, 0, 0, 0]`, data slots all zero, pilots `±1`. After LS + linear-interp + ZF, verify the equalized pilot subcarriers return as `±1` to `1e-3` relative error.

## 7. Bring-up incidents

*(To be filled in after silicon PASS on laptop. Anticipated per M25/M26 pattern: Peano NOCPP has no libc `<math.h>` → open-coded Taylor sin/cos + π/2 fold; `-O2` folds union-based `sign_of` into `llvm.copysign` which AIE2 rejects → `volatile uint32_t` OR into `0x3F800000`; `@iron.jit` decorator required on the driver function or `Program.resolve_program()` returns raw MLIR and no compile happens.)*

## 8. References

### OFDM and multicarrier
- Chang, "Synthesis of Band-Limited Orthogonal Signals for Multichannel Data Transmission", *Bell Syst. Tech. J.* 45(10), Dec 1966. https://ieeexplore.ieee.org/document/6768493
- Weinstein & Ebert, "Data Transmission by Frequency-Division Multiplexing Using the Discrete Fourier Transform", *IEEE TCOM* 19(5), Oct 1971. https://doi.org/10.1109/TCOM.1971.1090705
- Peled & Ruiz, "Frequency Domain Data Transmission Using Reduced Computational Complexity Algorithms", *IEEE ICASSP* 1980. https://doi.org/10.1109/ICASSP.1980.1171076
- Cimini, "Analysis and Simulation of a Digital Mobile Channel Using OFDM", *IEEE TCOM* COM-33(7), 1985. https://doi.org/10.1109/TCOM.1985.1096357
- van de Beek, Sandell, Börjesson, "ML Estimation of Time and Frequency Offset in OFDM Systems", *IEEE TSP* 45(7), 1997. https://doi.org/10.1109/78.611176

### Pilot-based channel estimation
- Coleri, Ergen, Puri, Bahai, "Channel Estimation Techniques Based on Pilot Arrangement in OFDM Systems", *IEEE Trans. Broadcasting* 48(3), Sept 2002. https://ieeexplore.ieee.org/document/1035788

### Textbook and standards references
- Proakis & Salehi, *Digital Communications*, 5th ed., §13.5 "OFDM", McGraw-Hill 2008. https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html
- Rice, *Digital Communications: A Discrete-Time Approach*, 2nd ed., Ch. 8 OFDM. https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544
- Oppenheim & Schafer, *Discrete-Time Signal Processing*, 3rd ed., §8.5 "Properties of the DFT" (IDFT via conjugate). https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003543
- IEEE Std 802.11-2020, "Wireless LAN Medium Access Control (MAC) and Physical Layer (PHY) Specifications", §17 "OFDM PHY specification". https://standards.ieee.org/ieee/802.11/7028/

### FFT algorithms (M17 lineage)
- Cooley & Tukey, "An Algorithm for the Machine Calculation of Complex Fourier Series", *Math. Comp.* 19(90), 1965. https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf
- Stockham, "High Speed Convolution and Correlation", *AFIPS Spring Joint Computer Conf.* 1966. https://doi.org/10.1145/1464291.1464335

### Internal cross-refs
- [M17_DESIGN.md](M17_DESIGN.md) — radix-4 Stockham FFT at N=64; twiddle-pack format; `fft_stockham_f32` symbol.
- [M25_DESIGN.md](M25_DESIGN.md) §4b — bring-up incidents 1–4 (open-coded Taylor sin/cos; sign-bit reinterpret; `-O2` copysign folding; closed-loop float rounding drift).
- [M26_DESIGN.md](M26_DESIGN.md) Amendment #1 — receiver-theoretic gate discipline for closed-loop kernels; motivates the open-loop rationale in §5 above.
- [MILESTONES_AND_MATHEMATICS.md](MILESTONES_AND_MATHEMATICS.md) — canonical math ledger.
- [ROADMAP.md](ROADMAP.md) §16 — one-line canonical spec.
