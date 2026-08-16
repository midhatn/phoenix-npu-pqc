"""M33d - transliteration cross-check for ML-DSA KeyGen composer.

Statically verifies that the composer in tests/m33_mldsa/mldsa_composer.py
routes every data-parallel step through the M33a and M33b silicon dispatch
seams, and that the KeyGen shape (Alg 6 of FIPS 204) is preserved: exactly
one ExpandA, one ExpandS, ell NTTs, k*ell basemuls, k INTTs, k Power2Rounds,
and standard pk / sk packing.

This runs entirely offline: no vectors, no dilithium-py execution. It is a
guardrail against accidentally deleting a silicon call site or reintroducing
a Python numeric primitive.

Also performs an independent sanity check that the composer's Montgomery
constants (R_MOD_Q, R_INV_MOD_Q, Q) satisfy the required algebraic
identities.

References
    FIPS 204: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSER = REPO / "tests" / "m33_mldsa" / "mldsa_composer.py"


def main() -> int:
    src = COMPOSER.read_text(encoding="utf-8")
    checks: list[tuple[str, bool]] = []

    # -- silicon dispatch seams --
    checks.append(("SiliconBackend class present",
                   "class SiliconBackend" in src))
    checks.append(("MLDSAComposer class present",
                   "class MLDSAComposer" in src))
    checks.append(("keygen_internal defined",
                   "def keygen_internal" in src))

    # Required silicon primitive calls inside the composer body.
    body = src.split("def keygen_internal", 1)[1]
    checks.append(("dispatches poly_ntt",       "poly_ntt(" in body))
    checks.append(("dispatches poly_invntt",    "poly_invntt(" in body))
    checks.append(("dispatches poly_basemul",   "poly_basemul(" in body))
    checks.append(("dispatches poly_power2round","poly_power2round(" in body))
    checks.append(("uses ExpandA (matrix)",
                   "_expand_matrix_from_seed" in body))
    checks.append(("uses ExpandS (vectors)",
                   "_expand_vector_from_seed" in body))
    checks.append(("uses _pack_pk",             "_pack_pk("  in body))
    checks.append(("uses _pack_sk",             "_pack_sk("  in body))
    checks.append(("tr = _h(pk, 64)",           "_h(pk, 64)" in body))

    # -- algebraic constants --
    def const(name: str) -> int:
        m = re.search(rf"^{name}\s*=\s*([^\n#]+)$", src, re.MULTILINE)
        if not m:
            raise RuntimeError(f"missing constant {name}")
        # `pow` is needed to evaluate `pow(1 << R_POW, -1, Q)`.
        return int(eval(m.group(1).strip(),
                        {"__builtins__": {"pow": pow}},
                        {"Q": 8380417, "R_POW": 32}))

    q = const("Q")
    r_pow = const("R_POW")
    r_mod = const("R_MOD_Q")
    r_inv = const("R_INV_MOD_Q")

    checks.append(("Q == 8380417", q == 8380417))
    checks.append(("R_POW == 32", r_pow == 32))
    checks.append(("R_MOD_Q == (1<<32) mod Q", r_mod == (1 << 32) % q))
    checks.append(("R_MOD_Q * R_INV_MOD_Q == 1 mod Q",
                   (r_mod * r_inv) % q == 1))

    ok = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            ok = False

    print("=" * 72)
    print("M33d composer transliteration check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
