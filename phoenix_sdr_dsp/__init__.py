"""Compatibility import package for Phoenix NPU PQC host-side entry points.

The historical ``phoenix_sdr_dsp`` module name is intentionally preserved for
existing PQC research imports. Native MLIR-AIE/IRON dependencies are loaded by
individual native runners only when a dispatch is requested, so host-safe
checks can inspect contracts without an NPU toolchain.
"""
