"""M33e - static transliteration audit for ML-DSA Sign_internal / Verify_internal.

Statically verifies that the composer in tests/m33_mldsa/mldsa_composer.py
routes every data-parallel step of Sign_internal (Alg 7) and Verify_internal
(Alg 8) through the M33a and M33b silicon dispatch seams, and that the
required silicon primitives (Decompose, HighBits, LowBits, MakeHint, UseHint,
CheckNormBound) are all present as MLDSAComposer methods.

This runs entirely offline: no vectors, no dilithium-py execution. It is a
guardrail against accidentally deleting a silicon call site or reintroducing
a Python numeric primitive.

References
    FIPS 204: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSER = REPO / "tests" / "m33_mldsa" / "mldsa_composer.py"


def main() -> int:
    src = COMPOSER.read_text(encoding="utf-8")
    checks: list[tuple[str, bool]] = []

    # -- methods exist --
    for name in [
        "poly_ntt",
        "poly_invntt",
        "poly_basemul",
        "poly_add_mod",
        "poly_power2round",
        "poly_decompose",
        "poly_high_bits",
        "poly_low_bits",
        "poly_make_hint",
        "poly_use_hint",
        "poly_check_norm",
        "sign_internal",
        "verify_internal",
    ]:
        checks.append((f"method {name} present", f"def {name}(" in src))

    # -- sign_internal composition audit --
    if "def sign_internal(" not in src:
        checks.append(("sign_internal defined", False))
    else:
        body = src.split("def sign_internal(", 1)[1].split("def verify_internal(", 1)[0]
        for tag, needle in [
            ("Sign: ExpandA",         "_expand_matrix_from_seed"),
            ("Sign: NTT s1/s2/t0",    "_vec_to_ntt"),
            ("Sign: ExpandMask",      "_expand_mask_vector"),
            ("Sign: A @ y_hat",       "_matmul_A_vec_ntt"),
            ("Sign: HighBits(w)",     "poly_high_bits"),
            ("Sign: SampleInBall",    "sample_in_ball"),
            ("Sign: c*s1 via NTT",    "_scale_vec_ntt"),
            ("Sign: LowBits(w-c*s2)", "poly_low_bits"),
            ("Sign: MakeHint",        "poly_make_hint"),
            ("Sign: CheckNormBound",  "poly_check_norm"),
            ("Sign: rejection loop",  "continue"),
            ("Sign: pack signature",  "_pack_sig"),
        ]:
            checks.append((tag, needle in body))

    # -- verify_internal composition audit --
    if "def verify_internal(" not in src:
        checks.append(("verify_internal defined", False))
    else:
        body = src.split("def verify_internal(", 1)[1]
        for tag, needle in [
            ("Verify: unpack pk",       "_unpack_pk"),
            ("Verify: unpack sig",      "_unpack_sig"),
            ("Verify: ExpandA",         "_expand_matrix_from_seed"),
            ("Verify: SampleInBall",    "sample_in_ball"),
            ("Verify: A @ z_hat",       "_matmul_A_vec_ntt"),
            ("Verify: c*t1 via NTT",    "_scale_vec_ntt"),
            ("Verify: UseHint",         "poly_use_hint"),
            ("Verify: CheckNormBound",  "poly_check_norm"),
            ("Verify: c_tilde compare", "c_tilde ==" ),
            ("Verify: externalMu path", "external_mu"),
        ]:
            checks.append((tag, needle in body))

    ok = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            ok = False

    print("=" * 72)
    print("M33e Sign/Verify composer transliteration check:",
          "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
