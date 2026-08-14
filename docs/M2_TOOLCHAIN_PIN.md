# Phoenix SDR-DSP Milestone 2 Toolchain Pin

- Purpose: pin the native Windows IRON / MLIR-AIE / XRT development toolchain
- Target operating system: Windows 11 Pro 25H2, build 26200.9168
- Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2 / `npu1`
- Input types: Milestone 0 audits, Milestone 1 decision, official native Windows IRON guide
- Output types: this pin record plus a later version dump
- Scaling: not applicable
- Alignment assumptions: not applicable
- State requirements: later steps install Python 3.13, the Windows XRT SDK, and a local mlir-aie checkout. They do not change the NPU driver.
- Error handling: stop after the first failed step. Do not continue to SAXPY. Do not fall back to WSL2 unless native setup itself is proven impossible.
- No unexplained constants: paths and versions below are taken from this machine or the cited official guide

Official guide:

https://xilinx.github.io/mlir-aie/dev/buildHostWinNative/

## Decision carried forward

Native Windows compiles `npu1` device code and executes it on the Phoenix NPU.

WSL2 does not compile in this milestone and does not access the NPU.

## Already present, do not reinstall

| Component | This machine |
|---|---|
| Windows 11 Pro 25H2 | build 26200.9168 |
| Visual Studio 2022 Community | 17.14.38 |
| Visual Studio 2026 Community | 18.9.0 |
| MSVC | 14.51.36231 / `cl` 19.51.36256 |
| Windows SDK | 10.0.26100 |
| CMake | 4.3.2 |
| Ninja | 1.11.1 |
| Git | 2.48.1.windows.1 |
| NPU device | `PCI\VEN_1022&DEV_1502`, OK |
| NPU driver | AMD 32.0.20102.3930 |
| XRT runtime | 2.21.0 |
| `xrt-smi` | `C:\Windows\System32\AMD\xrt-smi.exe` |

The NPU driver is newer than the documented Windows minimum `32.0.20101.3760`. Do not update or reinstall it in this milestone.

## Missing, install in this milestone

| Component | Pinned location or identity |
|---|---|
| CPython 3.13 | `winget` package `Python.Python.3.13` |
| Windows XRT SDK | `C:\Xilinx\XRT` from `xrt_windows_sdk.zip` tag `2.21.75` |
| mlir-aie checkout | `C:\phoenix-sdr-dsp\third_party\mlir-aie` |
| IRON environment | checkout-local `ironenv` created by `utils\iron_setup.py` |

## Explicitly not used as the IRON interpreter

- Miniconda `base` Python 3.12.9
- `python3.exe` Microsoft Store alias
- Ryzen AI 1.3.1 ONNX environment `ryzen-ai-1.3.1`
- WSL2 Ubuntu 3.12.3

## Out of scope

- SAXPY or any NPU kernel run
- Lime Suite / SoapySDR / LimeSDR
- NTT code
- Native Linux
- Dual boot
- Building mlir-aie wheels from source
- Changing the NPU driver
