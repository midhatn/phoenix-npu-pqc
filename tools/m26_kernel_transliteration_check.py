# Purpose: Verify the M26 QAM-16 receiver kernel (tests/m26_qam_rx/qam_rx_kernel.cc)
#          matches the Python reference (test_qam_rx_m26.qam16_rx_reference) at
#          bit-exact float32 precision. The kernel and the reference walk the
#          same closed-loop feedback path in the same order, so this check is
#          a strong sandbox pre-flight independent of the Phoenix NPU.
#
# Method: emulate the .cc line-by-line in Python using the SAME float32 rounding
#         (np.float32 wraps every intermediate) and the SAME dead-zone sgn_bit.
#         Compare the output hard-symbol buffer and LLR buffer to
#         qam16_rx_reference() slot-by-slot. Success criterion: 0 differing
#         slots on both output DMAs.
#
# Design: docs/M26_DESIGN.md sec 5.1
#
# References:
#   * NASA JPL TDA Progress Report 42-130 (closed-loop verification method):
#     https://ipnpr.jpl.nasa.gov/progress_report/42-130/130B.pdf
#   * Barry-Lee-Messerschmitt "Digital Communication" 3e sec 8.5:
#     https://link.springer.com/book/10.1007/978-1-4615-0227-2

import sys
from pathlib import Path

# Stub aie modules if running in a sandbox without IRON (matches
# tools/m25_kernel_transliteration_check.py pattern).
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

# Add tests/m26_qam_rx to sys.path so we can import the reference implementation.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "m26_qam_rx"))

from test_qam_rx_m26 import (
    ALPHA_PHI,
    ALPHA_TAU,
    BETA_PHI,
    BETA_TAU,
    BITS_PER_SYM,
    DATA_IN,
    DATA_OUT_LLR,
    DATA_OUT_SYM,
    INV_QAM16_SCALE,
    N_IN,
    N_SYM,
    QAM16_SCALE,
    SPS,
    _bits_to_qam16_symbols,
    _qam16_axis_slice,
    _sincos_taylor,
    _wrap_pi,
    qam16_rx_reference,
)


def kernel_emulation(in_bf16):
    """Emulates qam_rx_kernel.cc term-for-term. Uses the SAME helpers as the
    reference (Python mirrors the .cc), so a slot-by-slot diff of the output
    against qam16_rx_reference() must be all zeros.
    """
    x = in_bf16.astype(np.float32)

    phase = np.float32(0.0)
    freq = np.float32(0.0)
    mu = np.float32(0.5)
    freq_tau = np.float32(0.0)
    n_read = 0

    hist_I = np.zeros(3, dtype=np.float32)
    hist_Q = np.zeros(3, dtype=np.float32)

    hist_I[1] = x[0]
    hist_Q[1] = x[1]
    hist_I[2] = x[2]
    hist_Q[2] = x[3]

    out_sym = np.zeros(DATA_OUT_SYM, dtype=np.float32)
    out_llr = np.zeros(DATA_OUT_LLR, dtype=np.float32)

    for k in range(N_SYM):
        idx_now = 2 * (n_read + 2)
        if idx_now + 1 < 2 * N_IN:
            I_now = np.float32(x[idx_now])
            Q_now = np.float32(x[idx_now + 1])
        else:
            I_now = hist_I[2]
            Q_now = hist_Q[2]

        hist_I[0] = hist_I[1]; hist_I[1] = hist_I[2]; hist_I[2] = I_now
        hist_Q[0] = hist_Q[1]; hist_Q[1] = hist_Q[2]; hist_Q[2] = Q_now

        dI = np.float32(hist_I[2] - hist_I[0])
        dQ = np.float32(hist_Q[2] - hist_Q[0])
        e_tau = np.float32(dI * hist_I[1] + dQ * hist_Q[1])

        freq_tau = np.float32(freq_tau + BETA_TAU * e_tau)
        mu = np.float32(mu + freq_tau + ALPHA_TAU * e_tau)

        while mu >= 1.0:
            mu = np.float32(mu - 1.0); n_read += 1
        while mu < 0.0:
            mu = np.float32(mu + 1.0); n_read -= 1
        n_read += 1

        ySymI = np.float32((1.0 - mu) * hist_I[0] + mu * hist_I[1])
        ySymQ = np.float32((1.0 - mu) * hist_Q[0] + mu * hist_Q[1])

        s, c = _sincos_taylor(phase)
        zI = np.float32(ySymI * c + ySymQ * s)
        zQ = np.float32(ySymQ * c - ySymI * s)

        zI_lat = np.float32(zI * QAM16_SCALE)
        zQ_lat = np.float32(zQ * QAM16_SCALE)
        hat_aI = _qam16_axis_slice(zI_lat)
        hat_aQ = _qam16_axis_slice(zQ_lat)

        e_phi = np.float32(zI_lat * hat_aQ - zQ_lat * hat_aI)

        freq = np.float32(freq + BETA_PHI * e_phi)
        phase = np.float32(phase + freq + ALPHA_PHI * e_phi)
        phase = _wrap_pi(phase)

        out_sym[2 * k + 0] = np.float32(hat_aI * INV_QAM16_SCALE)
        out_sym[2 * k + 1] = np.float32(hat_aQ * INV_QAM16_SCALE)

        absI = np.float32(np.abs(zI_lat))
        absQ = np.float32(np.abs(zQ_lat))
        out_llr[4 * k + 0] = np.float32(zI_lat * 4.0)
        out_llr[4 * k + 1] = np.float32((2.0 - absI) * 4.0)
        out_llr[4 * k + 2] = np.float32(zQ_lat * 4.0)
        out_llr[4 * k + 3] = np.float32((2.0 - absQ) * 4.0)

    return out_sym.astype(bfloat16), out_llr.astype(bfloat16)


def _make_random_qam16_input(seed):
    """Reproduces the on-silicon input generator without importing XRTTensor."""
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=N_SYM * BITS_PER_SYM).astype(np.int32)
    syms = _bits_to_qam16_symbols(bits)
    up = np.repeat(syms, SPS)
    Ix = np.real(up).astype(np.float32)
    Qx = np.imag(up).astype(np.float32)

    theta0 = rng.uniform(-np.pi / 16, np.pi / 16)
    c, s = np.cos(theta0), np.sin(theta0)
    Ix2 = c * Ix - s * Qx
    Qx2 = s * Ix + c * Qx

    iq = np.zeros(DATA_IN, dtype=np.float32)
    iq[0::2] = Ix2
    iq[1::2] = Qx2
    return iq.astype(bfloat16), theta0


def _run_one_seed(seed):
    x, theta0 = _make_random_qam16_input(seed)
    ref_sym, ref_llr = qam16_rx_reference(x)
    emu_sym, emu_llr = kernel_emulation(x)

    diff_sym = np.abs(emu_sym.astype(np.float32) - ref_sym.astype(np.float32))
    diff_llr = np.abs(emu_llr.astype(np.float32) - ref_llr.astype(np.float32))
    n_bad_sym = int(np.sum(diff_sym > 0.0))
    n_bad_llr = int(np.sum(diff_llr > 0.0))
    print(
        f"[m26 transliteration] seed={seed}: theta0={theta0:+.5f} rad, "
        f"hardSym mismatches = {n_bad_sym}/{DATA_OUT_SYM}, "
        f"LLR mismatches = {n_bad_llr}/{DATA_OUT_LLR}"
    )
    assert n_bad_sym == 0, f"hardSym transliteration divergence, seed={seed}"
    assert n_bad_llr == 0, f"LLR transliteration divergence, seed={seed}"


def main():
    print("=== M26 QAM-16 receiver kernel transliteration check (sandbox) ===")
    _run_one_seed(seed=826)
    _run_one_seed(seed=827)
    print("PASS: kernel transliteration matches Python reference bit-for-bit "
          "on both seeds (hardSym and LLR).")


if __name__ == "__main__":
    main()
