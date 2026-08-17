"""Phoenix SDR-DSP host-side Python entry points.

The package intentionally contains only lightweight import-time code.  Native
MLIR-AIE/IRON dependencies are loaded by the individual silicon runners when a
dispatch is requested, so static checks can inspect the runner contracts on a
host that has no NPU toolchain.
"""
