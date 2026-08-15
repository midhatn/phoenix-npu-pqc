"""Bit-exact transliteration of tests/m25_psk_rx/psk_rx_kernel.cc line-for-line
into NumPy, cross-checked against the host reference in
tests/m25_psk_rx/test_psk_rx_m25.py on the seed-795 (BPSK) and seed-796
(QPSK) silicon-gate vectors.

Purpose: prove that (a) the .cc constants and per-symbol serial schedule
are correctly reproduced by the Python host reference, and (b) any silicon
vs host mismatch cannot be caused by a divergence in the two code paths.

Expected result: for both BPSK (order=2, seed=795) and QPSK (order=4,
seed=796), np.array_equal(kernel_out, reference_out) == True, i.e. 0
differing slots out of 1024.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "m25_psk_rx"))
from test_psk_rx_m25 import (  # noqa: E402
    _make_random_burst,
    _sgn_bit,
    _sincos_taylor,
    _wrap_pi,
    psk_rx_reference,
    N_SYM,
    N_IN,
    SPS,
    DATA_IN,
    DATA_OUT,
    TWO_PI,
    ALPHA_PHI,
    BETA_PHI,
    ALPHA_TAU,
    BETA_TAU,
)


# The .cc-shape wrap_pi and sincos_taylor helpers are re-imported directly
# from test_psk_rx_m25 to guarantee we do not accidentally introduce a
# divergent second copy in this checker.


def kernel_transliteration(in_bf16, order):
    """Walk psk_rx_kernel.cc line-for-line in NumPy scalar float32.

    Matches the psk_rx_body<ORDER> template body one statement at a time.
    """
    assert order in (2, 4)
    x_all = in_bf16.astype(np.float32)

    # State scalars, initialized as in the .cc body.
    phase = np.float32(0.0)
    freq = np.float32(0.0)
    mu = np.float32(0.5)
    freq_tau = np.float32(0.0)
    n_read = 0

    # 3-slot complex history.
    hist_I = np.zeros(3, dtype=np.float32)
    hist_Q = np.zeros(3, dtype=np.float32)

    # Prime: same 4 loads as the .cc before the for loop.
    hist_I[1] = x_all[0]
    hist_Q[1] = x_all[1]
    hist_I[2] = x_all[2]
    hist_Q[2] = x_all[3]

    Iy = np.zeros(N_SYM, dtype=np.float32)
    Qy = np.zeros(N_SYM, dtype=np.float32)

    for k in range(N_SYM):
        # (1) Fetch x_now.
        idx_now = 2 * (n_read + 2)
        if idx_now + 1 < 2 * N_IN:
            I_now = np.float32(x_all[idx_now])
            Q_now = np.float32(x_all[idx_now + 1])
        else:
            I_now = hist_I[2]
            Q_now = hist_Q[2]

        # Literal shifts (.cc order).
        hist_I[0] = hist_I[1]; hist_I[1] = hist_I[2]; hist_I[2] = I_now
        hist_Q[0] = hist_Q[1]; hist_Q[1] = hist_Q[2]; hist_Q[2] = Q_now

        # (2) Gardner TED.
        dI = np.float32(hist_I[2] - hist_I[0])
        dQ = np.float32(hist_Q[2] - hist_Q[0])
        e_tau = np.float32(dI * hist_I[1] + dQ * hist_Q[1])

        # (3) Timing PI.
        freq_tau = np.float32(freq_tau + np.float32(BETA_TAU * e_tau))
        mu = np.float32(mu + freq_tau + np.float32(ALPHA_TAU * e_tau))

        # (4) Wrap mu.
        while mu >= 1.0:
            mu = np.float32(mu - 1.0); n_read += 1
        while mu < 0.0:
            mu = np.float32(mu + 1.0); n_read -= 1
        n_read += 1

        # (5) Linear interp.
        ySymI = np.float32((np.float32(1.0) - mu) * hist_I[0] + mu * hist_I[1])
        ySymQ = np.float32((np.float32(1.0) - mu) * hist_Q[0] + mu * hist_Q[1])

        # (6) NCO derotate via on-tile Taylor sin/cos (mirror of sincos_taylor).
        s, c = _sincos_taylor(phase)
        zI = np.float32(ySymI * c + ySymQ * s)
        zQ = np.float32(ySymQ * c - ySymI * s)

        # (7) Costas error (branch on compile-time ORDER).
        if order == 4:
            sI = _sgn_bit(zI)
            sQ = _sgn_bit(zQ)
            e_phi = np.float32(zI * sQ - zQ * sI)
        else:
            e_phi = np.float32(zI * zQ)

        # (8) Carrier PI.
        freq = np.float32(freq + np.float32(BETA_PHI * e_phi))
        phase = np.float32(phase + freq + np.float32(ALPHA_PHI * e_phi))
        phase = _wrap_pi(phase)

        Iy[k] = zI
        Qy[k] = zQ

    out = np.zeros(DATA_OUT, dtype=np.float32)
    out[0::2] = Iy
    out[1::2] = Qy
    return out.astype(bfloat16)


def _run_one(order, seed, tag):
    np_in_bf16, theta0 = _make_random_burst(seed, order)

    kernel_out = kernel_transliteration(np_in_bf16, order=order)
    ref_out = psk_rx_reference(np_in_bf16, order=order)

    a = kernel_out.astype(np.float32)
    b = ref_out.astype(np.float32)
    diffs = int(np.count_nonzero(a != b))
    max_err = float(np.max(np.abs(a - b))) if diffs else 0.0
    print(
        f"[{tag}] seed={seed}  diffs={diffs}/{DATA_OUT}  max_err={max_err:.6e}  "
        f"theta0={theta0:+.4f} rad"
    )
    assert diffs == 0, (
        f"kernel transliteration diverges from host reference for {tag}: "
        f"{diffs} mismatched slots, max abs err {max_err}"
    )


def main():
    print("=== M25 kernel transliteration self-check ===")
    _run_one(order=2, seed=795, tag="BPSK order-2")
    _run_one(order=4, seed=796, tag="QPSK order-4")
    print("PASS: kernel .cc <-> host reference agree bit-for-bit on both PSK orders.")


if __name__ == "__main__":
    main()
