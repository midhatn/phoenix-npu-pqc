"""Bit-exact transliteration of tests/m24_correlator/correlator_kernel.cc
line-for-line into NumPy, cross-checked against the host reference in
tests/m24_correlator/test_correlator_m24.py on the seed-794 silicon-gate
vector.

Purpose: prove that (a) the .cc constants and loop schedule are correctly
reproduced by the Python host reference, and (b) any silicon vs host
mismatch cannot be caused by a divergence in the two code paths.

Expected result: np.array_equal(kernel_out, reference_out) == True,
i.e. 0 differing slots out of 4096.
"""
import sys
from pathlib import Path

# Stub aie modules if running in a sandbox without IRON.
try:
    from aie import iron  # noqa: F401
except ImportError:
    class _StubModule:
        def __getattr__(self, name):
            return _StubModule()

        def __call__(self, *a, **k):
            return _StubModule()

    for s in [
        "aie",
        "aie.iron",
        "aie.utils",
        "aie.utils.config",
        "aie.utils.hostruntime",
        "aie.utils.hostruntime.xrtruntime",
        "aie.utils.hostruntime.xrtruntime.tensor",
        "aie.utils.verify",
    ]:
        sys.modules[s] = _StubModule()

import numpy as np
from ml_dtypes import bfloat16

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "m24_correlator"))
from test_correlator_m24 import (
    L,
    _pack_iq,
    correlator_reference,
)


def kernel_transliteration(in_bf16):
    """Walk correlator_kernel.cc line-for-line in NumPy scalar float32."""
    x = in_bf16.astype(np.float32)
    Ix = x[0::2]
    Qx = x[1::2]
    N = len(Ix)

    # Reversed Barker-13 (exactly as in the .cc):
    #   s0..s12 = +1,-1,+1,-1,+1,+1,-1,-1,+1,+1,+1,+1,+1
    s = np.array(
        [+1.0, -1.0, +1.0, -1.0, +1.0, +1.0, -1.0,
         -1.0, +1.0, +1.0, +1.0, +1.0, +1.0],
        dtype=np.float32,
    )
    assert s.shape[0] == L

    hist_i = np.zeros(L, dtype=np.float32)
    hist_q = np.zeros(L, dtype=np.float32)
    out = np.zeros(2 * N, dtype=np.float32)

    for i in range(N):
        ii = np.float32(Ix[i])
        qq = np.float32(Qx[i])

        # Shift-and-ingest (mirrors kernel lines 96-107)
        hist_i[:L - 1] = hist_i[1:L]
        hist_i[L - 1] = ii
        hist_q[:L - 1] = hist_q[1:L]
        hist_q[L - 1] = qq

        # Dot products (mirrors kernel lines 116-141)
        # Iacc = hist_i[12]*s0 + hist_i[11]*s1 + ... + hist_i[0]*s12
        Iacc = np.float32(0.0)
        Qacc = np.float32(0.0)
        for k in range(L):
            Iacc = Iacc + np.float32(hist_i[L - 1 - k] * s[k])
            Qacc = Qacc + np.float32(hist_q[L - 1 - k] * s[k])

        out[2 * i] = Iacc
        out[2 * i + 1] = Qacc

    return out.astype(bfloat16)


def main():
    np.random.seed(794)
    Ix = np.random.uniform(-1.0, 1.0, 2048).astype(np.float32)
    Qx = np.random.uniform(-1.0, 1.0, 2048).astype(np.float32)
    x = _pack_iq(Ix, Qx)

    ref = correlator_reference(x)
    kern = kernel_transliteration(x)

    diff = ref.astype(np.float32) - kern.astype(np.float32)
    n_diff = int(np.count_nonzero(diff))
    max_diff = float(np.max(np.abs(diff)))
    print(f"Slots differing (kernel vs host reference): {n_diff} / {len(ref)}")
    print(f"Max absolute diff: {max_diff:.6e}")
    print(f"np.array_equal: {bool(np.array_equal(ref, kern))}")
    assert n_diff == 0, "M24 kernel and host reference diverged"
    print("PASS: M24 kernel is bit-exact to host reference on seed-794 vector.")


if __name__ == "__main__":
    main()
