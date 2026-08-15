# Phoenix SDR-DSP Roadmap

This roadmap follows the canonical 31-milestone plan defined in Section 16 of the [Phoenix SDR-DSP Master Prompt](../Phoenix-SDR-DSP-Master-Prompt.md). Every technical claim in this document is intended to be citable to a primary source; the References section at the bottom collects all sources with canonical URLs.

## Project positioning

`phoenix-sdr-dsp` is a **bit-accurate, silicon-validated NPU DSP kernel library** for the first-generation AMD XDNA1 architecture as implemented in the Ryzen 7040-series "Phoenix" APUs. The XDNA1 NPU is a spatial dataflow array of AI Engine (AIE2) tiles, organized as a 4×5 grid of compute tiles plus memory tiles and shim DMAs, per AMD's [official architecture description](https://www.amd.com/en/technologies/xdna.html) and the upstream [Linux `amdxdna` kernel driver documentation](https://docs.kernel.org/accel/amdxdna/amdnpu.html). Each AIE2 tile is a VLIW SIMD vector processor with 512-bit vector datapath and local L1 program/data memory ([AMD XDNA overview](https://www.amd.com/en/technologies/xdna.html); [IEEE Micro 2024 "AMD XDNA NPU in Ryzen AI Processors"](https://www.computer.org/csdl/magazine/mi/2024/06/10592049/1YtaXNWFBqE)).

The software toolchain used across all shipped milestones is the open-source MLIR-AIE / IRON stack ([Xilinx/mlir-aie GitHub](https://github.com/Xilinx/mlir-aie); [IRON documentation v1.4.1](https://xilinx.github.io/mlir-aie/1.4.1/)), which provides close-to-metal Python bindings that compile to MLIR and then to AI Engine core binaries via the Peano LLVM backend ([Peano/llvm-aie GitHub](https://github.com/Xilinx/llvm-aie); [Peano announcement on LLVM Discourse, 2024](https://discourse.llvm.org/t/peano-llvm-support-for-amd-xilinx-ai-engine-processors/79458); [AMD IRON tutorial PDF, MICRO 2024](https://www.amd.com/content/dam/amd/en/documents/products/processors/ryzen/ai/iron-for-ryzen-ai-tutorial-micro-2024.pdf)). Device dispatch uses the Xilinx Runtime (XRT) with the XDNA shim.

The SDR-integration track (LimeSDR, ring buffers, real-time streaming) is deferred until suitable SDR hardware is available for validation. The pure-DSP track (transforms, filters, modular arithmetic, NTT/FFT) continues without RF-hardware dependency.

## Status legend

- ✅ **Shipped** — silicon-validated on physical NPU, bit-accurate against CPU reference where applicable, present in `run_all_silicon_tests.py`.
- 🧪 **Shipped, unintegrated** — silicon-validated but not part of the regression runner; scheduled for renumbering and integration.
- 🚧 **Next up** — no hardware dependency, actively planned.
- 🔒 **Deferred — SDR hardware** — blocked pending acquisition of a supported SDR device.
- ⏸️ **Deferred — depends on prior deferred milestone** — blocked transitively.
- 💡 **Optional / research** — post-v1.0.

## Foundational milestones (M0–M2)

| M# | Focus | Status | Artifact |
|---|---|---|---|
| M0 | Windows environment audit | ✅ | `scripts/windows/windows_audit.ps1`, `audit/` |
| M1 | Native Windows architecture decision | ✅ | `docs/M1_ARCHITECTURE_DECISION.md` |
| M2 | Pinned Windows toolchain | ✅ | `docs/M2_TOOLCHAIN_PIN.md`, `toolchain.yaml` |

The native-Windows execution path is used because MLIR-AIE and Peano ship first-class native-Windows wheels ([MLIR-AIE 1.2 release notes, Phoronix](https://www.phoronix.com/news/AMD-MLIR-AIE-1.2)) and because the `amdxdna` NPU driver binds to the Windows host — WSL2 cannot directly access the NPU device ([Linux amdxdna documentation](https://docs.kernel.org/accel/amdxdna/amdnpu.html)). See [`docs/M1_ARCHITECTURE_DECISION.md`](M1_ARCHITECTURE_DECISION.md) for the full rejection rationale.

## Track 1 — NPU DSP kernels (shipped 16/16)

### Vector & scalar primitives (canonical §16 M3–M6)

| M# | Focus | Status | Notes |
|---|---|---|---|
| M3 | Native Windows MLIR-AIE pass-through example | ✅ | Shipped as SAXPY (`tests/m3_saxpy/`). SAXPY (`y = a·x + y`) is a strict superset of the pass-through demo the master prompt calls for; SAXPY exercises vector multiply-add and validates the compile → device-load → buffer → kernel → verify path in one step. |
| M5 | Native Windows NPU vector-copy kernel | ✅ | Shipped as 8-tap FIR (`tests/m5_fir/`) — vector-copy is a degenerate FIR (tap = identity). Divergence documented; no separate vector-copy milestone. |
| M6 | Vector arithmetic + complex I/Q primitives | ✅ | Shipped as complex mixer/NCO (`tests/m6_mixer/`). Covers complex multiply-add, the core primitive for downstream mixers, correlators, and phase rotators. |

### DSP kernels (extensions beyond §16 numbering)

| M# | Focus | Status | Notes |
|---|---|---|---|
| M7-ext | Power / RSSI energy detector | ✅ | `tests/m7_power/`. Not in §16 sequence; useful for spectrum monitoring, squelch, and correlation-based preamble detection. |
| M8-ext | Fused DSP pipeline (mixer + FIR + power) | ✅ | `tests/m8_pipeline/`. Multi-stage kernel fusion pattern, no SDR yet. |
| M9-ext | 4-column parallel FIR | ✅ | `tests/m9_parallel/`. Multi-column parallelization exercises the XDNA1 4×5 tile grid geometry ([Linux amdxdna docs](https://docs.kernel.org/accel/amdxdna/amdnpu.html)); pattern reusable for future kernels. |
| M10-ext | 4-column parallel multi-stage demodulator pipeline | ✅ | `tests/m9b_parallel_pipeline/`. In `run_all_silicon_tests.py` as Milestone 9b. |
| demo-iq | 4-column streamed I/Q throughput | 🧪 | `tests/npu_visible/`. Host-visible IRON+DMA mixer measured 2026-08-15 on Ryzen 9 7940HS: **7.459 Msps**, 29.84 MB/s I/Q in, ~92% Task Manager NPU, first-buffer $L_\infty = 0.007812$. Phoenix NPU is [10 TOPS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) ([INT8](https://www.tomshardware.com/pc-components/cpus/the-refresh-that-wasnt-amd-announces-hawk-point-ryzen-8040-series-with-zen-4-rdna3-and-xdna-teases-strix-point)). Not in `run_all_silicon_tests.py`. Kernel vectorization deferred. |

### Modular arithmetic & NTT track (canonical §16 M10–M15)

The NTT track implements the Number-Theoretic Transform, a finite-field analogue of the Discrete Fourier Transform that runs bit-exactly over integers modulo a prime ([Emergent Mind NTT survey](https://www.emergentmind.com/topics/number-theoretic-transform-ntt); [Ingonyama ICICLE NTT documentation](https://dev.ingonyama.com/2.8.0/icicle/primitives/ntt)). The prime modulus `q = 3329` and polynomial degree `N = 256` are the CRYSTALS-Kyber / ML-KEM parameters used by NIST's post-quantum key-encapsulation standard ([arXiv 2601.17806, Algorithm-Targeted NTT Hardware Acceleration, 2026](https://arxiv.org/html/2601.17806v1); [PLOS ONE, Area-time efficient pipelined NTT for CRYSTALS-Kyber](https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0323224&type=printable)).

| M# | Focus | Status | Artifact |
|---|---|---|---|
| M10 | Modular arithmetic (Barrett reduction, `q = 3329`) | ✅ | `tests/m10_modular/`. Uses the Barrett-reduction algorithm from [PLOS ONE 2025](https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0323224&type=printable). |
| M11 | Radix-2 NTT butterfly | ✅ | `tests/m11_butterfly/`. Cooley-Tukey butterfly generalized to finite field, form `X = U + T`, `Y = U − T` where `T = V · ω mod q` ([Emergent Mind NTT topic](https://www.emergentmind.com/topics/number-theoretic-transform-ntt-eda2bb95-c9d4-44b6-938d-c0b0dd00bafe)). |
| M12 | CPU NTT/INTT reference | ✅ | `tests/m12_ntt_ref/`. Bit-exact software reference the NPU implementation is verified against. |
| M13 | 16-point NPU NTT | ✅ | `tests/m13_ntt16/` |
| M14 | 256-point vectorized NPU NTT | ✅ | `tests/m14_ntt256/`. Matches Kyber `N = 256`. |
| M15 | NPU INTT + cyclic polynomial multiplication | ✅ | `tests/m15_polymul/` |
| M15+ | Negacyclic polynomial multiplication (`Z_q[x]/(x^N + 1)`) | ✅ | `tests/m15b_negacyclic/test_negacyclic_m16.py`. Kyber / [ML-KEM](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ring per [Isabelle/AFP](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf). Ported 2026-08-15 to the same `iron.Runtime` sequence-function API as M15. Schoolbook O(N²) kernel, bit-exact on Phoenix NPU1. Filename still says `m16`; keep until a dedicated renumber. The FIPS 203 KEM itself is **M32**, not this row. |

### FFT track (canonical §16 M16–M18)

The Fast Fourier Transform in radix-2 form is the [Cooley–Tukey algorithm (1965)](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf), which reduces the DFT operation count from O(N²) to O(N log N) by recursive decomposition into even/odd subsequences ([Rice University FFT tutorial](https://repository.rice.edu/server/api/core/bitstreams/01e9e0a5-fa6f-453d-a1b5-8209fa0a565c/content); [Brian McFee, Digital Signals Theory §8.2](https://brianmcfee.net/dstbook-site/content/ch08-fft/FFT.html)).

| M# | Focus | Status | Notes |
|---|---|---|---|
| M16 | CPU DFT/FFT reference | ✅ | `tests/m16_fft_ref/test_fft_reference_m16.py`. Three independent implementations cross-validated: direct O(N²) DFT via twiddle matrix, recursive radix-2 [Cooley-Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf) FFT, iterative in-place radix-2 FFT with bit-reversed permutation (dataflow proxy for the M17 NPU kernel). All match NumPy [`fft.fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html) to double-precision round-off (~1e-13 relative). Tests: impulse, DC constant, pure tone, random complex, x = IFFT(FFT(x)) round-trip, Parseval energy conservation. Sizes N ∈ {8, 16, 32, 64, 128, 256, 512, 1024}. Runs on Ubuntu in CI in ~0.3 s. |
| M17 | NPU FFT/IFFT | ✅ | Shipped as 64-point **radix-4 Stockham FFT** (`tests/m17_radix2_fft/test_fft_m17_v3.py`) delivering O(N log N) complexity per [Cooley-Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf) and the Stockham auto-sort variant that avoids bit-reversed permutation. Forward FFT SNR **138.79 dB** vs `numpy.fft.fft`. Round-trip IFFT via `conj(FFT(conj(Y)))/N` reuses the forward kernel with no separate IFFT device code, RMS SNR **135.11 dB**. Supersedes the earlier direct-DFT prototype in `tests/m17_fft_dft/` (retained pending removal). Wired into `run_all_silicon_tests.py`. |
| M17-parallel | 4-column parallel NPU FFT | ✅ | `tests/m17p_fft_parallel/`. Parallel channelizer running the M17 radix-4 Stockham kernel across all four AIE2 tile columns of the Phoenix NPU1 grid ([Linux amdxdna docs](https://docs.kernel.org/accel/amdxdna/amdnpu.html)). Batch throughput 1,993 FFTs/sec on 64 parallel 64-point frames. Wired into `run_all_silicon_tests.py`. |
| M17-butterfly | NPU FFT via radix-2/radix-4 Cooley-Tukey butterflies | ✅ | Delivered by the M17 radix-4 Stockham kernel above. Row retained for §16 traceability. |
| M18 | Streaming FFT spectrum analyzer connected to SDR | 🔒 | Requires SDR hardware. |

### Filtering & resampling (canonical §16 M19–M23)

| M# | Focus | Status | Notes |
|---|---|---|---|
| M19 | Complex FIR filter | ✅ | Real-valued 8-tap FIR shipped as `tests/m5_fir/`. Complex-valued (complex taps × complex I/Q input) 8-tap variant shipped as `tests/m19_complex_fir/` and wired as the 17th silicon regression entry. Design: [docs/M19_DESIGN.md](M19_DESIGN.md). |
| M20 | Polyphase decimation & interpolation | ✅ | Fused decim-M=4 + interp-L=4 kernel on one AIE2 core shipped as `tests/m20_polyphase/`, 16-tap Kaiser-window prototype LPF ([Kaiser 1974](https://ieeexplore.ieee.org/document/1451724)) with `taps *= L` interpolator scaling matching [`scipy.signal.resample_poly`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html) and [GNU Radio pfb](https://www.gnuradio.org/doc/doxygen-3.7/page_pfb.html). Polyphase decomposition per [Vaidyanathan 1993 ch. 4](https://www.pearson.com/en-us/subject-catalog/p/multirate-systems-and-filter-banks/P200000003431/9780130349507) and [Harris 2004 ch. 6](https://ieeexplore.ieee.org/book/9448967). Silicon PASS at atol=0.01 on random I/Q. Wired as the 18th silicon regression entry. Design: [docs/M20_DESIGN.md](M20_DESIGN.md). |
| M21 | Digital downconverter (DDC) | ✅ | Fused DDC (complex NCO at `f_c = -f_s/8` + 16-tap Kaiser LPF + decim-by-M=4) on one AIE2 core, shipped as [`tests/m21_ddc/`](../tests/m21_ddc/). 8-sample cordic-free LO LUT per [Analog Devices MT-085 "Fundamentals of DDS"](https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf). Signal chain follows [Harris 2004 ch. 8 "The Digital Down-Converter"](https://ieeexplore.ieee.org/book/9448967); block topology matches the [GNU Radio Frequency Xlating FIR Filter](https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter) reference. LPF reuses the M20 16-tap Kaiser prototype ([Kaiser 1974](https://ieeexplore.ieee.org/document/1451724)). Silicon PASS at max err 0.003906 (atol=0.01) on random I/Q (seed 789); on-carrier tone at `+f_s/8` decodes to mag=1.0000/phase=0.0000, image rejection 55.8 dB at `-f_s/8`. Wired as the 19th silicon regression entry. Design: [docs/M21_DESIGN.md](M21_DESIGN.md). |
| M22 | Digital upconverter (DUC) | ✅ | Fused DUC (zero-stuff interp by L=4 + 16-tap Kaiser×L LPF + complex NCO at `f_c = +f_s/8`) on one AIE2 core, shipped as [`tests/m22_duc/`](../tests/m22_duc/). Zero-stuff-and-filter interpolation follows the polyphase commutator identity [Vaidyanathan 1993 Eq. 4.3.13](https://dl.acm.org/doi/10.5555/151045) and [Harris 2004 ch. 7](https://ieeexplore.ieee.org/book/9448967); DUC signal chain per [Harris 2004 §8.4 "The Digital Up-Converter"](https://ieeexplore.ieee.org/book/9448967); block topology matches the [GNU Radio Frequency Xlating FIR Filter](https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter) run with negative decimation. Interpolator tap scaling `taps *= L` follows the [`scipy.signal.resample_poly`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html) convention. 8-sample cordic-free LO LUT (sign-flipped from M21) per [Analog Devices MT-085](https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf). LPF prototype reuses the M20 16-tap Kaiser design ([Kaiser 1974](https://ieeexplore.ieee.org/document/1451724)). Silicon PASS at max err 0.007812 (atol=0.01) on random I/Q (seed 792); DC baseband upconverts to `+f_s/8` at mag 0.9976 (FFT peak at bin 192), baseband tone at `-f_bb/8` lands at `+3f_s/32` (FFT peak at bin 144). Wired as the 20th silicon regression entry. Design: [docs/M22_DESIGN.md](M22_DESIGN.md). |
| M23 | Channelizer & filter bank | ✅ | Fused polyphase channelizer (input commutator + M=8-path 8-tap Kaiser FIR + 8-point matmul-DFT) on one AIE2 core, shipped as [`tests/m23_channelizer/`](../tests/m23_channelizer/). M-path analysis-bank topology per [Harris 2004 ch. 6 §6.3 Fig. 6.8](https://ieeexplore.ieee.org/book/9448967); polyphase commutator identity per [Vaidyanathan 1993 §4.3, Eq. 4.3.13](https://dl.acm.org/doi/10.5555/151045). Natural sample-to-branch order (`p = q`) matches the [GNU Radio pfb_channelizer_ccf](https://wiki.gnuradio.org/index.php/Polyphase_Channelizer) and [NVIDIA MatX channelize_poly](https://nvidia.github.io/MatX/api/signalimage/filtering/channelize_poly.html) conventions. 64-tap Kaiser prototype (β ≈ 5.653, cutoff π/M, 60 dB stop-band) per [Kaiser 1974](https://ieeexplore.ieee.org/document/1451724) via [`scipy.signal.firwin`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.firwin.html) with `scale=True` — `sum(h) = 0.99977`, exact even symmetry. 8-point DFT uses fully-embedded twiddles (matmul-style, same pattern as M17p `parallel_fft64_kernel.cc`). Silicon PASS at max err 0.003906 (atol=0.02) on random I/Q (seed 793); DC→ch0 iso 66.2 dB, tone→ch3 iso 66.2 dB, two-tone→ch1+ch5 iso 64.5 dB. Sandbox transliteration is bit-exact to host reference (0/4096 slots differ). Wired as the 21st silicon regression entry. Design: [docs/M23_DESIGN.md](M23_DESIGN.md). |

### Modulation & synchronization (canonical §16 M24–M27, partially SDR-blocked)

| M# | Focus | Status | Notes |
|---|---|---|---|
| M24 | Correlation, preamble detection, packet sync | ✅ | Fused Barker-13 matched-filter correlator on one AIE2 core, shipped as [`tests/m24_correlator/`](../tests/m24_correlator/). Matched-filter theory follows [Proakis & Salehi 5e §5.1.5](https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html) and [Massey 1972](https://ieeexplore.ieee.org/document/1091459); correlation-as-reversed-FIR identity per [Oppenheim & Schafer 3e §2.6.2](https://www.pearson.com/en-us/subject-catalog/p/discrete-time-signal-processing/P200000003543); block topology matches the [GNU Radio Correlation Estimator](https://wiki.gnuradio.org/index.php/Correlation_Estimator) and [liquid-dsp `detector_cccf`](https://liquidsdr.org/doc/detector/). Barker-13 preamble `(+1,+1,+1,+1,+1,-1,-1,+1,+1,-1,+1,-1,+1)` per [Barker 1953](https://ieeexplore.ieee.org/document/6773685) and [Wikipedia "Barker code"](https://en.wikipedia.org/wiki/Barker_code); PSL = 1 (|c_v| ≤ 1 for all nonzero shifts). Kernel is a hand-unrolled 13-term real FIR pair on I and Q with reversed Barker taps (M22 literal-index MAC discipline). Silicon PASS at max err 0.03125 (atol = 0.05) on random I/Q (seed 794); host gates: peak = 13.0 at sample 112 (aligned preamble), Iy steady = 5.0 on DC input, +45° rotated preamble preserves phase at |y| = 12.99, negated preamble peaks at -13.0. Sandbox transliteration bit-exact to host reference (0/4096 slots differ). Bring-up incident: three consecutive silicon runs produced all-zero output because the driver's `correlator_program` was missing the `@iron.jit` decorator (root cause documented in [docs/M24_DESIGN.md §5.3](M24_DESIGN.md)). Wired as the 22nd silicon regression entry. Design: [docs/M24_DESIGN.md](M24_DESIGN.md). |
| M25 | BPSK / QPSK receiver pipeline | ⏸️ | Needs M24 + Costas loop + Gardner/M&M timing recovery. |
| M26 | QAM receiver pipeline | ⏸️ | Extends M25 with soft-decision demapping. |
| M27 | OFDM: FFT + CP + pilots + channel estimation + equalization | ⏸️ | Uses M17 FFT. |

## Track 2 — SDR integration (🔒 blocked on hardware)

All milestones below require a working SDR device. Deferred until hardware is available.

| M# | Focus | Master prompt intent |
|---|---|---|
| M4 | SDR enumeration + Windows streaming test (no NPU) | §16: LimeSDR specifically; generalized here to any SDR via the `ISdrDevice` abstraction (§7 of the master prompt). |
| M7-canonical | Continuous SDR → host ring buffer | §9 real-time streaming architecture (double/triple buffering). |
| M8-canonical | Host buffer → NPU → host streaming bridge | §9 pipelined architecture. |
| M9-canonical | Real-time pass-through of SDR I/Q through NPU | §16 integration checkpoint. |
| M18 | Streaming FFT spectrum analyzer (uses M17 + SDR) | §16 M18. |
| M28 | Beamforming & multi-channel processing | Requires multi-channel SDR. |
| M31 | Unified native Windows SDR-DSP API | Final integration. |

**Hardware plan when unblocked:** Master prompt §7 specifies LimeSDR as the primary reference device. `ISdrDevice` abstraction is designed to accept additional backends. Realistic candidate devices when hardware is acquired: LimeSDR (primary, per master prompt), RTL-SDR (cheap RX validation), HackRF, PlutoSDR, USRP B-series, BladeRF. API choice (native LimeSuite / UHD / hackrf / rtlsdr vs SoapySDR) is deferred to the point of hardware acquisition, following the master prompt's §7 constraint ("do not choose between Lime Suite and SoapySDR without testing").

## Track 3 — Advanced / research (💡 optional)

| M# | Focus | Notes |
|---|---|---|
| M29 | Adaptive filtering & interference suppression | Can be prototyped on synthetic data; real validation needs SDR. |
| M30 | Optional learned AI blocks for SDR | Master prompt marks explicitly optional. Depends on Track 1 primitives + SDR integration. |

## Track 4 — FIPS 203 ML-KEM (🚧 next NTT item)

Extra milestone after the shipped M10–M15b stack. Numbered **M32** so it does not collide with master-prompt §16 (M0–M31 are SDR/DSP). Design: [`docs/M32_FIPS203_MLKEM.md`](M32_FIPS203_MLKEM.md). Stub: `tests/m32_mlkem/`.

[FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) (13 August 2024, [DOI 10.6028/NIST.FIPS.203](https://doi.org/10.6028/NIST.FIPS.203)) specifies ML-KEM, derived from round-3 [CRYSTALS-Kyber](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf) (§1.1). Ring `R_q = Z_3329[X]/(X^{256}+1)` is already the M15b ring. The KEM product is Algorithms 9–12 (NTT), not M15b schoolbook.

| M# | Focus | Status | Notes |
|---|---|---|---|
| M32 | FIPS 203 ML-KEM | 🚧 | Approved KEM: Algorithms 19–21. First set ML-KEM-512 (`k=2`); NIST default later is ML-KEM-768 ([Table 2](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)). Hashes from [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf). |
| M32a | CPU ML-KEM-512 reference | 🚧 | Host-only, bit-exact vs NIST [example values](https://csrc.nist.gov/projects/cryptographic-standards-and-guidelines/example-values) and CAVP internals ([§6](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)). |
| M32b | NPU NTT-domain negacyclic product | 🚧 | Algorithms 9–12 on Phoenix NPU1. Replaces schoolbook for the KEM path only. |
| M32c | SampleNTT + SamplePolyCBD + SHA3/SHAKE | 🚧 | Algorithms 7–8; PRF/H/G/J from FIPS 203 §4.1. |
| M32d | K-PKE component | 🚧 | Algorithms 13–15. **Not** approved standalone ([§3.3](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)). |
| M32e | ML-KEM.KeyGen / Encaps / Decaps | 🚧 | Algorithms 19–21. Then 768, then 1024. Do not add to the 16-suite until a gate is bit-exact on silicon. |

## Completed — v0.4.0 silicon + new-user install (2026-08-15)

The DSP / NTT / FFT kernel library is closed at **16/16 PASS**. A wipe-and-clone of [`main`](https://github.com/midhatn/phoenix-sdr-dsp) ran [`install.py`](../install.py) then `run_all_silicon_tests.py` and passed in **95.91 s** (cold xclbin). Cached re-run on the development tree is **17.46 s**. Stack: [Xilinx XRT](https://github.com/Xilinx/XRT) 2.21.75, [Xilinx MLIR-AIE](https://github.com/Xilinx/mlir-aie) / [IRON](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/) v1.4.1, [LLVM Peano](https://github.com/Xilinx/llvm-aie) `21.0.0.2026080301+c9c5ecb7`. New-user path is documented on the landing page [Installation](../README.md#installation) section.

Items 1–5 below are historical. The live next NTT item is M32a.

1. **v0.2.1 polish** — *completed*. Dependabot, CI badge, v0.4.0 tag.
2. **Directory renumbering pass** — *completed in v0.2.1*. Scheme B directories renamed to §16 canonical names. Blob SHAs preserved so `git log --follow` still tracks each file.
3. **M16 CPU FFT reference** — *completed*. `tests/m16_fft_ref/test_fft_reference_m16.py`; CI `cpu-reference-tests` on Ubuntu.
4. **M17-butterfly** — *completed*. Radix-4 Stockham FFT at 138.79 dB forward / 135.11 dB round-trip SNR.
5. **M15b negacyclic port to iron.Runtime** — *completed 2026-08-15*. Schoolbook kernel, bit-exact. Closes the 16-suite.
6. **M32 FIPS 203 ML-KEM** — *next NTT item*. Start at M32a (CPU ML-KEM-512 reference). Design: [`docs/M32_FIPS203_MLKEM.md`](M32_FIPS203_MLKEM.md). M15b proved the ring; M32 implements the approved KEM ([Algorithms 19–21](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)).
7. **M19 complex FIR** — DSP-track alternative: extend the shipped real-valued FIR to complex taps × complex I/Q.
8. **M20 polyphase** — *completed*. Fused decim + interp with scipy-convention tap scaling on top of M19.
9. **M21 DDC** — *completed*. Fused complex-NCO + Kaiser-LPF + decim-by-4 on one AIE2 core; reuses M20's LPF prototype and adds an 8-sample cordic-free LO LUT.
10. **M22 DUC** — *completed*. Mathematical mirror of M21: fused zero-stuff interp-by-L=4 (polyphase, `taps *= L`) + 16-tap Kaiser LPF (reused from M20) + complex NCO at `+f_s/8` on one AIE2 core.
11. **M23 channelizer** — *completed*. Fused M=8 polyphase analysis bank (input commutator + M-path 8-tap Kaiser FIR + 8-point matmul-DFT with fully-embedded twiddles) on one AIE2 core; closes the DSP-track filtering & resampling block (M19–M23).

## Toolchain events

### 2026-08-14 — Upstream mlir-aie v1.4.1 runtime API break (pinned at commit `3ca0193`)

Upstream release [mlir-aie v1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1) (2026-08-11) reshaped the `aie.iron.Runtime` surface incompatibly with the pre-v1.4.1 tests. The Phoenix SDR-DSP regression is pinned at commit [`3ca0193` — "Retain executable per kernel handle to fix run_chain use-after-free"](https://github.com/Xilinx/mlir-aie/commit/3ca0193) (2026-08-14, v1.4.1 + 13 commits) because that commit additionally contains the `run_chain` executable-lifetime fix required by the parallel-DMA milestones (M9, M9b, M17p). The four API changes introduced at v1.4.1 are:

- The context-manager form `rt = Runtime(); with rt.sequence(...) as (...):` was removed. `Runtime.__init__` now requires a `seq_fn: Callable` positional argument, verified against [`python/iron/runtime/runtime.py`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py) at that revision.
- `rt.start(worker)` was replaced by passing workers directly to `Program(device, rt, workers=[...])`.
- `rt.task_group()` / `rt.finish_task_group(tg)` were replaced by a per-sequence [`TaskGroup`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/taskgroup.py) constructed inside the sequence body with `tg.finish()`.
- `rt.fill(fifo.prod(), buf, tap, task_group=tg)` was replaced by endpoint-native `prod_ep.fill(buf, tap=tap, group=tg)`, with the endpoints passed as `fn_args` to `Runtime(seq_fn, fn_args=[...])`. The canonical multi-worker + TaskGroup shape is documented in the upstream [runtime-sequence test suite](https://github.com/Xilinx/mlir-aie/blob/3ca0193/test/python/runtimesequence.py) and the single-core matmul example [`programming_examples/getting_started/03_matrix_multiplication_single_core/matrix_multiplication_single_core.py`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/programming_examples/getting_started/03_matrix_multiplication_single_core/matrix_multiplication_single_core.py).

An initial silicon sweep after the pull failed 14 of 16 milestones with an identical `Runtime.__init__() missing 1 required positional argument: 'seq_fn'` traceback. All 12 iron-based tests were ported to the new API in a single sweep:

- **Single-worker:** M3 SAXPY (new `tests/m3_saxpy/`, first canonical port using upstream [`saxpy.cc`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/programming_examples/getting_started/01_SAXPY/saxpy.cc)), M5 FIR, M6 mixer, M7 power, M8 fused pipeline, M10 modular arithmetic, M11 NTT butterfly, M13 16-point NTT, M14 256-point NTT, M15 cyclic polymul.
- **Multi-worker with `TaskGroup` + per-column taps:** M9 4-column FIR, M9b 4-column demod pipeline (2-input), M17-parallel 4-column FFT channelizer.

**Post-migration silicon sweep: 15 / 16 PASS** on Phoenix NPU1 (AIE2, Win11). Only `tests/m15b_negacyclic/` still used the low-level `aie.dialects` + `runtime_sequence` + `XRTTensor` API rather than `iron.Runtime`.

The iron ports of M3–M15 / M17 / M17p landed on `feat/m17-radix2-fft-npu`, fast-forwarded to `main`, and pushed as commit `1ec80c8`.

### 2026-08-15 — M15b iron.Runtime port closes the suite

M15b was rewritten to the M15 host shape: `@iron.jit`, `ExternalFunction`, two input `ObjectFifo`s plus one output, [`Runtime(seq_fn)`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py), `Program(..., workers=[...])`, and uint32 `XRTTensor` buffers (the v1.4.1 host tensor rejects `int32` [`same_kind`](https://numpy.org/doc/stable/reference/generated/numpy.can_cast.html) copies). The schoolbook kernel and [Barrett](https://link.springer.com/chapter/10.1007/3-540-47721-7_24) constants (`MU = 20165`, shift 26) are unchanged. Ring is the Kyber / [ML-KEM](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ring `Z_3329[x]/(x^256+1)`. Silicon result: bit-exact vs `negacyclic_polymul_ref`, seed 42. Full suite **16 / 16 PASS** in 17.46 s on Phoenix NPU1.

### 2026-08-15 — `install.py` + clean-clone 16/16

[`install.py`](../install.py) is on `main`. A real-user wipe-and-clone downloaded the published [mlir_aie 1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1) `cp313` wheel (not rolling [`latest-wheels-4`](https://github.com/Xilinx/mlir-aie/releases/expanded_assets/latest-wheels-4)), put VS `llvm-objcopy` on PATH for the [Peano Windows fixup](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/), and retried shallow fetch over HTTP/1.1. `run_all_silicon_tests.py` re-execs checkout `ironenv` because [`py`](https://docs.python.org/3/using/windows.html#python-launcher-for-windows) binds to system CPython. Clean-clone suite: **16/16 PASS** in 95.91 s (cold xclbin) on Phoenix NPU1.

## Divergences from master prompt §16 — honest disclosure

- **Repo's early M-numbers (M3, M5, M6) map to §16 concepts but with different exact scope.** M3 SAXPY covers §16 M3 pass-through with extra work; M5 FIR is not §16 M5 (vector-copy); M6 mixer is a subset of §16 M6 vector-arithmetic. Numbering is preserved for git history stability; canonical mapping documented in this table.
- **Repo M7, M8, M9 are DSP-track additions**, not the §16 SDR-integration milestones. This roadmap suffixes them `-ext` and reserves the canonical §16 M7/M8/M9 numbering for Track 2.
- **Two `m10_`, `m11_`, `m12_` test directories exist** (one Scheme A modular/NTT, one Scheme B parallel-pipeline/FFT). Step 2 of the "Immediate next steps" resolves this via renumbering.
- **FFT was originally shipped as direct O(N²) DFT.** As of the M17 v3 radix-4 Stockham port the shipped version is O(N log N) and aligns with §16 intent; the earlier direct-DFT prototype in `tests/m17_fft_dft/` is retained pending removal. Prior divergence documented for history.
- **SDR-integration milestones (M4, M7-canonical, M8-canonical, M9-canonical, M18, M28, M31) are all unshipped** — the master prompt's original ordering has them preceding the NTT track. In this repo they are deferred to Track 2 pending hardware.

## References

### Hardware architecture

- AMD, "AMD Ryzen™ 9 7940HS" — official product page; Phoenix NPU rated up to 10 TOPS. https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html
- Tom's Hardware, "The refresh that wasn't — AMD announces 'Hawk Point' Ryzen 8040" (2023-12-06) — AMD states XDNA1 delivers 10 TOPS INT8 on Phoenix 7040. https://www.tomshardware.com/pc-components/cpus/the-refresh-that-wasnt-amd-announces-hawk-point-ryzen-8040-series-with-zen-4-rdna3-and-xdna-teases-strix-point
- AMD, "AMD XDNA™ Architecture" — official product page describing the spatial-dataflow AI Engine tile array. https://www.amd.com/en/technologies/xdna.html
- The Linux Kernel, "AMD NPU" — canonical description of the XDNA1 4×5 topology and the `amdxdna` driver. https://docs.kernel.org/accel/amdxdna/amdnpu.html
- IEEE Computer Society, "AMD XDNA NPU in Ryzen AI Processors" (IEEE Micro, 2024). https://www.computer.org/csdl/magazine/mi/2024/06/10592049/1YtaXNWFBqE
- Wikipedia, "AI engine" — encyclopedic summary of the AIE2 VLIW SIMD tile organization. https://en.wikipedia.org/wiki/AI_engine
- Daniel Estévez, "Getting peak TOPS on a Ryzen AI 7 350 NPU" (2026) — practical account of XDNA1/XDNA2 tile-array organization and IRON/Peano toolchain usage. https://destevez.net/2026/05/getting-peak-tops-on-a-ryzen-ai-7-350-npu/

### Toolchain

- Xilinx (AMD), MLIR-AIE GitHub repository. https://github.com/Xilinx/mlir-aie
- IRON / MLIR-AIE documentation v1.4.1. https://xilinx.github.io/mlir-aie/1.4.1/
- AMD, "Leveraging the IRON AI Engine API to program the Ryzen AI NPU" (MICRO 2024 tutorial PDF). https://www.amd.com/content/dam/amd/en/documents/products/processors/ryzen/ai/iron-for-ryzen-ai-tutorial-micro-2024.pdf
- Xilinx (AMD), llvm-aie (Peano) GitHub repository. https://github.com/Xilinx/llvm-aie
- Stephen Neuendorffer, "Peano: LLVM support for AMD/Xilinx AI Engine processors" (LLVM Discourse, 2024). https://discourse.llvm.org/t/peano-llvm-support-for-amd-xilinx-ai-engine-processors/79458
- Phoronix, "AMD Releases MLIR-AIE 1.2 Compiler Toolchain" — Windows/WSL2 compatibility note. https://www.phoronix.com/news/AMD-MLIR-AIE-1.2

### Cooley-Tukey FFT

- J. W. Cooley and J. W. Tukey, "An algorithm for the machine calculation of complex Fourier series", *Math. Comput.* 19:297–301 (1965) — the original radix-2 FFT paper. https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf
- C. S. Burrus et al., "Fast Fourier Transforms" (Rice University OpenStax textbook chapter). https://repository.rice.edu/server/api/core/bitstreams/01e9e0a5-fa6f-453d-a1b5-8209fa0a565c/content
- Brian McFee, "Digital Signals Theory §8.2 — Radix-2 Cooley-Tukey". https://brianmcfee.net/dstbook-site/content/ch08-fft/FFT.html

### Number-Theoretic Transform (Kyber / ML-KEM)

- Emergent Mind, "Number Theoretic Transform (NTT)" survey with Cooley-Tukey / Gentleman-Sande butterfly formulation. https://www.emergentmind.com/topics/number-theoretic-transform-ntt
- Ingonyama ICICLE documentation, "NTT — Number Theoretic Transform". https://dev.ingonyama.com/2.8.0/icicle/primitives/ntt
- "Algorithm-Targeted NTT hardware acceleration via Design-Time Specialization" (arXiv 2601.17806, 2026) — ML-KEM/Kyber ring parameters `(q, N) = (3329, 256)`. https://arxiv.org/html/2601.17806v1
- "Area-time efficient pipelined number theoretic transform for CRYSTALS-Kyber" (PLOS ONE, 2025) — Barrett reduction algorithm at `q = 3329`. https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0323224&type=printable
- Isabelle/AFP, "δ-Correctness Proof of CRYSTALS-KYBER with Number Theoretic Transform" — formalization of the negacyclic ring `Z_q[x]/(x^N + 1)`. https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf
- NIST, FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard* (2024-08-13) — official ML-KEM ring `R_q = Z_q[X]/(X^n+1)` with `(n, q) = (256, 3329)`. https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 203 landing page. https://csrc.nist.gov/pubs/fips/203/final
- NIST, FIPS 202, *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions* (2015). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf
- NIST Post-Quantum Cryptography project. https://csrc.nist.gov/projects/post-quantum-cryptography
- NIST CAVP. https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program
- NIST cryptographic example values. https://csrc.nist.gov/projects/cryptographic-standards-and-guidelines/example-values
- Avanzi et al., *CRYSTALS-Kyber* Algorithm Specification v3.02 (2021-08-04). https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf
- P. Barrett, "Implementing the Rivest Shamir and Adleman Public Key Encryption Algorithm on a Standard Digital Signal Processor", CRYPTO 1986. https://link.springer.com/chapter/10.1007/3-540-47721-7_24
- T. G. Stockham, Jr., "High-speed convolution and correlation", AFIPS 1966. https://dl.acm.org/doi/10.1145/1464182.1464209
- W. M. Gentleman and G. Sande, "Fast Fourier Transforms — for fun and profit", AFIPS 1966. https://dl.acm.org/doi/10.1145/1464291.1464352
- K. Ozaki, T. Ogita, S. Oishi, S. M. Rump, "Error-free transformations of matrix multiplication…", *Numerical Algorithms* 59:95–118 (2012). https://doi.org/10.1007/s11075-011-9478-1
- N. J. Higham, *Accuracy and Stability of Numerical Algorithms*, 2nd ed., SIAM (2002). https://doi.org/10.1137/1.9780898718027
- Native Windows IRON guide, mlir-aie 1.4.1. https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
- AMD, FFT_R4_AIE. https://github.com/diacccc/FFT_R4_AIE

### Project-internal references

- Canonical milestone plan: `../Phoenix-SDR-DSP-Master-Prompt.md` §16
- Shipped milestone details: `MILESTONES_AND_MATHEMATICS.md`
- Engineering rules: master prompt §13
- Response format for new milestones: master prompt §20
