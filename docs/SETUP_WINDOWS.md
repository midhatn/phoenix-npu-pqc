# Native Windows Setup

This guide prepares a clean Windows installation to run Phoenix SDR-DSP on a supported AMD Phoenix NPU.

## Scope

The project targets:

- Windows 11 Pro
- [AMD Ryzen 9 7940HS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) / Phoenix NPU
- [XDNA1 / AIE2](https://docs.kernel.org/accel/amdxdna/amdnpu.html)
- Native Windows [MLIR-AIE](https://github.com/Xilinx/mlir-aie), [LLVM-AIE / Peano](https://github.com/Xilinx/llvm-aie), and [XRT](https://github.com/Xilinx/XRT) ([official IRON Windows guide, v1.4.1](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/))

The validated versions are recorded in [toolchain-versions.md](../requirements/toolchain-versions.md).

## Prerequisites

Install these before cloning the external toolchain:

1. Git for Windows.
2. Python 3.13 ([IRON requires CPython 3.13 for Windows `pyxrt`](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/)).
3. CMake.
4. Visual Studio 2022 Build Tools with the Desktop Development with C++ workload (the [IRON guide](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/) also lists the C++ Clang Compiler for Windows component).
5. AMD NPU driver compatible with Phoenix/XDNA1 (guide minimum `32.0.20101.3760`).
6. XRT for Windows, installed under `C:\\Xilinx\\XRT` from [XRT 2.21.75](https://github.com/Xilinx/XRT/releases/tag/2.21.75) (`xrt_windows_sdk.zip`).

Verify the NPU is visible:

```powershell
& "C:\\Windows\\System32\\AMD\\xrt-smi.exe" examine
```

The output must list `NPU Phoenix`.

## Clone the Project

```powershell
Set-Location C:\\
git clone https://github.com/midhatn/phoenix-sdr-dsp.git
Set-Location C:\\phoenix-sdr-dsp
```

## Clone MLIR-AIE

MLIR-AIE is an external dependency and is intentionally not included in this repository. The regression suite requires mlir-aie **[v1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1)** or later (v1.4.1 released 2026-08-11 introduces the current [`iron.Runtime(seq_fn, fn_args=...)`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py) API used by every iron-based test in `tests/`). The v0.4.0 release of Phoenix SDR-DSP is verified against upstream commit [`3ca0193cea9e2c39ec670a65f93e1dd43c969f22`](https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22) (2026-08-14), which is v1.4.1 plus 13 commits including [PR #3545](https://github.com/Xilinx/mlir-aie/pull/3545) (`run_chain` executable-lifetime fix).

```powershell
New-Item -ItemType Directory -Force -Path third_party | Out-Null
Set-Location C:\\phoenix-sdr-dsp\\third_party

git clone --recurse-submodules https://github.com/Xilinx/mlir-aie.git
Set-Location C:\\phoenix-sdr-dsp\\third_party\\mlir-aie

git checkout 3ca0193cea9e2c39ec670a65f93e1dd43c969f22
git submodule update --init --recursive
```

Do not check out an mlir-aie release earlier than v1.4.1: the previous context-manager `Runtime()` API used before v1.4.1 is incompatible with the current tests. Details in `docs/M2_TOOLCHAIN_PIN.md`.

## Create the IRON Environment

From the MLIR-AIE checkout:

```powershell
Set-Location C:\\phoenix-sdr-dsp\\third_party\\mlir-aie
python utils\\iron_setup.py
```

Activate the resulting environment:

```powershell
& C:\\phoenix-sdr-dsp\\third_party\\mlir-aie\\ironenv\\Scripts\\Activate.ps1
```

## Post-Quantum Cryptography reference dependencies (M32 / M33)

The M32 FIPS 203 ML-KEM and M33 FIPS 204 ML-DSA tests use official NIST ACVP-Server known-answer vectors and two published reference implementations from the [pq-crystals](https://pq-crystals.org/) family. M32b/c/d and M33a/b dispatch directly to the NPU. M32e combines 60 host KATs with a nine-vector ML-KEM-512 silicon smoke gate, while M33d/e are host/NPU composers using the native M33a/M33b primitive runners. Since v1.0.0, `install.py` auto-installs the pinned PQC reference packages into the `ironenv` it creates. The equivalent manual step, useful if you bootstrapped `ironenv` another way or want to re-pin versions, is:

```powershell
& C:\\phoenix-sdr-dsp\\third_party\\mlir-aie\\ironenv\\Scripts\\python.exe -m pip install kyber-py==1.0.1 dilithium-py==1.4.0 pytest
```

Versions are pinned to the values validated on 2026-08-16 against the [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server) response vectors for ML-KEM ([FIPS 203, 2024-08-13](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)) and ML-DSA ([FIPS 204, 2024-08-13](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf)):

- [`kyber-py`](https://github.com/GiacomoPope/kyber-py) 1.0.1 — reference ML-KEM implementation used by the M32e composer gate as an oracle for [FIPS 203 Algorithms 19-21](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf).
- [`dilithium-py`](https://github.com/GiacomoPope/dilithium-py) 1.4.0 — reference ML-DSA implementation used by the M33d KeyGen and M33e Sign / Verify composer gates as an oracle for [FIPS 204 Algorithms 6-8](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf).
- [`pytest`](https://docs.pytest.org/) — test-parametrisation framework required by `tests/m32_mlkem/test_mlkem_m32e.py`, which imports it at module scope.

All SHAKE128, SHAKE256, SHA3-256, and SHA3-512 primitives used by the M32c reference and the FIPS 204 Keccak reuse come from CPython's [`hashlib`](https://docs.python.org/3/library/hashlib.html) standard library ([`shake_128`](https://docs.python.org/3/library/hashlib.html#hashlib.shake_128) and [`shake_256`](https://docs.python.org/3/library/hashlib.html#hashlib.shake_256) shipped in Python 3.6). No separate SHAKE / Keccak wheel is required.

The NIST ACVP-Server key-generation / encapsulation / decapsulation vectors for ML-KEM and the key-generation / signature-generation / signature-verification vectors for ML-DSA are vendored under `tests/m32_mlkem/vectors/` and `tests/m33_mldsa/vectors/` respectively, so the tests run offline once the packages above are installed. Vector provenance is documented in [`docs/PQC_COMPLETE_V1.md`](PQC_COMPLETE_V1.md).

## Validate the Installation

Run these commands after activation:

```powershell
python -c "import aie; print('MLIR-AIE:', aie.__file__)"
python -c "import pyxrt; print('XRT Python:', pyxrt.__file__)"
& "C:\\Windows\\System32\\AMD\\xrt-smi.exe" examine
```

The first two commands must complete without errors. The XRT command must list `NPU Phoenix`.

## Run the Regression Suite

```powershell
Set-Location C:\\phoenix-sdr-dsp
python run_all_silicon_tests.py
```

The automated suite runs 34 invocations covering M3, M5 through M15, M15b, M17, M17p, M19 through M27, and the Post-Quantum Cryptography track M32b, M32c, M32d, M32e plus M33a, M33b, M33d, M33e-sign, and M33e-verify. Its current composition is 29 direct-hardware entries, four host/NPU composer entries, and one intentional CPU reference entry (M12). The strict runner requires all three M32e silicon groups without skips, explicit M33 silicon backend declarations, and anchored `TOTAL x/x PASS` lines. The recorded 2026-08-17 run completed 34/34 in 126.29 seconds. See [`M33_SILICON_VALIDATION_20260817.md`](M33_SILICON_VALIDATION_20260817.md).

## Optional: I/Q Throughput

Not part of the 34-invocation suite. After ironenv is active:

```powershell
python tests\npu_visible\test_iq_throughput.py
```

Expected on Phoenix NPU1: first-buffer max abs error 0.007812, then about 7.5 Msps / 30 MB/s I/Q in over a 5 second window. See the landing-page I/Q section and `tests/npu_visible/README.md`.

## Troubleshooting

| Symptom | Check |
|---|---|
| `No module named aie` | Activate `third_party\\mlir-aie\\ironenv` and verify `python --version`. |
| `No module named pyxrt` | Confirm XRT is installed and its Python bindings match the active Python version. |
| No `NPU Phoenix` in `xrt-smi examine` | Install or update the AMD NPU driver; confirm the hardware is Phoenix/XDNA1. |
| Peano compiler is not found | Re-run `python utils\\iron_setup.py` inside the MLIR-AIE checkout. |
| Regression imports fail | Confirm the MLIR-AIE checkout is at the pinned commit and submodules are initialized. |
| `Runtime.__init__() missing 1 required positional argument: 'seq_fn'` | mlir-aie checkout is older than v1.4.1. Check out v1.4.1 or later (pinned: `3ca0193`) and re-run `python utils\\iron_setup.py`. |
