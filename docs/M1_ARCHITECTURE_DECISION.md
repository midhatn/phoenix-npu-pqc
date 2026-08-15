# Phoenix SDR-DSP Milestone 1 Architecture Decision

- Purpose: pin the compile and execution split for Phoenix/XDNA1 custom kernels
- Target operating system: Windows 11 Pro 25H2, build 26200.9168
- Target architecture: [AMD Ryzen 9 7940HS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) Phoenix / [XDNA1 / AIE2](https://docs.kernel.org/accel/amdxdna/amdnpu.html) / `npu1`
- Input types: Milestone 0 audits plus current official IRON/MLIR-AIE Windows documentation
- Output types: architecture decision record
- Scaling: not applicable
- Alignment assumptions: not applicable
- State requirements: none. This file does not change the machine.
- Error handling: if later milestones prove native `npu1` compilation or Windows XRT SDK host linkage cannot work, fall back to Priority 2 without changing the execution OS
- No unexplained constants: versions below come from the 2026-08-14 audits or the cited docs

## Decision

Use **Priority 1: native Windows** for both of these:

1. AIE2 / `npu1` device-code compilation
2. Phoenix NPU execution

Do **not** use WSL2 to talk to the NPU.

Do **not** install native Linux.

Do **not** dual-boot.

WSL2 remains installed as a compile-only fallback. It is used only if a later milestone proves that native Windows IRON cannot compile a Phoenix/`npu1` design.

## Why this is the current official path

The current IRON/MLIR-AIE native Windows guide is the recommended path for Windows 11. It states that programs can be built and run on a Ryzen AI NPU entirely inside Windows, without a POSIX environment.

Source (pinned docs, mlir-aie 1.4.1): https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/

That same page requires:

- Windows 11 with a supported Ryzen AI / XDNA NPU
- Visual Studio 2026 preferred, or Visual Studio 2022
- CPython 3.13 for the Windows XRT SDK `pyxrt` bindings
- CMake and Git
- Current Ryzen AI / XDNA NPU driver
- Windows XRT SDK, canonical path `C:\Xilinx\XRT`
- Minimum documented Windows NPU driver `32.0.20101.3760` with XRT `2.21.0`

The SAXPY example is the documented first end-to-end check: compile, run on the attached NPU, compare against NumPy, print `PASS!`.

The older WSL2 Windows guide still exists. It compiles device code in Ubuntu and builds host code with Visual Studio. The current native-Windows page now points Windows 11 users away from that path unless they specifically want POSIX.

Source (pinned docs, mlir-aie 1.4.1 WSL path): https://xilinx.github.io/mlir-aie/1.4.1/buildHostWin/

## Evidence from this machine

From `C:\phoenix-sdr-dsp\audit\windows_audit.txt` on 2026-08-14:

- Host: ASUS TUF Gaming A15 FA507XI
- CPU: AMD Ryzen 9 7940HS, 8 cores / 16 threads
- Memory: 64 GB DDR5-5600 dual channel
- OS: Windows 11 Pro 25H2, build 26200.9168
- NPU PnP: `PCI\VEN_1022&DEV_1502`, status OK, driver AMD `32.0.20102.3930`
- `xrt-smi examine`: device name `NPU Phoenix`, XRT `2.21.0`, firmware `1.5.5.391`
- `xrt-smi` path: `C:\Windows\System32\AMD\xrt-smi.exe`
- Runtime DLL present: `C:\Windows\System32\xrt_coreutil.dll`
- Windows XRT SDK headers and import libs: missing (`C:\Xilinx\XRT` does not exist)
- Visual Studio: Community 2022 17.14.38 and Community 2026 18.9.0
- MSVC: `cl` 19.51.36256, Windows SDK 10.0.26100
- CMake 4.3.2, Ninja 1.11.1, Git 2.48.1
- Python: Miniconda 3.12.9; no Python 3.13 found
- `pyxrt` import from Python 3.12: missing
- MLIR-AIE / IRON / Peano: missing
- Lime Suite / SoapySDR / LimeSDR USB IDs: missing
- `C:\Program Files\RyzenAI\1.3.1` exists and is the ONNX/Ryzen AI stack, not IRON

From `C:\phoenix-sdr-dsp\audit\wsl2_audit.txt` on 2026-08-14:

- Ubuntu 24.04.1 LTS under WSL2 kernel 6.6.87.2
- `/mnt/c` works
- No `/dev/accel`, no `/dev/dri`, no `/dev/kfd`
- No `xrt-smi` on the WSL PATH
- No `cmake`, `ninja`, `gcc`, `g++`, `clang`, or `pip`
- No `mlir-aie` checkout

The NPU driver on this machine is newer than the documented Windows minimum. Native execution is already proven at the `xrt-smi` level. Native custom-kernel compilation is not installed yet.

## Chosen split

Keep these operations separate, as required by the project rules:

| Operation | Location | Status after Milestone 1 |
|---|---|---|
| Windows-native device-code compilation | Windows IRON / MLIR-AIE / Peano | Selected. Not installed yet. |
| WSL2 device-code compilation | Ubuntu 24.04 WSL2 | Fallback only. Not selected. |
| Windows-native host compilation | Visual Studio + Windows XRT SDK + CMake | Selected. Compilers exist. SDK missing. |
| Windows-native NPU execution | Windows XRT + Phoenix NPU | Selected. `xrt-smi` already sees `NPU Phoenix`. |
| WSL2 direct NPU execution | WSL2 | Rejected. No NPU device node. |

## Tool roles

- MLIR-AIE and IRON: describe tiles, ObjectFifos, DMA, and the `npu1` graph
- AIE2 C++ kernels compiled by Peano / LLVM-AIE: vector DSP and later NTT butterflies
- Windows XRT SDK: headers, import libraries, and CPython 3.13 `pyxrt`
- Native Windows C++ host: LimeSDR I/Q rings, buffer reuse, submit/wait
- Existing Ryzen AI 1.3.1 / ONNX stack: not the primary DSP path
- AIE2P / `npu2` overlays already present under `C:\Windows\System32\AMD`: do not load on Phoenix

## Python policy

Create a dedicated CPython 3.13 interpreter for IRON and `pyxrt`.

Do not reuse the current Miniconda `base` 3.12.9 environment for IRON.

Do not rebuild XRT from source just to get 3.12 bindings unless native 3.13 setup fails later.

## LimeSDR impact

This decision does not install or select Lime Suite versus SoapySDR.

LimeSDR streaming remains a later Windows-native host problem. Missing Lime software does not change the NPU compile/execute split.

## Outcome (as of v0.4.0)

Priority 1 (native Windows for both device compilation and host execution) is validated: **16/16** milestones pass on Phoenix NPU1 silicon under this configuration (M15b iron.Runtime port landed 2026-08-15). The Priority 2 WSL2 fallback is not needed and has not been exercised. This decision is closed.

## Out of scope for this file

This file does not install Python 3.13, the Windows XRT SDK, MLIR-AIE, Peano, Lime Suite, or any driver.

Those actions belong to later gated milestones.
