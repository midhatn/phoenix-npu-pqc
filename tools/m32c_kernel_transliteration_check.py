# M32c kernel transliteration check.
#
# Verifies BIT-EXACT equality between:
#   (a) the primary host reference `keccak_sponge` in
#       tests/m32_mlkem/test_keccak_shake_m32c.py (transliterated from the
#       AIE2 keccak_shake_kernel.cc)
#   (b) Python's stdlib hashlib (SHA-3/SHAKE gold reference from the
#       OpenSSL provider that ships with CPython, itself validated against
#       NIST CAVP - https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/secure-hashing)
#
# Also runs SampleNTT / SamplePolyCBD against a second independent Python
# implementation to guard against bugs in the primary reference.
#
# Runs on >= 2 seeds and on empty input to guard against seed-specific luck.
#
# References:
#   - docs/M32c_DESIGN.md sec 2 (Keccak-f[1600] and sponge)
#     and sec 3 (kernel architecture).
#   - tools/m27_kernel_transliteration_check.py -- prior-art pattern.

import hashlib
import sys
import types
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tests" / "m32_mlkem"))


# ------------------------------------------------------------------
# Subscriptable CompileTime stub (M27 lesson - lets the test module import
# without pulling in real aie.iron).

class _CompileTimeStub:
    """Subscriptable stub so `CompileTime[int]` and `CompileTime[str]`
    expressions at module scope do not raise TypeError."""

    def __class_getitem__(cls, item):
        return item

    def __getitem__(self, item):
        return item


def _stub_aie_and_import_test():
    aie = types.ModuleType("aie")
    aie_iron = types.ModuleType("aie.iron")
    aie_iron.jit = (lambda fn: fn)
    aie_iron.CompileTime = _CompileTimeStub
    for n in ("In", "Out", "ExternalFunction", "ObjectFifo",
              "Program", "Runtime", "Worker"):
        setattr(aie_iron, n, (lambda *a, **k: None))
    aie_iron.get_current_device = (lambda: "stub")
    aie.iron = aie_iron
    sys.modules["aie"] = aie
    sys.modules["aie.iron"] = aie_iron
    aie_utils = types.ModuleType("aie.utils")
    aie_utils_cfg = types.ModuleType("aie.utils.config")
    aie_utils_cfg.cxx_header_path = (lambda: "/tmp")
    aie_utils_host = types.ModuleType("aie.utils.hostruntime")
    aie_utils_xrt = types.ModuleType("aie.utils.hostruntime.xrtruntime")
    aie_utils_tensor = types.ModuleType("aie.utils.hostruntime.xrtruntime.tensor")
    aie_utils_tensor.XRTTensor = None
    for name, mod in [
        ("aie.utils", aie_utils),
        ("aie.utils.config", aie_utils_cfg),
        ("aie.utils.hostruntime", aie_utils_host),
        ("aie.utils.hostruntime.xrtruntime", aie_utils_xrt),
        ("aie.utils.hostruntime.xrtruntime.tensor", aie_utils_tensor),
    ]:
        sys.modules[name] = mod
    import test_keccak_shake_m32c as t
    return t


# ------------------------------------------------------------------
# Second independent SampleNTT / SamplePolyCBD reference.
#
# Uses hashlib directly instead of the transliterated Keccak, so the two
# implementations only share the FIPS 203 algorithm structure, not the
# permutation code path.

KYBER_N = 256
KYBER_Q = 3329


def sample_ntt_v2(seed_32, j, i):
    """Second-source SampleNTT built on hashlib.shake_128 (SHAKE128 XOF)."""
    xof = hashlib.shake_128()
    xof.update(bytes(seed_32) + bytes([j & 0xFF, i & 0xFF]))
    # 840 bytes = 5 SHAKE128 rate blocks; matches kernel XOF_MAX_OUT after
    # the M32e-driven bump to eliminate SampleNTT tail failure on unlucky
    # NIST ML-KEM-512 KATs (worst-case 516 bytes observed empirically).
    stream = xof.digest(840)
    coeffs = []
    pos = 0
    while len(coeffs) < KYBER_N and pos + 3 <= len(stream):
        b0 = stream[pos + 0]
        b1 = stream[pos + 1]
        b2 = stream[pos + 2]
        pos += 3
        d1 = b0 + 256 * (b1 & 0x0F)
        d2 = (b1 >> 4) + 16 * b2
        if d1 < KYBER_Q:
            coeffs.append(d1)
        if len(coeffs) < KYBER_N and d2 < KYBER_Q:
            coeffs.append(d2)
    while len(coeffs) < KYBER_N:
        coeffs.append(0)
    return np.array(coeffs, dtype=np.int16)


def sample_poly_cbd_v2(seed_32, b, eta):
    """Second-source SamplePolyCBD built on hashlib.shake_256 (PRF)."""
    assert eta in (2, 3)
    prf = hashlib.shake_256()
    prf.update(bytes(seed_32) + bytes([b & 0xFF]))
    stream = prf.digest(64 * eta)
    coeffs = np.zeros(KYBER_N, dtype=np.int16)
    for idx in range(KYBER_N):
        bit_start = 2 * eta * idx
        byte_idx = bit_start >> 3
        bit_off = bit_start & 7
        hi = stream[byte_idx + 1] if (byte_idx + 1) < len(stream) else 0
        lo = stream[byte_idx]
        win = ((hi << 8) | lo) >> bit_off
        mask = (1 << eta) - 1
        a_bits = win & mask
        b_bits = (win >> eta) & mask
        coeffs[idx] = int(a_bits).bit_count() - int(b_bits).bit_count()
    return coeffs


# ------------------------------------------------------------------
# Cross-check driver.

def main():
    t = _stub_aie_and_import_test()

    print("=== M32c kernel transliteration cross-check ===")
    print("Refs: primary=Keccak transliteration; secondary=hashlib.\n")

    seeds = [
        b"\x00" * 32,
        bytes(range(32)),
        bytes([0x42] * 32),
    ]
    n_pass = 0
    n_fail = 0

    # -------- SHA3-256 --------
    for m in [b"", b"abc", bytes(range(200))]:
        got = t.keccak_sponge(m, 32, t.RATE_SHA3_256, t.DSP_SHA3)
        exp = hashlib.sha3_256(m).digest()
        ok = got == exp
        n_pass += ok; n_fail += (not ok)
        print(f"  SHA3-256  len(m)={len(m):4d}: {'PASS' if ok else 'FAIL'}")

    # -------- SHA3-512 --------
    for m in [b"", b"abc", bytes(range(200))]:
        got = t.keccak_sponge(m, 64, t.RATE_SHA3_512, t.DSP_SHA3)
        exp = hashlib.sha3_512(m).digest()
        ok = got == exp
        n_pass += ok; n_fail += (not ok)
        print(f"  SHA3-512  len(m)={len(m):4d}: {'PASS' if ok else 'FAIL'}")

    # -------- SHAKE128 --------
    for m in [b"", b"post-quantum", bytes(range(64))]:
        for out_len in (16, 32, 168, 200):
            got = t.keccak_sponge(m, out_len, t.RATE_SHAKE128, t.DSP_SHAKE)
            exp = hashlib.shake_128(m).digest(out_len)
            ok = got == exp
            n_pass += ok; n_fail += (not ok)
            print(f"  SHAKE128  len(m)={len(m):3d} out={out_len:3d}: "
                  f"{'PASS' if ok else 'FAIL'}")

    # -------- SHAKE256 --------
    for m in [b"", b"post-quantum", bytes(range(64))]:
        for out_len in (16, 32, 168, 200):
            got = t.keccak_sponge(m, out_len, t.RATE_SHAKE256, t.DSP_SHAKE)
            exp = hashlib.shake_256(m).digest(out_len)
            ok = got == exp
            n_pass += ok; n_fail += (not ok)
            print(f"  SHAKE256  len(m)={len(m):3d} out={out_len:3d}: "
                  f"{'PASS' if ok else 'FAIL'}")

    # -------- SampleNTT --------
    for seed in seeds:
        for (j, i) in [(0, 0), (0, 1), (1, 0)]:
            got = t.sample_ntt(seed, j, i)
            exp = sample_ntt_v2(seed, j, i)
            ok = bool(np.array_equal(got, exp)) and int(got.min()) >= 0 \
                 and int(got.max()) < KYBER_Q
            n_pass += ok; n_fail += (not ok)
            print(f"  SampleNTT  seed[0]={seed[0]:#04x} (j,i)=({j},{i}): "
                  f"{'PASS' if ok else 'FAIL'}")

    # -------- SamplePolyCBD --------
    for seed in seeds:
        for eta in (2, 3):
            for b in [0, 1, 7]:
                got = t.sample_poly_cbd(seed, b, eta)
                exp = sample_poly_cbd_v2(seed, b, eta)
                ok = bool(np.array_equal(got, exp)) and \
                     int(got.min()) >= -eta and int(got.max()) <= eta
                n_pass += ok; n_fail += (not ok)
                print(f"  CBD        seed[0]={seed[0]:#04x} eta={eta} b={b}: "
                      f"{'PASS' if ok else 'FAIL'}")

    print(f"\nResult: {n_pass} PASS, {n_fail} FAIL")
    if n_fail == 0:
        print("Primary Keccak transliteration + FIPS 203 samplers agree with "
              "hashlib gold reference across all cases.")
        print("-> M32c host reference is trustworthy for silicon gate (a).")
        sys.exit(0)
    else:
        print("MISMATCH -- fix the primary reference before running silicon.")
        sys.exit(1)


if __name__ == "__main__":
    main()
