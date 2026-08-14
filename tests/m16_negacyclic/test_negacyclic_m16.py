# Phoenix SDR-DSP Master Prompt: Milestone 16
# Description: Negacyclic Polynomial Multiplication (mod x^256 + 1, q = 3329) on Phoenix NPU1 (AIE2).
# Target architecture: AMD Ryzen 9 7940HS Phoenix NPU1 (XDNA1 / AIE2 / Win11 Pro)

import sys

import numpy as np
from aie.dialects.aie import (
    AIEDevice,
    ObjectFifoPort,
    core,
    device,
    object_fifo,
    tile,
)
from aie.dialects.aiex import (
    npu_dma_memcpy_nd,
    npu_sync,
    runtime_sequence,
)
from aie.ir import Context, IntegerType, Location
from aie.iron import Kernel
from aie.utils.hostruntime.xrtruntime.hostruntime import XRTTensor

q = 3329
N = 256

# Direct CPU Reference for Negacyclic Convolution mod (x^N + 1, q)
def negacyclic_polymul_ref(a, b, q=3329):
    N = len(a)
    c = [0] * N
    for i in range(N):
        for j in range(N):
            deg = i + j
            term = (int(a[i]) * int(b[j])) % q
            if deg < N:
                c[deg] = (c[deg] + term) % q
            else:
                c[deg - N] = (c[deg - N] - term + q) % q
    return c

# C Kernel for Negacyclic Polynomial Multiplication mod (x^256 + 1, 3329)
kernel_c_code = r"""
#include <stdint.h>

#define MOD 3329
#define N 256
#define BARRETT_MU 20165
#define BARRETT_SHIFT 26

static inline int32_t barrett_reduce(int32_t val) {
    int32_t q_val = (int32_t)(((int64_t)val * BARRETT_MU) >> BARRETT_SHIFT);
    int32_t res = val - q_val * MOD;
    if (res >= MOD) res -= MOD;
    if (res < 0) res += MOD;
    return res;
}

static inline int32_t mod_add(int32_t a, int32_t b) {
    int32_t res = a + b;
    if (res >= MOD) res -= MOD;
    return res;
}

static inline int32_t mod_sub(int32_t a, int32_t b) {
    int32_t res = a - b;
    if (res < 0) res += MOD;
    return res;
}

static inline int32_t mod_mul(int32_t a, int32_t b) {
    return barrett_reduce(a * b);
}

// Performs Negacyclic Polynomial Multiplication: C(x) = A(x) * B(x) mod (x^256 + 1, 3329)
void negacyclic_polymul_kernel(
    const int32_t* restrict in_a,
    const int32_t* restrict in_b,
    int32_t* restrict out_c
) {
    static int32_t c_acc[N];
    for (int i = 0; i < N; i++) {
        c_acc[i] = 0;
    }

    for (int i = 0; i < N; i++) {
        int32_t ai = in_a[i];
        if (ai == 0) continue;
        for (int j = 0; j < N; j++) {
            int32_t term = mod_mul(ai, in_b[j]);
            int deg = i + j;
            if (deg < N) {
                c_acc[deg] = mod_add(c_acc[deg], term);
            } else {
                c_acc[deg - N] = mod_sub(c_acc[deg - N], term);
            }
        }
    }

    for (int i = 0; i < N; i++) {
        out_c[i] = c_acc[i];
    }
}
"""

def main():
    print("======================================================================")
    print("      PHOENIX SDR-DSP MASTER PROMPT MILESTONE 16: NEGACYCLIC          ")
    print("            POLYNOMIAL MULTIPLICATION (mod x^256 + 1, q = 3329)        ")
    print("======================================================================")
    print(f"Modulus q: {q}, Ring Dimension N: {N}")
    print(f"Ring: Z_{q}[x] / (x^{N} + 1) (Kyber / ML-KEM arithmetic)")

    # Set deterministic random seed
    np.random.seed(42)

    # Test Case: Polynomial multiplication of random polynomials
    a_poly = np.random.randint(0, q, size=N, dtype=np.int32)
    b_poly = np.random.randint(0, q, size=N, dtype=np.int32)

    # Compute CPU gold reference
    print("\nComputing CPU Reference Negacyclic Polynomial Multiplication...")
    c_gold = negacyclic_polymul_ref(a_poly, b_poly, q=q)

    # Pack input buffer: [A (256), B (256)] -> Total: 512 elements (2048 bytes)
    # Output buffer: [C (256)] elements of int32 (1024 bytes)
    input_packed = np.zeros(512, dtype=np.int32)
    input_packed[0:256] = a_poly
    input_packed[256:512] = b_poly

    print("Synthesizing AIE2 Kernel and Dispatching to Phoenix NPU...")
    kernel = Kernel("negacyclic_polymul_kernel", kernel_c_code)

    with Context() as ctx, Location.unknown(ctx):
        i32_ty = IntegerType.get_signless(32, context=ctx)

        @device(AIEDevice.npu1_1col)
        def device_body():
            tile_0_0 = tile(0, 0)
            tile_0_2 = tile(0, 2)

            fifo_in = object_fifo("in_fifo", tile_0_0, tile_0_2, 2, i32_ty, [512])
            fifo_out = object_fifo("out_fifo", tile_0_2, tile_0_0, 2, i32_ty, [256])

            @core(tile_0_2)
            def core_body():
                elem_in = fifo_in.acquire(ObjectFifoPort.Consume, 1)
                elem_out = fifo_out.acquire(ObjectFifoPort.Produce, 1)

                kernel(
                    elem_in,
                    elem_in + 256,
                    elem_out
                )

                fifo_in.release(ObjectFifoPort.Consume, 1)
                fifo_out.release(ObjectFifoPort.Produce, 1)

            @runtime_sequence(i32_ty, i32_ty)
            def sequence(in_buf, out_buf):
                npu_dma_memcpy_nd(metadata="in_fifo", bd_id=0, mem=in_buf, sizes=[1, 1, 1, 512])
                npu_dma_memcpy_nd(metadata="out_fifo", bd_id=1, mem=out_buf, sizes=[1, 1, 1, 256])
                npu_sync(column=0, row=0, direction=0, channel=0)

        # Sequences & XRTTensors
        in_tensor = XRTTensor((512,), dtype=np.int32)
        out_tensor = XRTTensor((256,), dtype=np.int32)

        in_tensor[:] = input_packed
        out_tensor[:] = 0

        print("Compiling with Peano and executing on physical Phoenix NPU silicon...")
        device_body.run([in_tensor], [out_tensor])

        actual_c = np.array(out_tensor[:], dtype=np.int32)

    # Verification
    print("\n--- Silicon Execution Results ---")
    print(f"Input Poly A [0..4]:    {list(a_poly[:5])}")
    print(f"Input Poly B [0..4]:    {list(b_poly[:5])}")
    print(f"Ref Poly C [0..4]:      {c_gold[:5]}")
    print(f"Actual Poly C on NPU:   {list(actual_c[:5])}")

    matches = np.array_equal(actual_c, c_gold)
    diffs = np.sum(actual_c != c_gold)

    if matches:
        print("\nPASS!")
        print(f"SUCCESS: Phoenix NPU executed Negacyclic Polynomial Multiplication mod (x^{N} + 1, {q}) with 100% BIT-EXACT accuracy!")
        print("PASS!")
    else:
        print(f"\nFAIL: Mismatch in {diffs} / {N} polynomial coefficients!")
        sys.exit(1)

if __name__ == "__main__":
    main()
