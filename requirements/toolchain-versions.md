# Verified Native Windows Toolchain

This project was validated on a native Windows environment targeting the AMD Phoenix NPU.

## Host Platform

| Component | Verified value |
|---|---|
| Operating system | Windows 11 Pro, build 26200.9168 |
| System | ASUS TUF Gaming A15 FA507XI |
| Processor | AMD Ryzen 9 7940HS with Radeon 780M Graphics |
| NPU | AMD Phoenix NPU (XDNA1 / AIE2) |
| Git | 2.48.1.windows.1 |
| Python | 3.13.15 |
| CMake | 4.3.2 |

## NPU Runtime

| Component | Verified value |
|---|---|
| XRT | 2.21.0 |
| XRT SDK root | `C:\Xilinx\XRT` |
| NPU driver | 32.0.20102.3930 |
| NPU firmware | 1.5.5.391 |
| XRT device | `NPU Phoenix` |

## Compiler and Python Environment

| Component | Verified value |
|---|---|
| MLIR-AIE | 1.3.4 |
| LLVM-AIE / Peano | `21.0.0.2026080301+c9c5ecb7` |
| MLIR-AIE repository | `https://github.com/Xilinx/mlir-aie.git` |
| MLIR-AIE tested commit | `3ca0193cea9e2c39ec670a65f93e1dd43c969f22` |
| Python environment | `third_party\mlir-aie\ironenv` |

## Required Validation

Before running the silicon tests, verify:

```powershell
python -c "import aie; print(aie.__file__)"
python -c "import pyxrt; print(pyxrt.__file__)"
& "C:\Windows\System32\AMD\xrt-smi.exe" examine
```

The XRT output must show an `NPU Phoenix` device. The `aie` and `pyxrt` imports must succeed.
