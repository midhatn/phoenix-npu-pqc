# Milestone 3: single-core SAXPY vectorised in bfloat16.

SAXPY is `y \leftarrow a\cdot x + y` ([Lawson, Hanson, Kincaid, and Krogh, ACM TOMS 1979](https://dl.acm.org/doi/10.1145/355841.355847); [Netlib `saxpy.f`](https://netlib.org/blas/saxpy.f)).
Inputs are [`bfloat16`](https://cloud.google.com/blog/products/ai-machine-learning/bfloat16-the-secret-to-high-performance-on-cloud-tpus) ([AMD XAPP1406](https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Floating-Point-Numerical-Formats)).
Dispatched through [`iron.Runtime`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py) on Phoenix NPU1 ([Linux `amdxdna`](https://docs.kernel.org/accel/amdxdna/amdnpu.html)).
