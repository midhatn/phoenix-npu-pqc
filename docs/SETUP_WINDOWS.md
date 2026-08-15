# Native Windows Setup

This guide prepares a clean Windows installation to run Phoenix SDR-DSP on a supported AMD Phoenix NPU.

## Scope

The project targets:

- Windows 11 Pro
- AMD Ryzen 9 7940HS / Phoenix NPU
- XDNA1 / AIE2
- Native Windows MLIR-AIE, LLVM-AIE / Peano, and XRT

The validated versions are recorded in [toolchain-versions.md](../requirements/toolchain-versions.md).

## Prerequisites

Install these before cloning the external toolchain:

1. Git for Windows.
2. Python 3.13.
3. CMake.
4. Visual Studio 2022 Build Tools with the Desktop Development with C++ workload.
5. AMD NPU driver compatible with Phoenix/XDNA1.
6. XRT for Windows, installed under `C:\\Xilinx\\XRT`.

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

MLIR-AIE is an external dependency and is intentionally not included in this repository. The regression suite requires mlir-aie **v1.4.1** or later (v1.4.1 released 2026-08-11 introduces the current `iron.Runtime(seq_fn, fn_args=...)` API used by every iron-based test in `tests/`). The v0.4.0 release of Phoenix SDR-DSP is verified against upstream commit `3ca0193cea9e2c39ec670a65f93e1dd43c969f22` (2026-08-14), which is v1.4.1 plus 13 commits including PR #3545 (`run_chain` executable-lifetime fix).

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

The automated suite runs 16 entries covering M3, M5 through M15, M15b, M17, and M17p. It requires the physical NPU and compares NPU results against CPU references. Expected outcome at release v0.4.0: 15 of 16 tests pass, with M15b the sole failure pending iron.Runtime port.

## Troubleshooting

| Symptom | Check |
|---|---|
| `No module named aie` | Activate `third_party\\mlir-aie\\ironenv` and verify `python --version`. |
| `No module named pyxrt` | Confirm XRT is installed and its Python bindings match the active Python version. |
| No `NPU Phoenix` in `xrt-smi examine` | Install or update the AMD NPU driver; confirm the hardware is Phoenix/XDNA1. |
| Peano compiler is not found | Re-run `python utils\\iron_setup.py` inside the MLIR-AIE checkout. |
| Regression imports fail | Confirm the MLIR-AIE checkout is at the pinned commit and submodules are initialized. |
| `Runtime.__init__() missing 1 required positional argument: 'seq_fn'` | mlir-aie checkout is older than v1.4.1. Check out v1.4.1 or later (pinned: `3ca0193`) and re-run `python utils\\iron_setup.py`. |
