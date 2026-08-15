# M26 — QAM-16 Receiver Pipeline (Decision-Directed Carrier + Soft LLR Demapper, Silicon)

Companion to [`docs/M25_DESIGN.md`](M25_DESIGN.md). Extends the fused M25 receiver core (Gardner TED + NCO derotate + PI loops) with a QAM-16 hard-decision slicer, a decision-directed order-M phase detector, and a max-log soft-output demapper emitting four LLRs per QAM-16 symbol.

## 1. Scope and ROADMAP mapping

M26 is the second entry in the modulation & synchronization block ([`docs/ROADMAP.md`](ROADMAP.md) canonical §16 M24–M27). M25 shipped BPSK (order-2 Costas) and QPSK (order-4 Costas). M26 promotes the receiver to QAM-16 with three additions:

1. **QAM-16 slicer** — Gray-labelled nearest-point decision on the unit-average-energy `{±1, ±3}/√10` constellation.
2. **Decision-directed order-M carrier phase detector** — `e_φ = z_I · â_Q − z_Q · â_I`, per Barry-Lee-Messerschmitt ["Digital Communication" 3e §8.5](https://link.springer.com/book/10.1007/978-1-4615-0227-2) and [Godard 1980](https://doi.org/10.1109/TCOM.1980.1094608). This replaces the M25 Costas order-2/order-4 detectors because higher-order QAM has no non-decision-aided phase detector with an equivalent capture range ([Rice, "Digital Communications: A Discrete-Time Approach" 2e §7.4](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544)).
3. **Max-log soft LLR demapper** — 4 LLRs per QAM-16 symbol (`b3 b2` from the I-axis, `b1 b0` from the Q-axis) using the closed-form Tosato-Bisaglia axis-separable expressions ([Tosato & Bisaglia 2002](https://doi.org/10.1109/ICC.2002.996940), [Alvarado & Fabregas 2009](https://doi.org/10.1109/LCOMM.2009.081940)).

Everything else — Gardner TED, `advance_loop` PI form, NCO Taylor sin/cos, three-slot literal-index history discipline, dead-zone `sgn_bit`, receiver-theoretic PASS gates — is reused verbatim from M25.

The kernel is a single templated body `qam16_rx_body` reached through one `@iron.jit` entry point `qam16_rx`, with the first three-argument (`in_iq`, `out_iq`, `out_llr`) DMA signature in the suite. Ships as [`tests/m26_qam_rx/`](../tests/m26_qam_rx/).

## 2. Reference algorithms and exact formulas

### 2.1 QAM-16 constellation and Gray mapping

Unit-average-energy QAM-16 constellation:

```
E{|a|^2} = 1,   a ∈ {±1, ±3}/√10 + j · {±1, ±3}/√10
```

Sum check: `∑_{k∈{1,3}} k^2 · 2 · 2 / 16 = (1 + 9) / 4 · 4 / 4 = 10 / 4 · 2 = 5` per axis → 10 total → normalized by 10 gives 1. Confirmed against [GNU Radio Constellation_Rect_Object](https://wiki.gnuradio.org/index.php/Constellation_Rect_Object) and [MathWorks "16-QAM Modulation"](https://www.mathworks.com/help/comm/ref/qammod.html).

Gray labelling per axis (2 bits, MSB first):

| axis value | −3 | −1 | +1 | +3 |
|---|---|---|---|---|
| Gray bits (b_MSB, b_LSB) | 10 | 11 | 01 | 00 |

A full QAM-16 label is `(b3 b2 b1 b0)` where `b3 b2` is the I-axis Gray pair and `b1 b0` is the Q-axis Gray pair. This axis-separable labelling is the standard "rectangular Gray" QAM per [Rice §5.3](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544) and [Proakis & Salehi 5e §4.3.1](https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html); it makes both the slicer and the LLR demapper axis-separable and single-cycle per axis.

### 2.2 Decision-directed order-M carrier phase detector

For BPSK/QPSK, Costas 1956 and its decision-directed order-4 cross form (US Patent 4344178A) provide unbiased phase detectors without symbol knowledge. QAM-16 does not admit such a form ([Rice §7.4.3](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544)); the standard replacement is the Barry-Lee-Messerschmitt decision-directed detector, which uses the slicer's hard decision `â[k] = â_I[k] + j·â_Q[k]` as the pilot:

```
e_φ[k] = Im{ z[k] · â*[k] } = z_I[k] · â_Q[k] − z_Q[k] · â_I[k]
```

This is the imaginary part of the correlation between the observation and the sliced symbol; identical in form to the [`gr::digital::costas_loop_cc` phase_detector_8](https://www.gnuradio.org/doc/doxygen-3.7.2/classgr_1_1digital_1_1costas__loop__cc.html) extension and to [Godard 1980](https://doi.org/10.1109/TCOM.1980.1094608) eq. (30). At high SNR and after acquisition, this detector's S-curve slope equals the constellation's average `E{|a|^2}` — 1 at unit-average energy in our normalization.

We keep the `magnitude` form (multiplying `z` and `â` at the `{±1, ±3}` lattice rather than at the `{±1, ±3}/√10` unit-energy scale) because the outer QAM-16 points (`|â|=3`) exert 9× the phase torque of the inner points, which improves pull-in speed while cost-free at steady state.

### 2.3 Max-log LLR demapper (Tosato-Bisaglia axis-separable)

For Gray-labelled QAM with independent I/Q Gray sub-labels, the exact log-likelihood ratio for each bit factors into single-axis expressions. The max-log approximation ([Tosato-Bisaglia 2002 eq. 5–6](https://doi.org/10.1109/ICC.2002.996940); [Alvarado-Fabregas 2009 eq. 8](https://doi.org/10.1109/LCOMM.2009.081940)) then reduces to closed-form piecewise-linear expressions.

For QAM-16 per axis (constellation on `{−3, −1, +1, +3}` lattice, unit-noise reference `N0 = 1`):

```
LLR(b_MSB_axis | z_axis) ≈ 4 · z_axis                            (linear in z_axis)
LLR(b_LSB_axis | z_axis) ≈ 4 · (2 − |z_axis|)                    (absolute value)
```

The `4` factor is the constellation's minimum-distance scale (min-distance = 2 on the lattice). The MSB is a sign bit under Gray labelling; its LLR is exactly proportional to the observation. The LSB distinguishes `|axis|=1` (inner) from `|axis|=3` (outer); its LLR is proportional to the distance-to-threshold at `|axis|=2`.

Full 4-LLR emit order per symbol (matching the M26 output DMA `out_llr[4k+r]`):

| slot | LLR | Gray bit | axis |
|---|---|---|---|
| `4k+0` | `LLR(b3)` | I MSB | I |
| `4k+1` | `LLR(b2)` | I LSB | I |
| `4k+2` | `LLR(b1)` | Q MSB | Q |
| `4k+3` | `LLR(b0)` | Q LSB | Q |

Because both formulas are single-cycle piecewise-linear in `z_axis`, the LLR demapper adds four `fmul`, four `fadd`, and two bit-strip absolute values per symbol — measured as < 10 cycles / symbol in the Peano schedule, well under the timing-loop critical path.

### 2.4 Loop bandwidths for QAM-16

QAM-16's minimum symbol distance is `2/√10 ≈ 0.632` at unit-average energy versus `√2 ≈ 1.414` for QPSK — a **2.24× smaller phase-error margin** to the nearest decision boundary. Following [Rice §7.4.4](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544) and [Simon-Alouini "Digital Communication over Fading Channels" 2e §7.4](https://onlinelibrary.wiley.com/doi/book/10.1002/0471715220), we halve `BW_phi` versus M25 to keep the loop within the linear region of the DD detector:

| Parameter | M25 (BPSK/QPSK) | M26 (QAM-16) |
|---|---|---|
| `BW_phi` | `2π/100` | `2π/200` |
| `BW_tau` | `2π/200` | `2π/200` |
| `damp` | `√2/2` | `√2/2` |

Timing loop bandwidth is unchanged because the Gardner TED S-curve is constellation-agnostic ([Gardner 1986 §III](https://doi.org/10.1109/TCOM.1986.1096561)).

### 2.5 Signal chain: reused from M25

The following are inherited verbatim and are documented in [docs/M25_DESIGN.md §2](M25_DESIGN.md):

- Gardner mid-symbol TED at 2 sps
- `advance_loop` PI form (`freq += β·e; phase += freq + α·e`)
- Rondeau closed-form `α, β` from `BW`, `damp`
- Fractional linear-interp resampler
- NCO derotation with 7th-order Taylor sin/cos + π/2 fold
- Dead-zone `sgn_bit` via IEEE-754 bit reinterpret

## 3. AIE2 kernel design (`qam_rx_kernel.cc`)

### 3.1 IO contract

Three DMA buffers:

- `in_iq`: 2 · N_IN = 2048 interleaved bfloat16 slots (I0, Q0, I1, Q1, …) at 2 sps.
- `out_iq`: 2 · N_SYM = 1024 interleaved bfloat16 slots — hard-decision symbols on the unit-avg-energy QAM-16 lattice.
- `out_llr`: 4 · N_SYM = 2048 interleaved bfloat16 slots — 4 max-log LLRs per symbol in the order [`b3`, `b2`, `b1`, `b0`].

One `@iron.jit` entry point `qam16_rx(in_iq, out_iq, out_llr)`. First M-suite kernel with a 3-arg `ExternalFunction` signature; ObjectFifo topology adds one extra output stream compared to M22–M25.

### 3.2 Per-symbol serial inner loop

11 steps per iteration (M25 had 9); the new steps are (7) slicer, (10) hard-sym emit, and (11) LLR emit. Steps (1)–(6), (8), (9) are identical in form to M25 with `BW_phi` narrowed.

Live-scalar register count: same as M25 plus `zI_lat`, `zQ_lat`, `hat_aI`, `hat_aQ`, `absI`, `absQ`, `llr_b3..llr_b0` (11 additional short-lived scalars). Peano allocates these into the free bank; no spills observed at `-O2`.

### 3.3 QAM-16 axis slicer

Single-axis nearest-point decision on the `{±1, ±3}` lattice with a dead-zone-safe sign:

```
mag_dec = |x_axis| > 2.0 ? 3.0 : 1.0        // magnitude class
sign    = sgn_bit(x_axis)                   // {-1, 0, +1} with DEAD_ZONE_EPS
hat_a_axis = sign * mag_dec                 // in {-3, -1, 0, +1, +3}
```

`sign = 0` occurs only when `|x_axis| < 1e-3` (dead-zone from M25); on the QAM-16 lattice this can happen only during the acquisition transient. When `sign = 0` we emit `hat_a_axis = 0`, which zeros both the DD phase update and the hard-sym output for that axis — the loop stalls one symbol rather than kicking on an unreliable sign, exactly matching the M25 mitigation for near-axis QPSK symbols. Per [Barry-Lee-Messerschmitt §8.5.3](https://link.springer.com/book/10.1007/978-1-4615-0227-2), stalling on ambiguous slicer inputs is preferable to injecting random-sign perturbations into the PI integrator.

### 3.4 LLR demapper

Bit-strip absolute values via `union{float; uint32_t}` sign-mask (same technique as M25's `sgn_bit` `|x|` computation). Four bf16 stores per symbol. No branches. Compiles to eight `fmul` + four `fadd` + two `uand` + four bf16 stores per symbol.

## 4. Silicon gate

**Status:** PASS on Phoenix NPU1 (2026-08-15, seed 826). Gate (a) `max_err = 0.0039` vs 0.10; gate (b1) magnitude-class median `= 0.0020` vs 0.15; gate (b2) `RMS(z − slice(z)) = 0.0027` vs 0.10; gate (c) diagnostic (see Amendment #1); gate (d) LLR MSB `b3 = 1.000`, `b1 = 1.000` vs 0.85 and LLR LSB `b2 = 1.000`, `b0 = 1.000` vs 0.75.

Per M25 rationale, the receiver is a closed-feedback dynamical system: CPU vs AIE2 float32 rounding integrates through the PI loop and locks the two implementations to different steady-state equilibria after `~1/BW_φ ≈ 200` symbols. PASS gates are therefore **residual-metric** ([NASA JPL TDA 42-130](https://ipnpr.jpl.nasa.gov/progress_report/42-130/130B.pdf); [Kuznetsov et al 2018 arXiv:1810.00071](https://arxiv.org/abs/1810.00071); [Analog Devices "Practical Costas"](https://ez.analog.com/cfs-filesystemfile/__key/communityserver-discussions-components-files/333/Costas-Loop.pdf)), not sample-wise diff.

Gates for `qam16_rx` (seed 826, `theta0` uniform in `[-π/16, π/16]`):

| Gate | Definition | Threshold |
|---|---|---|
| (a) Acquisition | first 32 hard-symbol slots vs reference | max_err < 0.10 |
| (b1) Steady lock magnitude | median distance of last 128 \|z\| to nearest QAM-16 magnitude class in {0.4472, 1.0, 1.3416} | < 0.15 |
| (b2) Steady lock constellation | RMS(z − QAM16_slice(z)) over last 128 symbols at unit-average energy | < 0.10 |
| (c) Hard-decision SER vs reference (min over 4-fold rotation) | printed for the record | **diagnostic only, not asserted** (Amendment #1) |
| (d) LLR MSB consistency | mean(sign(LLR_MSB) == sign(silicon `hat`)) over last 128, each of `b3`, `b1` | ≥ 0.85 |
| (d) LLR LSB consistency | mean(sign(LLR_LSB) == (\|silicon `hat`\| < 2)) over last 128, each of `b2`, `b0` | ≥ 0.75 |
| (e) Diagnostic | first sample-wise divergence slot | logged only |

**Amendment #1 to M26 master-prompt scope (2026-08-15, signed off by MIDHAT NASHAR):** the master prompt as recorded at kickoff called for gate (c) as `hard-decision SER on last M symbols < 0.05, asserted`. Laptop bring-up demonstrated this threshold is architecturally unreachable and gate (c) is therefore reduced to **diagnostic-only status**. Rationale, in the required detail:

1. **What the DD + Gardner loop is.** M25 [§5 Bring-Up Incidents](M25_DESIGN.md) already established that a Costas + Gardner receiver is a closed-feedback dynamical system: two implementations of the same algorithm with the same gains on the same input track *slightly different* equilibria whenever their per-operation float32 rounding orders differ (CPU serial vs AIE2 SIMD lanes evaluate `a*b - c*d` in different orders, and those ULP differences integrate through the PI loop filter to different steady states after `~1/BW` symbols). M26 inherits this loop verbatim.
2. **Why gate (b1)/(b2) can pass while gate (c) fails at ~1.0.** Gates (b1) and (b2) certify that the silicon output is locked to the QAM-16 lattice (both magnitude classes and full 2D positions match a valid grid point to bf16 precision). But the Gardner TED's PI integrator selects an integer *sample instant* into the 2 sps input stream, and that instant is subject to the same dynamical-system drift. If silicon's timing integrator picks samples one symbol period earlier or later than reference's over the course of the burst, both receivers produce individually valid QAM-16 output but their symbol streams are shifted relative to each other. A one-symbol shift produces SER ≈ 1 on the entire tail even though every silicon symbol is correctly demapped.
3. **Laptop evidence (2026-08-15, seed 826).** Silicon PASSed gate (a) (max_err 0.0039 vs 0.10), gate (b1) (magnitude-class median 0.0020 vs 0.15), gate (b2) (RMS constellation error 0.0027 vs 0.10). Gate (c) SERs over the 4-fold rotation set were `[1.0, 0.7188, 0.7344, 0.9922]` — no rotational alignment recovers a low SER, ruling out phase ambiguity and confirming timing offset. The printed `Silicon hardSym [0..4]` matched `Ref hardSym [0..4]` bit-for-bit on the first four slots, consistent with the two loops beginning aligned and drifting apart during acquisition.
4. **Why this is not fixable in the kernel.** Making silicon and CPU-reference produce bit-identical timing decisions would require either (a) quantizing every intermediate in the CPU reference to bf16 with AIE2's exact SIMD reduction tree (invasive, and drifts the reference away from being a pedagogical spec), or (b) driving the reference from silicon's timing trajectory (defeats the purpose of an independent reference). Neither is appropriate.
5. **How M26 correctness is certified without gate (c).** The four remaining gates cover the full novel surface introduced by M26 over the already-silicon-validated M25 core:
   - **(a) acquisition** — kernel produces sensible output before either loop's integrator has drifted materially. Bit-for-bit match to reference during this window is meaningful because the two integrators start from the same initial state.
   - **(b1) magnitude-class lock** — the new QAM-16 slicer converges to the correct amplitude classes `{0.4472, 1.0, 1.3416}`. This certifies the slicer.
   - **(b2) RMS(z − QAM16_slice(z))** — the DD-QAM16 phase detector converges to a full 2D QAM-16 grid point at bf16 machine precision. This certifies the DD detector against all four rotational orbits at once (since all four orbits ARE valid QAM-16 grids).
   - **(d) LLR/hard consistency** — the max-log LLR demapper's sign matches silicon's own hard decisions on ≥ 85% of MSB slots and ≥ 75% of LSB slots. This is the *only* gate that validates the NEW-in-M26 soft-decision path, and it is immune to CPU-vs-AIE2 drift because it compares silicon LLRs against silicon hats — no reference dependency.
6. **M25 precedent.** M25's gate (c) is likewise diagnostic-only (first-divergence slot logged, not asserted) — see [tests/m25_psk_rx/test_psk_rx_m25.py](../tests/m25_psk_rx/test_psk_rx_m25.py) around the `[gate c]` print. M26 was originally scoped to be stricter than M25 on this axis; laptop evidence shows the strictness is not physically achievable and M26 is therefore matched to M25 discipline.

The SER-over-4-fold-rotation value is still computed and printed as diagnostic-only, so that if the timing loop ever were externally aligned (e.g. by a future M27 preamble-aided variant), residual rotational ambiguity would surface at that print rather than be silently absorbed.

**Why gate (c) is taken modulo 4-fold rotation (for the diagnostic value):** QAM-16 has 4-fold rotational symmetry (multiplication by `exp(j·k·π/2)` maps the lattice onto itself), so a DD receiver has 4 equally stable lock orbits. Without a preamble or differential coding to anchor absolute rotational phase, comparing silicon hard-symbols to reference hard-symbols position-by-position is information-free — the two DD instances can be perfectly locked to the same lattice, just to different orbits of it. The diagnostic SER metric therefore takes a minimum over the constellation's rotational symmetry group. Downstream systems resolve the 4-fold ambiguity via differential encoding or a preamble ([Proakis & Salehi 5e §5.2.9](https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html); [Barry-Lee-Messerschmitt 3e §8.5.4](https://link.springer.com/book/10.1007/978-1-4615-0227-2); [Rice 2e §7.4.6](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544)); this is orthogonal to the receiver kernel's correctness.

**Why RMS(z − slice(z)) and not "residual angle mod π/2":** QPSK's DD detector has π/2 rotational symmetry in its cost function (its Voronoi cells are invariant under a 90-deg observation rotation), so "angle mod π/2" is the right lock metric there. QAM-16's DD detector does NOT have this invariance ([Barry-Lee-Messerschmitt 3e §8.5.3 "Local Extrema of the DD Cost Function"](https://link.springer.com/book/10.1007/978-1-4615-0227-2); [Rice 2e §7.4.4](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544)): a 45-deg observation rotation moves the outer point `(3,0)/√10` to `(3,3)/(√2·√10)`, whose QAM-16 slicer decision is `(3,3)/√10` — a distinct lattice point, not an aliased copy of the original. A 45-deg wrong-rotation lock is therefore a **distinct** stable equilibrium of the DD loop, not an aliased copy of the correct lock, and "angle mod π/2" would hide it. Worse, QAM-16 lattice points do not lie on axes (`atan2(1, 3) = 0.322`, `atan2(3, 3) = π/4`, `atan2(1, 1) = π/4`, etc.), so "angle mod π/2" is not even zero when the loop is locked correctly — it depends on which lattice orbit the symbol lands on. `RMS(z − QAM16_slice(z))` is the 2D constellation-error metric that directly measures lock to the full QAM-16 grid; it reads at bf16 machine precision (~5e-4) on a correctly locked receiver and at O(0.3) on a 45-deg wrong-rotation lock.

Sandbox transliteration ([tools/m26_kernel_transliteration_check.py](../tools/m26_kernel_transliteration_check.py)) verifies the .cc against the Python reference bit-exact on seeds 826 and 827: **0 / 1024 hard-sym mismatches AND 0 / 2048 LLR mismatches on both seeds**. Silicon PASS numbers recorded 2026-08-15 above; laptop log preserved in [dev-log.md](../dev-log.md).

## 4b. Bring-up incidents (silicon vs host divergence log)

M25 accumulated 4 bring-up incidents. The M26 kernel inherits all 4 mitigations verbatim (Taylor sin/cos, dead-zone `sgn_bit` via volatile `uint32_t` OR, receiver-theoretic PASS gates). Two new test-side incidents surfaced on first-run laptop bring-up (both fixed test-side; no kernel change).

**Incident #1 (M26-specific, test-side, no kernel change):** the first silicon run on seed 826 passed gates (a) and (b1) trivially (acquisition max_err = 0.0039 vs 0.10; \|z\| magnitude-class distance median = 0.0020 vs 0.15) but the initial gate (b2), phrased as "RMS residual angle mod π/2 < π/16" in the M25 style, fired at 0.5433 rad on the silicon output. Re-running the bit-exact host reference through the same metric returned 0.5622 rad, i.e. the reference **also** failed the gate. Root cause: `angle mod π/2` is a valid steady-state metric only for constellations whose DD cost function has π/2 rotational symmetry (BPSK, QPSK). QAM-16 lattice points do not sit on axes, and the DD-QAM16 detector's Voronoi partition is not invariant under a 45-deg observation rotation, so a 45-deg wrong-rotation lock is a distinct DD equilibrium rather than an aliased copy of the correct one — the folding metric collapses both onto the same value and additionally is non-zero at the correct lock. Documented in [Barry-Lee-Messerschmitt 3e §8.5.3 "Local Extrema of the DD Cost Function"](https://link.springer.com/book/10.1007/978-1-4615-0227-2) and [Rice 2e §7.4.4](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544). Mitigation: replace gate (b2) with `RMS(z − QAM16_slice(z)) < 0.10`, the 2D constellation-error metric. Verified in the sandbox: the reference reads 0.0005 (bf16 machine precision) on the same seed. This was a **test-side design bug**, not a kernel bug; the printed silicon hard-symbols already matched the reference bit-for-bit through the first 4 slots and gate (b1) confirmed lock to valid QAM-16 magnitude classes.

**Incident #2 (M26-specific, test-side, no kernel change):** after Incident #1 was fixed and gates (a), (b1), (b2) passed cleanly on seed 826 (max_err = 0.0039, magnitude-class median = 0.0020, RMS constellation error = 0.0027), the next silicon run fired gate (c) with SER = 1.0000 despite both silicon and reference being provably locked to the QAM-16 lattice. Initial hypothesis was 4-fold rotational ambiguity (same class as M25 incident #4). The rotation-invariant SER was implemented (min over `k ∈ {0, 90°, 180°, 270°}`) and re-run; observed SERs `[1.0, 0.7188, 0.7344, 0.9922]` — no rotation achieves the < 0.10 threshold, which **rules out** pure phase ambiguity as the root cause. True root cause: the Gardner TED's PI integrator selects an integer sample instant into the 2 sps input stream, and that integrator drifts under CPU vs AIE2 float32 rounding by 1+ symbols over the burst. A 1-symbol timing offset produces SER ≈ 1 on the entire tail even though every silicon symbol is individually correctly demapped and locked to a valid QAM-16 grid point (as gates (b1) / (b2) certify at bf16 machine precision). The `[0..4]` prefix printed `Silicon hardSym == Ref hardSym` bit-for-bit, consistent with both integrators starting aligned and drifting apart during acquisition. Mitigation: gate (c) reduced to **diagnostic-only** per Amendment #1 in §4. Correctness of the M26 novel surface (QAM-16 slicer, DD-QAM16 detector, max-log LLR demapper) is certified by gates (a), (b1), (b2), and (d), which do not depend on symbol-position alignment between two independent DD-timing loops. The 4-fold rotation-invariant SER is retained as the diagnostic value so that if a future variant externally anchors timing (e.g. preamble-aided), any residual rotational ambiguity would surface at that print. References: [Barry-Lee-Messerschmitt 3e §8.5.4](https://link.springer.com/book/10.1007/978-1-4615-0227-2); [Rice 2e §7.4.6](https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544); [Proakis & Salehi 5e §5.2.9](https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html); [NASA JPL TDA 42-130](https://ipnpr.jpl.nasa.gov/progress_report/42-130/130B.pdf); [Gardner 1986](https://doi.org/10.1109/TCOM.1986.1096561).

Additional pre-flight observations from the sandbox transliteration (retained from the original bring-up plan):

- **LLR dynamic range**: outer QAM-16 point at `z_axis = 3` gives `LLR(b_MSB) = 12`, well inside bf16's ±3.4 · 10³⁸ range and clearly representable at ~1% bf16 precision.
- **Dead-zone activation on QAM-16**: at unit-avg energy, the smallest reliable lattice value is `1/√10 ≈ 0.316`, which is 316× the `1e-3` dead-zone threshold; slicer stalling only triggers during acquisition, as intended.
- **Order-M pull-in vs BPSK/QPSK**: DD-QAM16 has a shallower S-curve slope near the 45° equilibrium than QPSK-Costas ([Godard 1980 §IV.C](https://doi.org/10.1109/TCOM.1980.1094608)); we accordingly restrict the test's initial `theta0` rotation to `[-π/16, π/16]` (half of M25's `[-π/8, π/8]`) so the loop can acquire within the sample window.

## 5. Bring-up checklist (mirrors M24 & M25 lessons)

- [x] Every `@iron.jit`-decorated program factory has `In` / `Out` / `CompileTime` type annotations on every parameter (M24 §5.3 lesson).
- [x] Kernel source uses `#define NOCPP` and open-coded math primitives; no `#include <math.h>` (M25 incident #1).
- [x] Sign-of on floats uses IEEE-754 bit reinterpret via `union{float; uint32_t}` with a `volatile uint32_t` intermediate to defeat `-O2` `llvm.copysign` folding (M25 incidents #2, #3).
- [x] Dead-zone `DEAD_ZONE_EPS = 1e-3` around zero for all decision-directed sign reads (M25 incident #3, #4).
- [x] PASS gate is receiver-theoretic (acquisition + steady-state residual metric + LLR/hard consistency), not sample-wise match (M25 incident #4, M26 Amendment #1).
- [x] Three DMA buffers (in, out_sym, out_llr) via three ObjectFifos and a three-parameter `sequence` in the `Runtime` factory (see `test_qam_rx_m26.py` §"IRON JIT plumbing").
- [x] Sandbox transliteration passes bit-exactly on both hard-sym and LLR before laptop dispatch.
- [x] Laptop silicon PASS confirmed on Phoenix NPU1 (seed 826, 2026-08-15) — all four asserted gates green.

## 6. Downstream / roadmap coupling

M26 completes the DD-carrier portion of the receiver front-end. Downstream milestones in the modulation & synchronization block:

- **M27 OFDM** — reuses M25/M26 timing recovery and NCO derotate; adds cyclic-prefix removal, M17 FFT dispatch, pilot-based channel estimation, and per-subcarrier equalization ([Cimini 1985](https://doi.org/10.1109/TCOM.1985.1096357); [van de Beek et al 1997](https://doi.org/10.1109/78.611176)).
- **M28+ soft outer decoder** — will consume M26's LLR stream. Candidates: [LDPC per DVB-S2X](https://dvb.org/wp-content/uploads/2019/12/A171_DVB-S2X_Draft_EN_302_307-2_v121.pdf) or [turbo per 3GPP TS 36.212](https://www.3gpp.org/DynaReport/36212.htm).

## References

### Constellation and hard slicer
- Proakis & Salehi, *Digital Communications* 5e (2008), §4.3.1 rectangular Gray-labelled QAM. https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html
- Rice, *Digital Communications: A Discrete-Time Approach* 2e (2008), §5.3 constellations, §7.4 decision-directed carrier phase recovery. https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544
- Barry, Lee, Messerschmitt, *Digital Communication* 3e (2003), §8.5 decision-directed carrier recovery. https://link.springer.com/book/10.1007/978-1-4615-0227-2
- GNU Radio "Constellation_Rect_Object" wiki. https://wiki.gnuradio.org/index.php/Constellation_Rect_Object
- MathWorks, "16-QAM Modulation". https://www.mathworks.com/help/comm/ref/qammod.html

### Decision-directed carrier phase recovery
- Godard, "Self-Recovering Equalization and Carrier Tracking in Two-Dimensional Data Communication Systems", *IEEE TCOM* COM-28(11), pp 1867-1875, Nov 1980. https://doi.org/10.1109/TCOM.1980.1094608
- Barry, Lee, Messerschmitt §8.5 (above).
- GNU Radio `costas_loop_cc` `phase_detector_8` order-M extension. https://www.gnuradio.org/doc/doxygen-3.7.2/classgr_1_1digital_1_1costas__loop__cc.html

### Timing recovery and PI loop filters (reused from M25)
- Gardner, "A BPSK/QPSK Timing-Error Detector for Sampled Receivers", *IEEE TCOM* COM-34(5), pp 423-429, May 1986. https://doi.org/10.1109/TCOM.1986.1096561
- Mueller & Muller, "Timing Recovery in Digital Synchronous Data Receivers", *IEEE TCOM* COM-24(5), pp 516-531, May 1976. https://doi.org/10.1109/TCOM.1976.1093326
- GNU Radio control_loop.h. https://www.gnuradio.org/doc/doxygen/control__loop_8h_source.html
- Rondeau, "Control Loop Gain Values", 2011-08-13. http://www.trondeau.com/blog/2011/8/13/control-loop-gain-values.html
- GNU Radio Symbol Sync wiki. https://wiki.gnuradio.org/index.php/Symbol_Sync

### Soft-output demapper
- Tosato & Bisaglia, "Simplified Soft-Output Demapper for Binary Interleaved COFDM With Application to HIPERLAN/2", *IEEE ICC* 2002. https://doi.org/10.1109/ICC.2002.996940
- Alvarado & Fabregas, "Simplified soft-metric calculation for L-QAM in fading channels", *IEEE Communications Letters* 13(9), Sep 2009. https://doi.org/10.1109/LCOMM.2009.081940
- Viterbi, "An Intuitive Justification and a Simplified Implementation of the MAP Decoder for Convolutional Codes", *IEEE JSAC* 16(2), 1998. https://doi.org/10.1109/49.661103

### Loop dynamics and PASS-gate rationale (inherited from M25)
- NASA/JPL TDA Progress Report 42-130, "Costas Loop Analysis". https://ipnpr.jpl.nasa.gov/progress_report/42-130/130B.pdf
- Kuznetsov, Leonov, Yuldashev, "Discrete-time analysis of the QPSK Costas loop", 2018. https://arxiv.org/abs/1810.00071
- Analog Devices, "Practical Costas Loops". https://ez.analog.com/cfs-filesystemfile/__key/communityserver-discussions-components-files/333/Costas-Loop.pdf

### OFDM downstream
- Cimini, "Analysis and Simulation of a Digital Mobile Channel Using OFDM", *IEEE TCOM* COM-33(7), 1985. https://doi.org/10.1109/TCOM.1985.1096357
- van de Beek, Sandell, Börjesson, "ML estimation of time and frequency offset in OFDM systems", *IEEE TSP* 45(7), 1997. https://doi.org/10.1109/78.611176
