# NPU visibility tests

Not part of the 16-milestone regression. Do not add these paths to
`run_all_silicon_tests.py`.

## I/Q throughput (preferred)

4-column streamed complex mixer. One dispatch moves 64 frames x 1024 bf16
x 4 columns (~0.5 MiB I/Q). First dispatch is checked against NumPy
(`L_inf = 0.007812`, same bound as M6). A cold run prints
`First dispatch (includes compile)`; a repeat run prints
`First dispatch (cached)` (IRON xclbin under `%USERPROFILE%\.npu\cache`).
The next 5 seconds print MB/s and Msps.

```powershell
python tests\npu_visible\test_iq_throughput.py
```

### Measured (2026-08-15, Ryzen 9 7940HS, Phoenix NPU1)

AMD rates this NPU at [up to 10 TOPS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html)
([INT8 on Phoenix 7040](https://www.tomshardware.com/pc-components/cpus/the-refresh-that-wasnt-amd-announces-hawk-point-ryzen-8040-series-with-zen-4-rdna3-and-xdna-teases-strix-point)).

| Metric | 1-column 8 KB loop | 4-column stream |
| --- | ---: | ---: |
| IQ in | 3.85 MB/s | **29.84 MB/s** |
| IQ out | 3.85 MB/s | **29.84 MB/s** |
| IQ in+out | 7.70 MB/s | **59.68 MB/s** |
| Complex rate | 0.963 Msps | **7.459 Msps** |
| Task Manager NPU | ~53% | **~92%** |
| First-buffer `L_inf` | 0.007812 | 0.007812 |

A 1-column 8 KB M6 loop is host-bound. This version keeps all four AIE
columns ([Phoenix 4×5 XDNA1](https://docs.kernel.org/accel/amdxdna/amdnpu.html))
in an acquire/release stream (`Worker(while_true=True)`,
`dynamic_objfifo_lowering=True`; [IRON `Runtime` / `Worker` at the v1.4.1 pin](https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py))
so the NPU is not idle between 8 KB
Python round-trips. Rates are host-visible (IRON + shim DMA), not a
theoretical AIE peak. Kernel vectorization is deferred.

## Duty-cycle spin (optional)

Bounces the Task Manager NPU graph with random 0-100% targets for 5 seconds.

```powershell
python tests\npu_visible\test_npu_visible.py
```
