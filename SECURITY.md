# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Phoenix SDR-DSP, please **do not**
open a public GitHub issue. Instead, report it privately so it can be
investigated and disclosed responsibly.

### How to report

Preferred: use GitHub's **Private Vulnerability Reporting**
(Security tab → "Report a vulnerability").

Alternative: email **medhat.nashar@gmail.com** with the subject line
`[phoenix-sdr-dsp SECURITY]`.

Please include, if possible:

- A description of the vulnerability and its potential impact
- Steps to reproduce (host OS/build, NPU driver + firmware version, XRT
  version, milestone / test file, sample inputs)
- Any proof-of-concept code, kernel dump, or `xrt-smi` capture
- Your name/handle for acknowledgment (or "anonymous" if preferred)

You should receive an initial response within **7 days**. If the issue is
confirmed, we will work on a fix and coordinate a disclosure timeline with you.

## Scope

**In scope:**

- Kernel logic bugs in `include/sdr_dsp/*.hpp` and `tests/m*/` (incorrect
  modular arithmetic, NTT twiddle stride errors, off-by-one indexing, buffer
  overruns in AIE tile local memory).
- Host-side XRT dispatch logic in test drivers (`test_*_m*.py`) that could
  crash the NPU, corrupt DMA buffers, or hang XRT.
- Numerical correctness regressions that break bit-exact verification against
  reference implementations.
- Reproducibility issues in the toolchain lock (`toolchain.yaml`,
  `scripts/bootstrap_env.ps1`).

**Out of scope (report upstream):**

- Bugs in the AMD XDNA driver → https://github.com/amd/xdna-driver
- Bugs in MLIR-AIE / IRON → https://github.com/Xilinx/mlir-aie
- Bugs in LLVM Peano → https://github.com/Xilinx/llvm-aie
- Bugs in XRT itself → https://github.com/Xilinx/XRT

## Supported Versions

Only the latest `main` branch receives security fixes. Once tagged releases
exist, this table will list supported versions.

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

## Safe Harbor

Good-faith security research conducted according to this policy will not
result in legal action from the maintainer. We consider "good faith" to include:

- Avoiding privacy violations, destruction of data, and disruption to others.
- Only interacting with test accounts and hardware you own or have explicit
  permission to test.
- Giving reasonable time to remediate before public disclosure.
