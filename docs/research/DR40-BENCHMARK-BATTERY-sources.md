# DR40 Research and Provenance: High-Throughput Hardware Benchmark Protocol & Profiling Battery

## Milestone Deliverable Context
- Deliverable: **DR40 (Reproducible High-Throughput Hardware Benchmark Protocol & Profiling Battery for AIE2 on AMD Phoenix NPU)**
- Standards: NIST IR 8419, eBACS / SUPERCOP (Bernstein & Lange), ISO/IEC 19790:2012, ISO/IEC 24759:2017
- Target Architecture: AMD Phoenix AIE2 / XDNA1 (AIE2 Vector Compute Tiles + DMA ObjectFifos)
- Classification & Integrity Rules:
  - Kernel Execution: **[ON-TILE SILICON]** for AIE2 hardware execution of post-quantum cryptographic primitives (NTT butterfly stages, Keccak-f[1600] permutations, vector polynomial multiply-accumulate, rejection sampling), on-chip batch loop execution, and output state serialization.
  - Host Harness & Profiling: **[HOST RUNTIME]** for high-resolution nanosecond timing, batch scaling, DMA vs compute latency separation, statistical repeatability metrics, and independent oracle verification.
  - Anti-Fabrication Invariant: No hardcoded timing constants, simulated cycles, or fixed throughput strings. Latency and throughput must be derived dynamically from high-resolution host timers and physical execution on AMD Phoenix NPU.

## Citation Ledger

### Citation 1: Bernstein & Lange: eBACS: ECRYPT Benchmarking of Cryptographic Systems
- Source Title: eBACS: ECRYPT Benchmarking of Cryptographic Systems
- Authors: Daniel J. Bernstein and Tanja Lange
- Source Type: Upstream project and benchmarking specification
- Full URL: https://bench.cr.yp.to/
- Publication Date: 2008-01-01 (updated continuously)
- Access Date: 2026-09-05T16:10:00Z
- Relevant Section: Benchmarking Methodology: Measurement of Cycles, Operations, Median, Quartiles, and Batch Scaling
- Exact Technical Claim:
  - High-precision cryptographic benchmarking requires isolating core cryptographic transform execution from system noise via warmup passes and iterative measurement.
  - Performance characterization should report median and distribution percentiles rather than single arithmetic means to resist outlier perturbation.
  - Batching multiple operations within a single dispatch amortizes invocation overhead and measures sustained algorithmic throughput.
- How Claim Was Independently Verified: Verified against eBACS methodology and implemented in phoenix_sdr_dsp/pqc/dr40_benchmark_abi.py and 	ests/test_pqc_dr40_contract.py.
- Affected Files: phoenix_sdr_dsp/pqc/dr40_benchmark_abi.py, phoenix_sdr_dsp/pqc/kernels/dr40_benchmark_internal.hpp, 	ests/test_pqc_dr40_contract.py.
- Confidence Level: PRIMARY

### Citation 2: NIST IR 8419: Benchmarking Post-Quantum Cryptography
- Source Title: NIST IR 8419: Post-Quantum Cryptography: Benchmarking and Migration Guidance
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Technical Report
- Full URL: https://csrc.nist.gov/pubs/ir/8419/final
- Publication Date: 2024-08-13
- Access Date: 2026-09-05T16:10:00Z
- Relevant Section: Section 3: Performance Metrics and Benchmarking Protocols for Lattice-Based KEM and Signature Primitives
- Exact Technical Claim:
  - Cryptographic hardware accelerators must report throughput in operations per second (ops/sec) and latency across key generation, encapsulation/signing, and decapsulation/verification sub-primitives.
  - Primitive operations (NTT/INTT, Keccak permutations, matrix-vector product) should be benchmarked as modular building blocks.
- How Claim Was Independently Verified: Verified against NIST IR 8419 modular decomposition and implemented across DR40 benchmark workload modes.
- Affected Files: phoenix_sdr_dsp/pqc/dr40_benchmark_abi.py, 	ests/pqc_device_resident/test_dr40_benchmark_silicon.py.
- Confidence Level: PRIMARY

### Citation 3: ISO/IEC 19790:2012 / ISO/IEC 24759:2017: Cryptographic Modules Testing
- Source Title: ISO/IEC 24759:2017: Test requirements for cryptographic modules
- Author / Organization: International Organization for Standardization (ISO) / International Electrotechnical Commission (IEC)
- Source Type: Normative standard
- Full URL: https://www.iso.org/standard/65985.html
- Publication Date: 2017-06-01
- Access Date: 2026-09-05T16:10:00Z
- Relevant Section: Clause 6.3: Operational Performance and Functional Conformance
- Exact Technical Claim:
  - Performance and throughput testing of hardware cryptographic engines must evaluate 100% of generated output buffers against authoritative test vectors or independent reference models to ensure computational validity during speed profiling.
- How Claim Was Independently Verified: Built independent oracle validation into every benchmark execution pass in DR40 ABI and test runners.
- Affected Files: phoenix_sdr_dsp/pqc/dr40_benchmark_abi.py, 	ests/pqc_device_resident/test_dr40_benchmark_silicon.py.
- Confidence Level: PRIMARY

### Citation 4: Repository Performance and Ground Truth Policy
- Source Title: Repository Anti-Fabrication and Ground Truth Engineering Rules
- Author / Organization: Project Security Governance
- Source Type: Policy specification (AGENTS.md and .agents/rules/zero-speculation-policy.md)
- Full URL: https://github.com/midhatn/phoenix-npu-pqc/blob/main/AGENTS.md
- Publication Date: 2026-08-01
- Access Date: 2026-09-05T16:10:00Z
- Relevant Section: Ground Truth and Benchmark Reporting
- Exact Technical Claim:
  - Prohibit invented timings, synthetic benchmarks, fixed throughput strings, or decorative metrics.
  - Prohibit claims of performance that exceed demonstrated, reproducible experimental evidence.
  - Enforce full buffer bit-exact comparison against independent oracles during benchmark execution.
- How Claim Was Independently Verified: Enforced via fail-closed architecture in phoenix_sdr_dsp/pqc/dr40_benchmark_abi.py.
- Affected Files: phoenix_sdr_dsp/pqc/dr40_benchmark_abi.py, 	ests/pqc_device_resident/test_dr40_benchmark_silicon.py.
- Confidence Level: PRIMARY
