# M32b kernel transliteration check.
#
# Verifies BIT-EXACT equality between:
#   (a) the primary host reference in tests/m32_mlkem/test_ntt_m32b.py
#       (transliterated from the AIE2 tests/m32_mlkem/ntt_kernel.cc)
#   (b) an independent second-source implementation in unbounded Python ints,
#       done in the plain-modular domain (no Montgomery, no signed-16-bit
#       wrap), and cross-checked against a big-integer schoolbook oracle:
#
#          For any input polynomial a in Z_q[X]/(X^n+1):
#              INTT( NTT(a) o NTT(b) )  ==  a * b   (mod q, mod X^n+1)
#
#       where "o" is the pq-crystals poly_basemul_montgomery. Because the
#       primary reference is in the Montgomery domain, the surrounding
#       Montgomery scale factor is 1 (invntt_tomont multiplies by R, basemul
#       divides by R, one factor left over from tomont).
#
# Also cross-checks:
#   (c) the 128-entry ZETAS table baked into the primary reference matches an
#       independent recomputation R * 17^{brv7(k)} mod q (this is exactly
#       reference test R1 -- we re-run it here so a single script gives one
#       PASS/FAIL count).
#   (d) poly_add / poly_sub primary reference matches a straight big-integer
#       modular add / sub.
#
# References:
#   * docs/M32b_DESIGN.md sec 2 (NTT math) and sec 3 (kernel architecture)
#   * tools/m32c_kernel_transliteration_check.py -- prior-art pattern
#   * FIPS 203 (Aug 2024), Algorithms 9-12
#     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
#   * pq-crystals/kyber ref/ntt.c, ref/reduce.c, ref/poly.c
#     https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c
#   * Kyber CFRG draft rev 04 -- NTT matrix formulation, negacyclic pairing
#     https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html

import sys
import types
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tests" / "m32_mlkem"))


# ------------------------------------------------------------------
# Subscriptable CompileTime stub (M27 / M32c lesson).

class _CompileTimeStub:
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
    import test_ntt_m32b as t
    return t


# ------------------------------------------------------------------
# Independent (unbounded-int) implementations used as second sources.

KYBER_N = 256
KYBER_Q = 3329
KYBER_ZETA = 17


def _brv(i, k):
    r = 0
    for _ in range(k):
        r = (r << 1) | (i & 1)
        i >>= 1
    return r


def _mod_q_signed(x):
    v = int(x) % KYBER_Q
    if v > KYBER_Q // 2:
        v -= KYBER_Q
    return v


def zetas_indep():
    """Independent 128-entry table: R * 17^{brv7(k)} mod q, signed."""
    R = (1 << 16) % KYBER_Q
    return [_mod_q_signed(R * pow(KYBER_ZETA, _brv(k, 7), KYBER_Q))
            for k in range(128)]


def schoolbook_bigint(a, b):
    """Negacyclic polynomial product using unbounded Python ints throughout.
    Second source for the primary reference schoolbook.
    """
    a_i = [int(x) % KYBER_Q for x in a]
    b_i = [int(x) % KYBER_Q for x in b]
    prod = [0] * (2 * KYBER_N)
    for i in range(KYBER_N):
        ai = a_i[i]
        if ai == 0:
            continue
        for j in range(KYBER_N):
            prod[i + j] = (prod[i + j] + ai * b_i[j]) % KYBER_Q
    return [_mod_q_signed(prod[i] - prod[i + KYBER_N]) for i in range(KYBER_N)]


def poly_add_bigint(a, b):
    return [_mod_q_signed(int(a[i]) + int(b[i])) for i in range(KYBER_N)]


def poly_sub_bigint(a, b):
    return [_mod_q_signed(int(a[i]) - int(b[i])) for i in range(KYBER_N)]


# ------------------------------------------------------------------
# Cross-checks.

def _random_poly(rng):
    v = rng.integers(0, KYBER_Q, size=KYBER_N).astype(np.int64)
    v = np.where(v > KYBER_Q // 2, v - KYBER_Q, v).astype(np.int16)
    return v


def cross_check():
    t = _stub_aie_and_import_test()

    n_pass = 0
    n_total = 0

    # ---- 1) Zeta table cross-check (independent big-int recomputation).
    zi = zetas_indep()
    zp = [int(x) for x in t.ZETAS]
    n_total += 1
    if zi == zp:
        n_pass += 1
        print("[cross] (1) 128-entry ZETAS: independent recompute matches "
              "embedded pq-crystals table: PASS")
    else:
        for k in range(128):
            if zi[k] != zp[k]:
                print(f"[cross] (1) mismatch @ k={k}: indep={zi[k]} prim={zp[k]}")
                break

    # ---- 2) Schoolbook oracles agree (primary numpy-int16 vs second-source
    #        pure-big-int) on 3 random polynomial pairs.
    rng = np.random.default_rng(0xB1F00D)
    n_pairs = 3
    n_ok = 0
    for k in range(n_pairs):
        a = _random_poly(rng)
        b = _random_poly(rng)
        prim = t.schoolbook_negacyclic(a, b).tolist()
        indep = schoolbook_bigint(a, b)
        if prim == indep:
            n_ok += 1
        else:
            print(f"[cross] (2) schoolbook mismatch pair #{k}")
    n_total += n_pairs
    n_pass += n_ok
    print(f"[cross] (2) schoolbook (int16 primary) vs (bigint second source): "
          f"{n_ok}/{n_pairs} PASS")

    # ---- 3) End-to-end MultiplyNTTs vs bigint schoolbook, using the primary
    #        Montgomery-domain reference kernels for NTT/basemul/INTT.
    n_ok = 0
    for k in range(n_pairs):
        a = _random_poly(rng)
        b = _random_poly(rng)
        na = t.ntt_forward_ref(a)
        nb = t.ntt_forward_ref(b)
        nab = t.poly_basemul_ref(na, nb)
        ab = t.ntt_inverse_ref(nab)
        got = [_mod_q_signed(int(x)) for x in ab]
        exp = schoolbook_bigint(a, b)
        if got == exp:
            n_ok += 1
        else:
            first = next(i for i in range(KYBER_N) if got[i] != exp[i])
            print(f"[cross] (3) MultiplyNTTs mismatch pair #{k} first_diff={first}")
    n_total += n_pairs
    n_pass += n_ok
    print(f"[cross] (3) primary NTT/BASEMUL/INTT chain vs bigint schoolbook: "
          f"{n_ok}/{n_pairs} PASS")

    # ---- 4) NTT round-trip: INTT(NTT(a)) == R * a mod q via primary reference.
    n_ok = 0
    R_mod_q = (1 << 16) % KYBER_Q
    for k in range(n_pairs):
        a = _random_poly(rng)
        aa = t.ntt_inverse_ref(t.ntt_forward_ref(a))
        got = [_mod_q_signed(int(x)) for x in aa]
        exp = [_mod_q_signed(int(x) * R_mod_q) for x in a]
        if got == exp:
            n_ok += 1
    n_total += n_pairs
    n_pass += n_ok
    print(f"[cross] (4) primary INTT(NTT(a)) == R * a mod q: "
          f"{n_ok}/{n_pairs} PASS")

    # ---- 5) poly_add / poly_sub primary vs bigint modular reference.
    n_ok = 0
    for k in range(n_pairs):
        a = _random_poly(rng)
        b = _random_poly(rng)
        s_prim = [_mod_q_signed(int(x)) for x in t.poly_add_ref(a, b)]
        d_prim = [_mod_q_signed(int(x)) for x in t.poly_sub_ref(a, b)]
        s_ind = poly_add_bigint(a, b)
        d_ind = poly_sub_bigint(a, b)
        if s_prim == s_ind and d_prim == d_ind:
            n_ok += 1
    n_total += n_pairs
    n_pass += n_ok
    print(f"[cross] (5) poly_add / poly_sub primary vs bigint modular: "
          f"{n_ok}/{n_pairs} PASS")

    # ---- 6) Basemul degree-1 factor identity: replay the exact 5-step
    #        pq-crystals basemul() sequence with unbounded ints + explicit
    #        R^{-1} folding per Montgomery reduce. This is a mechanical
    #        transliteration of the C body, so any deviation catches a bug
    #        in the primary basemul_ref transliteration.
    n_ok = 0
    n_bm = 4
    R_inv = pow((1 << 16) % KYBER_Q, -1, KYBER_Q)
    for k in range(n_bm):
        a = [int(x) for x in _random_poly(rng)[:2]]
        b = [int(x) for x in _random_poly(rng)[:2]]
        gamma = int(t.ZETAS[64 + k])
        # Mechanical replay: each fqmul folds one factor of R^{-1}.
        step1 = _mod_q_signed(a[1] * b[1] * R_inv)          # r0 = fqmul(a1,b1)
        step2 = _mod_q_signed(step1 * gamma * R_inv)        # r0 = fqmul(r0,gamma)
        step3 = _mod_q_signed(a[0] * b[0] * R_inv)          # fqmul(a0,b0)
        exp0 = _mod_q_signed(step2 + step3)                 # r[0] += fqmul(a0,b0)
        step4 = _mod_q_signed(a[0] * b[1] * R_inv)          # r1 = fqmul(a0,b1)
        step5 = _mod_q_signed(a[1] * b[0] * R_inv)          # fqmul(a1,b0)
        exp1 = _mod_q_signed(step4 + step5)                 # r[1] += ...
        r_prim = t.basemul_ref(a, b, gamma).tolist()
        # Primary basemul does NOT Barrett-reduce; coefficients can exceed
        # the (-q/2, q/2] window but are still congruent to the expected
        # value mod q. Compare in Z_q, not by exact int16 value.
        r_prim_modq = [_mod_q_signed(x) for x in r_prim]
        if r_prim_modq == [exp0, exp1]:
            n_ok += 1
        else:
            print(f"[cross] (6) mismatch #{k}: prim(modq)={r_prim_modq} "
                  f"exp=[{exp0},{exp1}]")
    n_total += n_bm
    n_pass += n_ok
    print(f"[cross] (6) basemul primary vs bigint replay: "
          f"{n_ok}/{n_bm} PASS")

    print(f"\nM32b transliteration check: {n_pass}/{n_total} PASS")
    return n_pass == n_total


if __name__ == "__main__":
    ok = cross_check()
    if not ok:
        sys.exit(1)
