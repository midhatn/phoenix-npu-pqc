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
| M0 | Windows + WSL2 environment audit | ✅ | `scripts/windows/`, `scripts/wsl2/`, `audit/` |
| M1 | Native Windows architecture decision | ✅ | `docs/M1_ARCHITECTURE_DECISION.md` |
| M2 | Pinned Windows toolchain | ✅ | `docs/M2_TOOLCHAIN_PIN.md`, `toolchain.yaml` |

The native-Windows execution path is used because MLIR-AIE and Peano have first-class Windows/WSL2 support ([MLIR-AIE 1.2 release notes on Windows Subsystem for Linux compatibility, Phoronix](https://www.phoronix.com/news/AMD-MLIR-AIE-1.2)) and because WSL2 cannot directly access the NPU hardware (the `amdxdna` driver binds to the Windows host, per [Linux amdxdna documentation](https://docs.kernel.org/accel/amdxdna/amdnpu.html)).

## Track 1 — NPU DSP kernels (active)

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
| M10-ext | 4-column parallel multi-stage demodulator pipeline | 🧪 | `tests/m9b_parallel_pipeline/`. Present in tree, not in regression runner. To be integrated as an M9-ext companion. |

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
| M15+ | Negacyclic polynomial multiplication (`Z_q[x]/(x^N + 1)`) | ✅ | `tests/m15b_negacyclic/`. Repo currently labels this M16; canonically an extension of M15. The negacyclic ring `Z_q[x]/(x^N + 1)` is the Kyber ring, per [Isabelle/AFP CRYSTALS-Kyber formalization](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf). To be renumbered to avoid collision with §16 M16 (CPU FFT reference). |

### FFT track (canonical §16 M16–M18)

The Fast Fourier Transform in radix-2 form is the [Cooley–Tukey algorithm (1965)](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf), which reduces the DFT operation count from O(N²) to O(N log N) by recursive decomposition into even/odd subsequences ([Rice University FFT tutorial](https://repository.rice.edu/server/api/core/bitstreams/01e9e0a5-fa6f-453d-a1b5-8209fa0a565c/content); [Brian McFee, Digital Signals Theory §8.2](https://brianmcfee.net/dstbook-site/content/ch08-fft/FFT.html)).

| M# | Focus | Status | Notes |
|---|---|---|---|
| M16 | CPU DFT/FFT reference | ✅ | `tests/m16_fft_ref/test_fft_reference_m16.py`. Three independent implementations cross-validated: direct O(N²) DFT via twiddle matrix, recursive radix-2 [Cooley-Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf) FFT, iterative in-place radix-2 FFT with bit-reversed permutation (dataflow proxy for the M17 NPU kernel). All match NumPy [`fft.fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html) to double-precision round-off (~1e-13 relative). Tests: impulse, DC constant, pure tone, random complex, x = IFFT(FFT(x)) round-trip, Parseval energy conservation. Sizes N ∈ {8, 16, 32, 64, 128, 256, 512, 1024}. Runs on Ubuntu in CI in ~0.3 s. |
| M17 | NPU FFT/IFFT | 🧪 | Shipped as 64-point direct DFT in bfloat16 (`tests/m17_fft_dft/`). Silicon-validated against NumPy with `atol=0.1`. **Honest caveat**: implementation is a direct O(N²) DFT, not the radix-2/radix-4 O(N log N) butterfly implementation ([Cooley-Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf)) that §16 implies. The direct DFT is easier to vectorize on AIE2's 512-bit vector datapath ([AI Engine Wikipedia summary](https://en.wikipedia.org/wiki/AI_engine)) but does not scale beyond small N. Radix-butterfly version tracked as M17-butterfly. To be renumbered and integrated into regression runner. |
| M17-parallel | 4-column parallel NPU FFT | 🧪 | `tests/m17p_fft_parallel/`. Parallel channelizer variant of M17 using multiple AIE2 tile columns. |
| M17-butterfly | NPU FFT via radix-2/radix-4 Cooley-Tukey butterflies | 🚧 | Follow-up to M16/M17 to align implementation with §16 intent and achieve O(N log N) complexity. Reuses the modular-arithmetic butterfly pattern from `tests/m11_butterfly/` adapted to complex bfloat16 twiddle factors. |
| M18 | Streaming FFT spectrum analyzer connected to SDR | 🔒 | Requires SDR hardware. |

### Filtering & resampling (canonical §16 M19–M23)

| M# | Focus | Status | Notes |
|---|---|---|---|
| M19 | Complex FIR filter | ✅ (partial) | Real-valued 8-tap FIR shipped as current `tests/m5_fir/`. Complex-valued (complex taps × complex I/Q input) variant is the canonical M19 gap. |
| M20 | Polyphase decimation & interpolation | 🚧 | No hardware dependency. Post-M17-butterfly. |
| M21 | Digital downconverter (DDC) | 🚧 | Builds on M6 mixer + M19 complex FIR + M20 polyphase. |
| M22 | Digital upconverter (DUC) | 🚧 | Symmetric with M21. |
| M23 | Channelizer & filter bank | 🚧 | Uses M17 FFT + M19 FIR. `m17p_fft_parallel` is a partial prototype. |

### Modulation & synchronization (canonical §16 M24–M27, partially SDR-blocked)

| M# | Focus | Status | Notes |
|---|---|---|---|
| M24 | Correlation, preamble detection, packet sync | 🚧 | Partially runnable on synthetic vectors; full validation needs SDR. Correlation kernel can be prototyped now. |
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

## Immediate next steps (v0.3 series)

Ordered by dependency:

1. **v0.2.1 polish** (in progress): dependabot, CI badge in README, delete duplicate `LICENSE.md`, publish v0.2 release tag.
2. **Directory renumbering pass** — *completed in v0.2.1*. The Scheme B directories have been renamed to align with §16 canonical: `tests/m10_benchmark/` → `tests/m9b_parallel_pipeline/`, `tests/m11_fft/` → `tests/m17_fft_dft/`, `tests/m12_fft_parallel/` → `tests/m17p_fft_parallel/`, `tests/m16_negacyclic/` → `tests/m15b_negacyclic/`. Blob SHAs preserved so `git log --follow` still tracks each file's history. Integration into `run_all_silicon_tests.py` (currently only wires Scheme A milestones M3–M15) is tracked separately.
3. **M16 CPU FFT reference** — *completed*. Shipped as `tests/m16_fft_ref/test_fft_reference_m16.py` with three cross-validated implementations (direct O(N²) DFT, recursive radix-2 [Cooley-Tukey](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf), iterative in-place with bit-reversal). Wired into the CI `cpu-reference-tests` job so every push runs it on Ubuntu. Serves as the ground-truth oracle for M17.
4. **M17-butterfly**: implement radix-2 (and optionally radix-4) FFT via the shipped M11 NTT-butterfly pattern adapted to complex bfloat16 twiddles, replacing the direct DFT with an O(N log N) implementation.
5. **M19 complex FIR**: extend the shipped real-valued FIR to complex-valued taps and complex I/Q input.
6. **M20 polyphase**: decimation + interpolation on top of M19.

## Divergences from master prompt §16 — honest disclosure

- **Repo's early M-numbers (M3, M5, M6) map to §16 concepts but with different exact scope.** M3 SAXPY covers §16 M3 pass-through with extra work; M5 FIR is not §16 M5 (vector-copy); M6 mixer is a subset of §16 M6 vector-arithmetic. Numbering is preserved for git history stability; canonical mapping documented in this table.
- **Repo M7, M8, M9 are DSP-track additions**, not the §16 SDR-integration milestones. This roadmap suffixes them `-ext` and reserves the canonical §16 M7/M8/M9 numbering for Track 2.
- **Two `m10_`, `m11_`, `m12_` test directories exist** (one Scheme A modular/NTT, one Scheme B parallel-pipeline/FFT). Step 2 of the "Immediate next steps" resolves this via renumbering.
- **FFT is shipped as direct O(N²) DFT, not O(N log N) butterfly.** §16 implies butterfly; the shipped version is direct DFT. Documented on the M17 line above with a butterfly follow-up planned.
- **SDR-integration milestones (M4, M7-canonical, M8-canonical, M9-canonical, M18, M28, M31) are all unshipped** — the master prompt's original ordering has them preceding the NTT track. In this repo they are deferred to Track 2 pending hardware.

## References

### Hardware architecture

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

### Project-internal references

- Canonical milestone plan: `../Phoenix-SDR-DSP-Master-Prompt.md` §16
- Shipped milestone details: `MILESTONES_AND_MATHEMATICS.md`
- Engineering rules: master prompt §13
- Response format for new milestones: master prompt §20
