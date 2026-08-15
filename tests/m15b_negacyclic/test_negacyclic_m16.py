# Purpose: Master Prompt Milestone 15b: NPU negacyclic polynomial
#          multiplication on silicon (Kyber ring).
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Parameters: N = 256, prime modulus q = 3329, ring Z_q[x] / (x^256 + 1).
#
# Ported from aie.dialects + runtime_sequence (pre-v1.4.1) to the same
# iron.Runtime sequence-function shape as M15 (commit 1ec80c8).
# Kyber ring: https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf

from pathlib import Path

import numpy as np
from aie import iron
from aie.iron import (
    CompileTime,
    ExternalFunction,
    In,
    ObjectFifo,
    Out,
    Program,
    Runtime,
    Worker,
)
from aie.utils.config import cxx_header_path
from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor

MOD_Q = 3329
N_POLY = 256

# Schoolbook kernel. Same Barrett constants as the pre-port M15b test.
KERNEL_CC_CODE = r"""
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

extern "C" {

// C(x) = A(x) * B(x) mod (x^256 + 1, 3329)
void negacyclic_polymul_kernel(
    const uint32_t* restrict in_a,
    const uint32_t* restrict in_b,
    uint32_t* restrict out_c
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

}
"""


def negacyclic_polymul_ref(a, b, q=MOD_Q):
    n = len(a)
    c = np.zeros(n, dtype=np.int64)
    for i in range(n):
        for j in range(n):
            deg = i + j
            term = (int(a[i]) * int(b[j])) % q
            if deg < n:
                c[deg] = (c[deg] + term) % q
            else:
                c[deg - n] = (c[deg - n] - term + q) % q
    return c.astype(np.uint32)


@iron.jit
def negacyclic_pipeline(
    input_a: In,
    input_b: In,
    output_c: Out,
    *,
    N: CompileTime[int],
    kernel_source: CompileTime[str],
):
    tile_ty = np.ndarray[(N,), np.dtype[np.uint32]]

    of_a = ObjectFifo(tile_ty, name="in_a")
    of_b = ObjectFifo(tile_ty, name="in_b")
    of_c = ObjectFifo(tile_ty, name="out_c")

    mul_fn = ExternalFunction(
        "negacyclic_polymul_kernel",
        source_file=kernel_source,
        arg_types=[tile_ty, tile_ty, tile_ty],
        include_dirs=[cxx_header_path()],
    )

    def core_body(of_a, of_b, of_c, mul_fn):
        elem_a = of_a.acquire(1)
        elem_b = of_b.acquire(1)
        elem_c = of_c.acquire(1)
        mul_fn(elem_a, elem_b, elem_c)
        of_a.release(1)
        of_b.release(1)
        of_c.release(1)

    worker = Worker(
        core_body,
        fn_args=[of_a.cons(), of_b.cons(), of_c.prod(), mul_fn],
    )

    def sequence(a_in, b_in, c_out, a_prod, b_prod, c_cons):
        a_prod.fill(a_in)
        b_prod.fill(b_in)
        c_cons.drain(c_out, wait=True)

    rt = Runtime(
        sequence,
        [tile_ty, tile_ty, tile_ty, of_a.prod(), of_b.prod(), of_c.cons()],
    )
    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 15b: Negacyclic PolyMul (Kyber ring) ===")
    print(f"Parameters: N = {N_POLY}, modulus q = {MOD_Q}")
    print(f"Ring: Z_{MOD_Q}[x] / (x^{N_POLY} + 1)")

    kernel_src_path = Path(__file__).parent.resolve() / "negacyclic_kernel.cc"
    with open(kernel_src_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(KERNEL_CC_CODE)

    np.random.seed(42)
    poly_a = np.random.randint(0, MOD_Q, size=N_POLY, dtype=np.uint32)
    poly_b = np.random.randint(0, MOD_Q, size=N_POLY, dtype=np.uint32)
    ref_c = negacyclic_polymul_ref(poly_a, poly_b, q=MOD_Q)
    out_c = np.zeros(N_POLY, dtype=np.uint32)

    print("Computing CPU reference, then compiling with Peano...")
    t_a = XRTTensor(poly_a)
    t_b = XRTTensor(poly_b)
    t_c = XRTTensor(out_c)

    res = negacyclic_pipeline(
        t_a,
        t_b,
        t_c,
        N=N_POLY,
        kernel_source=str(kernel_src_path),
    )
    print(f"Kernel execution result: {res}")

    actual_c = t_c.numpy().astype(np.uint32)
    print("\n--- Silicon Execution Results ---")
    print(f"Input Poly A [0..4]:    {list(poly_a[:5])}")
    print(f"Input Poly B [0..4]:    {list(poly_b[:5])}")
    print(f"Ref Poly C [0..4]:      {list(ref_c[:5])}")
    print(f"Actual Poly C on NPU:   {list(actual_c[:5])}")

    matches = np.array_equal(actual_c, ref_c)
    diffs = int(np.sum(actual_c != ref_c))
    if matches:
        print("\nPASS!")
        print(
            f"SUCCESS: Phoenix NPU executed Negacyclic Polynomial Multiplication "
            f"mod (x^{N_POLY} + 1, {MOD_Q}) with 100% BIT-EXACT accuracy!"
        )
        print("PASS!")
        return
    print(f"\nFAIL: Mismatch in {diffs} / {N_POLY} polynomial coefficients!")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
