# Phoenix SDR-DSP v1.1.0 Roadmap

Post-v1.0.0 development plan. Every claim in this document is intended to be citable to a primary source; the References section at the bottom collects all sources with canonical URLs.

Related: [`ROADMAP.md`](ROADMAP.md) covers milestones through v1.0.0 (M3, M5–M15, M15b, M17, M17p, M19–M27, M32b/c/d/e, M33a/b/d/e — **34 / 34 PASS on Phoenix NPU1**). This document extends that plan.

## Positioning statement for v1.1.0

v1.0.0 is a **correctness** release: 33 milestones and 34 test invocations validated bit-exact against reference implementations and, for the Post-Quantum Cryptography track, against the [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server) known-answer test vectors for [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) and [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf).

v1.1.0 extends v1.0.0 along three orthogonal tracks. Each track is independently valuable and independently releasable — a mini-release for any completed track is acceptable and encouraged. None of the tracks invalidates a v1.0.0 claim.

- **Track A — RF-live SDR demonstrations.** Feed one or more M19–M27 milestones with captured or over-the-air I/Q instead of synthetic test vectors.
- **Track B — CPU-baseline benchmarks.** Add measured throughput and latency numbers for representative kernels vs. a same-laptop Zen 4 CPU baseline, so future claims of the form "runs faster / comparably / slower on the NPU" are backed by numbers.
- **Track C — Community integration.** Prepare the artifacts that let the project be adopted, referenced, or extended by third parties — a stripped-down IRON example contribution, a GNU Radio out-of-tree module skeleton, and reproducible bench scripts.

## Status legend (reused from `ROADMAP.md`)

- ✅ **Shipped** — silicon-validated on physical NPU, bit-accurate against CPU reference where applicable, present in `run_all_silicon_tests.py`.
- 🚧 **Next up** — no hardware dependency, actively planned.
- 🔒 **Deferred — SDR hardware** — blocked pending acquisition of a supported SDR device.
- 📋 **Planned — v1.1.0** — targeted for this roadmap, no hardware or research blocker known.
- 💡 **Optional / research** — post-v1.1.0.

---

## Track A — RF-live SDR demonstrations

### A1. M25L — PSK receiver with captured I/Q loopback

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Depends on | M25 (silicon-validated, shipped v1.0.0) |
| Hardware | None (offline I/Q file playback) |
| Deliverable | `tests/m25L_psk_capture/` — reads a `.sigmf-data` / `.sigmf-meta` I/Q capture, dispatches to the M25 kernel, decodes the payload, compares against an expected bit sequence stored alongside the capture |
| Reference format | [SigMF v1.0.0](https://github.com/sigmf/SigMF) — the canonical format for interchange of recorded RF signals |
| Test-vector source | One of: [PySDR reference captures](https://pysdr.org/content/rds.html); [SigMF example dataset](https://github.com/sigmf/SigMF-datasets); a laptop-recorded RTL-SDR capture of a known local transmitter |
| Acceptance | Bit-exact demod of the target payload from at least one publicly shared capture, plus a documented reproduction recipe (capture link + `sha256`) |

Rationale: M25 today validates against synthetic constellations. A SigMF-file loopback closes the correctness-to-realism gap without requiring the user to own SDR hardware. It also produces a downloadable artifact that reviewers can re-verify.

### A2. M26L — QAM-16 receiver with captured I/Q loopback

Same shape as A1, targeting M26 (fused QAM-16 receiver with soft-decision LLR demapping). Depends on A1's SigMF loader plumbing so A1 lands first.

### A3. M27L — OFDM demodulator against a public Wi-Fi / DVB-T capture

Higher effort, more valuable. M27 currently runs an OFDM loopback against synthetic subcarriers; A3 replaces the transmit side with a captured [802.11a / g](https://standards.ieee.org/ieee/802.11/7028/) or [DVB-T](https://www.etsi.org/deliver/etsi_en/300700_300799/300744/01.06.01_60/en_300744v010601p.pdf) burst. Depends on A1 + A2 plumbing.

### A4. LimeSDR live-radio ingest (optional, hardware-blocked)

| Field | Value |
|---|---|
| Status | 🔒 Deferred — SDR hardware |
| Hardware | [LimeSDR-USB](https://limemicro.com/products/boards/limesdr/) or [LimeSDR-Mini v2.2](https://limemicro.com/products/boards/limesdr-mini-2-0/) |
| Deliverable | Streaming ingest via [SoapySDR](https://github.com/pothosware/SoapySDR) → ring buffer → NPU dispatch, at a bandwidth the NPU can sustain |
| Acceptance | Continuous demod of a live over-the-air signal (FM broadcast is easiest) for ≥ 60 seconds without buffer underruns |

Unblocks the SigMF-optional path — instead of playing a file back, users tune a real radio. This is the milestone SDR-community forums (r/RTLSDR, GNU Radio, ham radio) will ask about first.

---

## Track B — CPU-baseline benchmarks

### B1. Benchmark harness — `bench/run_bench.py`

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Deliverable | Python harness that measures wall-clock and CPU-time throughput for a named kernel on both (a) Phoenix NPU dispatch and (b) Zen 4 CPU reference at native AVX2 |
| Baselines | Zen 4 AVX2 reference for each benchmarked kernel, running single-threaded on the same host laptop |
| Metrics | Median of ≥ 100 runs; report median + 95th percentile latency, operations / second, and NPU / CPU ratio |
| Output | `bench/results/<milestone>_<git-sha>_<date>.json`, indexed under `bench/results/index.md` |

Design constraints:
- Warm-up run excluded from the sample
- xclbin cache pre-warmed before timed dispatch (mirrors real steady-state use)
- CPU baseline uses a NumPy + [SciPy](https://scipy.org/) reference where one exists; otherwise a hand-written AVX2 C reference compiled with the same LLVM version as Peano to keep the compiler variable pinned

### B2. First benchmarked kernels

| Kernel | Why this one first |
|---|---|
| M32b — NTT over `Z_3329` (ML-KEM NTT, n = 256) | Small, well-defined, has a canonical reference: [pq-crystals `kyber/ref/ntt.c`](https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c). The comparison against AVX2 kyber-py or the AVX2 reference is a clean single-number claim. |
| M33a — NTT over `Z_8380417` (ML-DSA NTT, n = 256) | Same reasoning, larger modulus, longer twiddle. Canonical reference: [pq-crystals `dilithium/ref/ntt.c`](https://github.com/pq-crystals/dilithium/blob/main/ref/ntt.c). |
| M23 — channelizer | SDR-representative and well-studied. Reference: [`scipy.signal.resample_poly`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html) or the polyphase equivalent from [PySDR §Multirate](https://pysdr.org/content/multirate.html). |
| M16 — Stockham FFT | Already CPU-referenced in v1.0.0; useful to publish alongside the NPU number for scale. Reference: [`scipy.fft.fft`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.fft.fft.html) with the same input. |

Deliverable acceptance: for each of the four kernels, a published JSON file plus one paragraph in `docs/BENCHMARKS.md` stating the median NPU throughput, the median CPU-baseline throughput, and the ratio, with the reproduction command. **No performance claim without a published number.**

### B3. Power measurement (optional, hardware-dependent)

| Field | Value |
|---|---|
| Status | 💡 Optional / research |
| Blocker | Requires access to package-level power counters ([AMD µProf](https://www.amd.com/en/developer/uprof.html) or platform Energy-Aware Runtime) on the specific SKU |
| Deliverable | Report energy per operation (J / op) alongside throughput for the B2 kernels |

Only worth doing after B2 numbers exist. Energy claims are the strongest promotional angle for NPU workloads but also the easiest to get wrong.

---

## Track C — Community integration

### C1. Upstream IRON `programming_examples/` contribution

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Depends on | Green light from IRON / MLIR-AIE maintainers on [`Xilinx/mlir-aie` Discussion #3556](https://github.com/Xilinx/mlir-aie/discussions/3556) |
| Deliverable | A single-kernel example matching the conventions of [`programming_examples/basic/`](https://github.com/Xilinx/mlir-aie/tree/main/programming_examples/basic) — most likely the M32b NTT over `Z_3329` or the M19 complex FIR |
| Acceptance | Merged upstream, or explicit maintainer feedback recorded and applied |

If the Discussion doesn't get a green light, this becomes a documented standalone example under `phoenix-sdr-dsp/examples/iron_upstream/` for anyone who wants to adopt it.

### C2. GNU Radio out-of-tree module skeleton — `gr-phoenix`

| Field | Value |
|---|---|
| Status | 💡 Optional / research |
| Deliverable | An out-of-tree GNU Radio module ([`gr-modtool`](https://wiki.gnuradio.org/index.php?title=Out-of-tree_modules) generated) wrapping one Phoenix kernel as a GR block. FIR (M19) is the natural first candidate |
| Acceptance | The block can be instantiated in [GNU Radio Companion](https://wiki.gnuradio.org/index.php/GNURadioCompanion) and passes a synthetic signal through the NPU-backed FIR |

Deferred to research because GR out-of-tree modules built on Windows against a native-Windows NPU dispatch path have no established prior art; expect friction. Landing this unlocks the entire GNU Radio community as an adjacent audience.

### C3. Reproducibility artifacts

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Deliverable | (a) A CITATION.cff bump referencing v1.1.0; (b) a Zenodo-archived release for the v1.0.0 tag so it has a citable DOI; (c) a `SECURITY.md` covering the PQC track since users may reasonably ask "should I use this for real crypto?" — the answer is documented as "no, this is a bit-exact reference for standards compliance, not a hardened deployment library" |

Rationale: (a) and (b) make the project citable in academic writing; (c) inoculates against a class of misunderstanding that would otherwise land in the issue tracker.

### C4. AMD Vitis-Tutorials `Developer_Contributed/` submission

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Deliverable | A self-contained tutorial under [`Vitis-Tutorials/Developer_Contributed/`](https://github.com/Xilinx/Vitis-Tutorials/tree/main/Developer_Contributed) walking through one Phoenix SDR/DSP kernel end-to-end on Ryzen AI + IRON — most likely M19 complex FIR or M20 polyphase resampler |
| Precedent | [`Developer_Contributed/02-AIE_DSP_with_Makefile_and_GUI`](https://github.com/Xilinx/Vitis-Tutorials/tree/main/Developer_Contributed/02-AIE_DSP_with_Makefile_and_GUI) — an older DSP-on-AIE tutorial targeting VCK190 with the classic Vitis 2024.1 flow. Explicitly warns "has not been validated with the latest Vitis release", leaving an open gap for a modern Ryzen-AI / IRON DSP tutorial |
| Requirements | Signed commits (`git commit -s`), MIT license header, README with tool versions and setup, source + scripts only (no binaries), target the current release branch |
| Acceptance | Merged into `Developer_Contributed/`, or explicit maintainer feedback recorded and applied |

### C5. `kyber-py` downstream-user issue

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Deliverable | A GitHub issue on [`GiacomoPope/kyber-py`](https://github.com/GiacomoPope/kyber-py) documenting Phoenix SDR/DSP as an ACVP-validated downstream user of `kyber-py==1.0.1` for the M32e ML-KEM composer oracle |
| Purpose | Establishes a public reference from the canonical Python ML-KEM implementation back to this project; gives the maintainer a datapoint on how the library is being used |

### C6. `dilithium-py` downstream-user issue

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Deliverable | A GitHub issue on [`GiacomoPope/dilithium-py`](https://github.com/GiacomoPope/dilithium-py) documenting Phoenix SDR/DSP as an ACVP-validated downstream user of `dilithium-py==1.4.0` for the M33d KeyGen and M33e Sign / Verify composer oracles |
| Purpose | Same as C5, for the ML-DSA oracle path |

### C7. Open Quantum Safe (`liboqs`) community post

| Field | Value |
|---|---|
| Status | 📋 Planned — v1.1.0 |
| Deliverable | A Show-and-Tell style post in [`open-quantum-safe/liboqs`](https://github.com/open-quantum-safe/liboqs) Discussions (or an issue if Discussions are not enabled) describing the M32 / M33 Phoenix NPU implementation of FIPS 203 and FIPS 204, its ACVP KAT validation, and its relationship to `liboqs` (complementary reference-implementation target on non-cryptographic silicon, not a competing production library) |
| Purpose | Reaches the largest active PQC-implementation community on GitHub; establishes visibility in a venue that predates FIPS 203 / 204 and that all serious PQC library authors track |

---

## Milestone numbering

Following the v1.0.0 convention, new milestones extend the sequence:

| Existing | v1.1.0 extension |
|---|---|
| M25 (PSK RX, synthetic) | **M25L** (PSK RX, live-capture loopback) |
| M26 (QAM RX, synthetic) | **M26L** (QAM RX, live-capture loopback) |
| M27 (OFDM loopback, synthetic) | **M27L** (OFDM, captured Wi-Fi / DVB-T burst) |
| — | **M34** (LimeSDR ingest, hardware-blocked) |

Benchmarks and community-integration artifacts are numbered `B1`, `B2`, `B3`, `C1`, `C2`, `C3` inside this document rather than folded into the M-series, since they aren't silicon-milestones in the same sense.

## Release cut criteria for v1.1.0

The v1.1.0 tag can be cut when **at least one milestone from Track A** and **at least the B1 harness plus one B2 kernel** are landed. Track C is not blocking. This lets v1.1.0 land as soon as there is one honest, defensible new claim to make, rather than gating on the full plan.

If Track A slips (SDR-hardware acquisition, capture curation, etc.), an interim **v1.0.1** release covering Track B alone is acceptable. If Track A lands first, **v1.0.1** covering just RF-live is also acceptable. The point is to release when there is something new to say, not to accumulate.

## Non-goals for v1.1.0

To keep scope honest, these are explicitly **out of scope**:

- **New kernels beyond the 33 shipped in v1.0.0.** v1.1.0 is about deepening what exists, not widening it.
- **A hardened production PQC library.** The M32 / M33 composers are FIPS-compliant *reference* implementations validated against ACVP-Server KATs. They are not side-channel-hardened, not constant-time-audited, and not intended for deployment. `SECURITY.md` (C3) will state this in-repo.
- **Cross-platform support (Linux, WSL, macOS).** [`M1_ARCHITECTURE_DECISION.md`](M1_ARCHITECTURE_DECISION.md) documents why native Windows is the only supported host today. Revisiting that is a v2 concern.

## References

- Phoenix v1.0.0 release notes — [github.com/midhatn/phoenix-sdr-dsp/releases/tag/v1.0.0](https://github.com/midhatn/phoenix-sdr-dsp/releases/tag/v1.0.0)
- IRON / MLIR-AIE Discussion #3556 — [github.com/Xilinx/mlir-aie/discussions/3556](https://github.com/Xilinx/mlir-aie/discussions/3556)
- SigMF specification v1.0.0 — [github.com/sigmf/SigMF](https://github.com/sigmf/SigMF)
- SigMF example datasets — [github.com/sigmf/SigMF-datasets](https://github.com/sigmf/SigMF-datasets)
- PySDR textbook — Marc Lichtman, [pysdr.org](https://pysdr.org/)
- pq-crystals reference implementations — [pq-crystals/kyber](https://github.com/pq-crystals/kyber), [pq-crystals/dilithium](https://github.com/pq-crystals/dilithium)
- NIST ACVP-Server — [github.com/usnistgov/ACVP-Server](https://github.com/usnistgov/ACVP-Server)
- SoapySDR — [github.com/pothosware/SoapySDR](https://github.com/pothosware/SoapySDR)
- LimeSDR hardware — [limemicro.com](https://limemicro.com/products/boards/limesdr/)
- GNU Radio out-of-tree modules — [wiki.gnuradio.org — Out-of-tree modules](https://wiki.gnuradio.org/index.php?title=Out-of-tree_modules)
- AMD µProf power profiler — [amd.com/en/developer/uprof.html](https://www.amd.com/en/developer/uprof.html)
- IEEE 802.11 — [standards.ieee.org/ieee/802.11/7028](https://standards.ieee.org/ieee/802.11/7028/)
- ETSI DVB-T EN 300 744 — [etsi.org — EN 300 744](https://www.etsi.org/deliver/etsi_en/300700_300799/300744/01.06.01_60/en_300744v010601p.pdf)
- Zenodo — [zenodo.org](https://zenodo.org/)
- SciPy signal processing — [scipy.org](https://scipy.org/); [scipy.signal.resample_poly](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html); [scipy.fft.fft](https://docs.scipy.org/doc/scipy/reference/generated/scipy.fft.fft.html)
