# Phoenix SDR-DSP

Native-Windows SDR, deterministic DSP, and finite-field NTT experiments for the AMD Ryzen 9 7940HS Phoenix NPU1 (XDNA1 / AIE2).

## Documentation

- [Milestones and Mathematics](docs/MILESTONES_AND_MATHEMATICS.md) — detailed M0–M15 implementation status, DSP equations, NTT parameters, verification rules, and regression coverage.

## Validated regression suite

The automated regression suite covers the silicon-validated milestones M3 and M5 through M15:

```powershell
python run_all_silicon_tests.py
```

The suite compares deterministic NPU operations with independent CPU references. Integer modular and NTT workloads are required to be bit-exact; `bfloat16` DSP workloads report their observed numerical error.

## Platform

- Windows 11 Pro
- AMD Ryzen 9 7940HS Phoenix NPU1
- XDNA1 / AIE2
- Native Windows MLIR-AIE, Peano, and XRT workflow
