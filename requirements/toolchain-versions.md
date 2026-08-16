# Verified Native Windows Toolchain

This project was validated on a native Windows environment targeting the AMD Phoenix NPU.

## Host Platform

| Component | Verified value |
|---|---|
| Operating system | Windows 11 Pro, build 26200.9168 |
| System | ASUS TUF Gaming A15 FA507XI |
| Processor | [AMD Ryzen 9 7940HS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) with Radeon 780M Graphics |
| NPU | AMD Phoenix NPU ([XDNA1 / AIE2](https://docs.kernel.org/accel/amdxdna/amdnpu.html)) |
| Git | 2.48.1.windows.1 |
| Python | 3.13.15 |
| CMake | 4.3.2 |

## NPU Runtime

| Component | Verified value |
|---|---|
| XRT | 2.21.0 ([SDK zip 2.21.75](https://github.com/Xilinx/XRT/releases/tag/2.21.75); [IRON Windows guide](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/)) |
| XRT SDK root | `C:\Xilinx\XRT` |
| NPU driver | 32.0.20102.3930 |
| NPU firmware | 1.5.5.391 |
| XRT device | `NPU Phoenix` |

## Compiler and Python Environment

| Component | Verified value |
|---|---|
| MLIR-AIE | v1.4.1 + 13 commits (pin `3ca0193`) |
| LLVM-AIE / Peano | `21.0.0.2026080301+c9c5ecb7` |
| MLIR-AIE repository | `https://github.com/Xilinx/mlir-aie.git` |
| MLIR-AIE tested commit | `3ca0193cea9e2c39ec670a65f93e1dd43c969f22` |
| Upstream release base | [v1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1) |
| Extra upstream fix included | [PR #3545](https://github.com/Xilinx/mlir-aie/pull/3545) — run_chain executable lifetime |
| Python environment | `third_party\mlir-aie\ironenv` |

## Post-Quantum Cryptography (PQC) reference packages

Auto-installed inside the `ironenv` by `install.py` for the M32 [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM and M33 [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA composer gates. Versions are pinned to the values validated on 2026-08-16 against the [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server) response vectors:

| Component | Verified value | Upstream |
|---|---|---|
| `kyber-py` | `1.0.1` | [github.com/GiacomoPope/kyber-py](https://github.com/GiacomoPope/kyber-py) |
| `dilithium-py` | `1.4.0` | [github.com/GiacomoPope/dilithium-py](https://github.com/GiacomoPope/dilithium-py) |
| `pytest` | unpinned | [docs.pytest.org](https://docs.pytest.org/) |

All SHAKE128 / SHAKE256 / SHA3-256 / SHA3-512 primitives come from the CPython [`hashlib`](https://docs.python.org/3/library/hashlib.html) standard library, so no separate SHAKE / Keccak wheel is required. The equivalent manual install command is documented in [`docs/SETUP_WINDOWS.md`](../docs/SETUP_WINDOWS.md). NIST ACVP-Server KAT vectors for ML-KEM (keyGen / encapsulation / decapsulation) and ML-DSA (keyGen / signature-generation / signature-verification) are vendored inside the repository at `tests/m32_mlkem/vectors/` and `tests/m33_mldsa/vectors/`. Source: [`usnistgov/ACVP-Server`](https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files).

## Required Validation

Before running the silicon tests, verify:

```powershell
python -c "import aie; print(aie.__file__)"
python -c "import pyxrt; print(pyxrt.__file__)"
& "C:\Windows\System32\AMD\xrt-smi.exe" examine
```

The XRT output must show an `NPU Phoenix` device. The `aie` and `pyxrt` imports must succeed.
