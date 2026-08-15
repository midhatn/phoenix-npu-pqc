# M17 v3-b: NPU Dispatch Milestone — Numerics WIP

**Status:** Checkpoint commit. Pipeline executes end-to-end on Phoenix NPU silicon; numeric output is structured but incorrect.

**Date:** 2026-08-15
**Branch:** `feat/m17-radix2-fft-npu`
**Author:** midhatn

## What Works (v3-b Milestone)

For the first time in this project, a custom FFT kernel dispatches to and returns from the Phoenix (aie2p) NPU:

- **Peano compiles the kernel** to a valid aie2p ELF (8684 bytes standalone)
- **aiecc.py** builds the xclbin without errors
- **ld.lld** links the ELF (after `PROFILING=0` patch removed `get_cycles()` dependency)
- **XRT** loads the artifact to the Phoenix NPU
- **The kernel executes to completion** — `run.wait()` returns `ERT_CMD_STATE_COMPLETED`
- **ObjectFifo DMA marshalling works** — input (128 fp32) and twiddle (512 bf16) buffers reach the core; output (128 fp32) buffer returns to host

This validates every layer of the iron.jit + aie_api + Peano toolchain on our hardware.

## What Doesn't Work (v3-c TODO)

The kernel produces **structured but numerically wrong** output for the 3-tone test signal
(amplitudes 1.0, 0.7, 0.5 at bins 4, 12, 20):

- **Expected peaks:** [4, 12, 20]
- **Actual peaks:**   [1, 33, 49]
- **8 NaN values** appear at fixed positions in the output
- **Non-peak bins** contain nonzero structured values (not memory garbage) — e.g., bin 0 = 8.8, bin 8 = 18.8, bin 24 = 17.2

The output is deterministic across runs and identical whether or not
`-DAIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16` is set.

## Hypotheses Investigated (all disproven or inconclusive)

### 1. Ping-pong buffer clobbers input (disproven)

The kernel uses `float *src = (stage % 2 == 0) ? x : y` (line 176) which means the input
buffer `x` is written to during odd stages. Theory: iron.jit's ObjectFifo makes `x`
read-only, so intermediate writes are dropped, corrupting the FFT.

**Diagnostic:** printed input readback from device after kernel execution — bytes are
identical to what was uploaded. Either iron.jit copied input to a writable local buffer
(hiding the writes from the host) or the writes went through fine. In either case, this
is not the bug.

### 2. Missing AMD emulation flag (disproven)

AMD's makefile sets `-DAIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16`, we don't. Theory:
`aie::mmul<4,8,8,bfloat16,bfloat16,accfloat>` might silently misbehave on aie2p without
the flag.

**Diagnostic:** added `#define AIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16 1` to the wrapper
above the kernel `#include`. Output is bit-identical to before the flag. Either the flag
is ineffective in our aie_api version or it does not touch the code paths we hit.

### 3. Twiddle byte-layout mismatch (disproven)

Theory: our Python twiddle generator packs `[real, imag]` bf16 pairs, but the kernel
expects the Ozaki-style 4-slice split `[r0, i0, r1, i1, r2, i2, r3, i3]`.

**Verified against source:** our `twiddles_r4_stockham.py` already uses the 4-slice
Ozaki split (function `split_to_bf16`, packing loop at lines 100-121) and matches AMD's
driver `test.cpp` lines 205-256 exactly. Self-test reconstructs twiddles to max_err
~2.98e-8, well below fp32 machine epsilon. Layout is correct.

## Suspected Root Causes (untested)

Ordered by rough likelihood:

1. **iron.jit ObjectFifo semantics mismatch with AMD raw XRT `bo_tmp1` scratch buffer.**
   AMD driver passes 5 buffers (`bo_input, bo_twiddle, bo_out, bo_tmp1, bo_trace`); the
   `bo_tmp1` is a large scratch region separate from input/output. Our iron.jit graph
   wires only 3 ObjectFifos. If the kernel expects `bo_tmp1` to exist at a specific
   address (via linker section or ADF placement), the absent buffer could cause corrupt
   reads/writes into unrelated memory.

2. **aie2p `aie::mmul<4,8,8,bfloat16,bfloat16,accfloat>` does not do what the AMD kernel
   assumes.** AMD validated the kernel at N=256; N=64 hits fewer general-stage iterations,
   so a boundary condition (e.g., stage 0 separate code path with `Q_TILE=4` vs `m=16`)
   could interact differently with the mmul emulation.

3. **iron.jit default Peano flags for aie2p enable optimizations that break the mmul.**
   No easy way to inspect the actual flags used; would need to enable verbose logging on
   iron.jit and compare against `PEANOWRAP2P_FLAGS` from AMD `makefile-common`.

## v3-c Investigation Plan

When we return to this:

1. **Compare against AMD known-good output.** Build the reference (`FFT_R4_AIE`)
   locally at N=64 with a fixed input pattern; save `fft_results_N64_amd.csv`; run our
   kernel with the identical input and compare bit-for-bit. This tells us whether the
   bug is in *our* graph (twiddle upload, ObjectFifo wiring, DMA sync) vs *the kernel
   itself at N=64* vs *the aie2p mmul semantics*.

2. **Instrument stage 0.** Add explicit writes of intermediate values to the output
   buffer after stage 0 completes; verify `butterfly_out[0..3]` matches the analytic
   radix-4 butterfly of the first four input samples. This isolates stage-0 vs
   general-stage bugs.

3. **Add a `bo_tmp1` equivalent scratch ObjectFifo.** If hypothesis (1) is right, giving
   the kernel a dedicated scratch buffer of `2*N` floats might resolve the corruption.
   Requires modifying the kernel signature to accept a fourth pointer and updating the
   iron.jit graph to wire it up.

4. **Try `-DAIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16` at the *iron.jit compile flag* level
   rather than as a wrapper `#define`.** May reveal that iron.jit strips or reorders defs
   applied via `#define` in `.cc` sources.

5. **Test N=256 (AMD validated size).** If N=256 produces correct output, the bug is
   size-specific and lives in the LOG4N=3 code path. If N=256 also fails, the bug is
   toolchain- or graph-related and independent of N.

## Files In v3-b Checkpoint

- `kernels/fft_stockham_f32.cc` — modified from FFT_R4_AIE upstream:
  - `PROFILING` guard changed to `0` (removes `get_cycles()` symbol -> fixes ld.lld link)
  - Benchmark 10000-iteration loop in `fft_stockham_f32()` collapsed to single call
  - Three `in_vecs = aie::load_v<32>(...)` sites patched to
    `in_vecs.from_vector(aie::load_v<32>(...))` (fixes aie_api operator= rejection)
- `tests/m17_radix2_fft/fft64_r4_wrapper.cc` — thin wrapper that `#define FFT_SIZE 64`
  before including the shared kernel
- `tests/m17_radix2_fft/twiddles_r4_stockham.py` — Ozaki 4-slice bfloat16 twiddle packer,
  matches `FFT_R4_AIE/test.cpp` layout, self-test passes at max_err ~3e-8
- `tests/m17_radix2_fft/test_fft_m17_v3.py` — mlir-aie graph (3 ObjectFifos: input,
  twiddle, output) and host driver with numpy cross-check

## References

- Upstream kernel: diacccc/FFT_R4_AIE (Apache-2.0, AMD); commit vendored 2026-08-14
- iron.jit: mlir-aie 1.4.1, `python/aie/iron/*`
- Peano: LLVM-AIE fork, aie2p target