# Phoenix SDR-DSP Milestone 2 Toolchain Verification Report

- Generated: 2026-08-14
- Host: ASUS TUF Gaming A15 FA507XI (AMD Ryzen 9 7940HS / Phoenix / XDNA1 / AIE2 / `npu1`)
- OS: Windows 11 Pro 25H2 (Build 26200.9168)

## Pinned Components Status

| Component | Pinned Version / Path | Verification Status |
|---|---|---|
| Python | CPython 3.13.15 (`C:\Users\midhat\AppData\Local\Programs\Python\Python313\python.exe`) | Installed & Verified |
| Windows XRT SDK | Tag 2.21.75 at `C:\Xilinx\XRT` | Installed & Verified |
| `pyxrt` Bindings | `C:\Xilinx\XRT\python\pyxrt.pyd` | Successfully loaded, created `pyxrt.device(0)` handle |
| LLVM Tools Helper | `C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\Llvm\x64\bin\llvm-objcopy.exe` | Verified & Used |
| `mlir_aie` | 1.3.4 (wheel via official rolling channel) | Installed in `ironenv` |
| `llvm-aie` (Peano) | 21.0.0.2026080301+c9c5ecb7 | Installed & Prepared in `ironenv` |
| Virtual Env | `C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv` | Ready |
| Activation Scripts | `iron_env.ps1`, `iron_env.cmd` | Present |

## Verification Check

Running `. .\iron_env.ps1` inside PowerShell sets up the runtime environment with:
- Target: AMD Phoenix NPU (XDNA1 / AIE2 / `npu1`)
- Compilers: `aie-opt`, `aie-translate`, `aiecc.py`, `clang++` (Peano)
- Runtime: Windows XRT SDK + `pyxrt`
