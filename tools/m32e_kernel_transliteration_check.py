# m32e_kernel_transliteration_check.py
# ==================================================================================
# Second-source cross-check for M32e: verifies that mlkem_composer.HostBackend
# and the FIPS 203 composition on top of it are byte-for-byte equal to a fully
# independent, NIST-KAT-verified reference (kyber-py v1.2.0).
#
# This tool runs entirely on the sandbox/laptop CPU (no @iron.jit dispatch).  Its
# job is to confirm that the pq-crystals-style pure-Python reference we plan to
# route through Phoenix NPU produces the exact same bytes as the independently
# implemented (Python) library that passes NIST ACVP-Server ML-KEM-512 KATs.
#
# Post-Quantum Cryptography (PQC) context:
#   ML-KEM-512 = FIPS 203 Kyber-512 = NIST PQC KEM standard (Aug 2024).
#
# References:
#   FIPS 203 (final) - https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
#   FIPS 203 landing - https://csrc.nist.gov/pubs/fips/203/final
#   NIST ACVP-Server - https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files
#   kyber-py         - https://pypi.org/project/kyber-py/
#   pq-crystals ref  - https://github.com/pq-crystals/kyber/tree/main/ref
# ==================================================================================

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSER_DIR = REPO_ROOT / "tests" / "m32_mlkem"
VECTOR_DIR = COMPOSER_DIR / "vectors"

# Allow importing the composer module.
sys.path.insert(0, str(COMPOSER_DIR))


def _lazy_import():
    """Lazy import so the module loads cleanly even under ruff import checks."""
    from mlkem_composer import (
        HostBackend,
        mlkem_decaps_internal,
        mlkem_encaps_internal,
        mlkem_keygen_internal,
    )
    return HostBackend, mlkem_keygen_internal, mlkem_encaps_internal, mlkem_decaps_internal


def _lazy_kyber_py():
    from kyber_py.ml_kem import ML_KEM_512
    return ML_KEM_512


def _hx(s: str) -> bytes:
    return bytes.fromhex(s)


def _load_json(name: str):
    with open(VECTOR_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def check_all(verbose: bool = False) -> tuple[int, int]:
    """Return (n_pass, n_fail) across all four axes.

    Axis 1: composer HostBackend keygen == kyber-py keygen  (25 KATs)
    Axis 2: composer HostBackend encaps == kyber-py encaps  (25 KATs)
    Axis 3: composer HostBackend decaps == kyber-py decaps  (10 KATs)
    Axis 4: kyber-py output == NIST ACVP expected            (60 KATs)  [oracle check]
    """
    HostBackend, keygen, encaps, decaps = _lazy_import()
    ML_KEM_512 = _lazy_kyber_py()

    be = HostBackend()
    n_pass = n_fail = 0

    # ---- KeyGen (25 tcIds) ----------------------------------------------
    kg_p = _load_json("keygen_prompt.json")
    kg_e = _load_json("keygen_expected.json")
    for tg_p, tg_e in zip(kg_p["testGroups"], kg_e["testGroups"]):
        if tg_p["parameterSet"] != "ML-KEM-512":
            continue
        exp_by_id = {t["tcId"]: t for t in tg_e["tests"]}
        for t in tg_p["tests"]:
            exp = exp_by_id[t["tcId"]]
            d, z = _hx(t["d"]), _hx(t["z"])
            exp_ek = _hx(exp["ek"])
            exp_dk = _hx(exp["dk"])

            # composer
            keys = keygen(be, d, z)
            # kyber-py
            kp_ek, kp_dk = ML_KEM_512._keygen_internal(d, z)

            comp_ok = (keys.ek == kp_ek and keys.dk == kp_dk)
            oracle_ok = (kp_ek == exp_ek and kp_dk == exp_dk)
            nist_ok = (keys.ek == exp_ek and keys.dk == exp_dk)

            if comp_ok and oracle_ok and nist_ok:
                n_pass += 1
                if verbose:
                    print(f"  KG tcId={t['tcId']:3d}: PASS")
            else:
                n_fail += 1
                print(f"  KG tcId={t['tcId']:3d}: FAIL "
                      f"comp={comp_ok} oracle={oracle_ok} nist={nist_ok}")

    # ---- Encaps + Decaps (25 + 10) --------------------------------------
    ed_p = _load_json("encapdecap_prompt.json")
    ed_e = _load_json("encapdecap_expected.json")
    for tg_p, tg_e in zip(ed_p["testGroups"], ed_e["testGroups"]):
        if tg_p["parameterSet"] != "ML-KEM-512":
            continue
        func = tg_p.get("function", "")
        if func not in ("encapsulation", "decapsulation"):
            continue
        exp_by_id = {t["tcId"]: t for t in tg_e["tests"]}
        for t in tg_p["tests"]:
            exp = exp_by_id[t["tcId"]]
            if func == "encapsulation":
                ek = _hx(t["ek"])
                m = _hx(t["m"])
                exp_K = _hx(exp["k"])
                exp_c = _hx(exp["c"])

                K, c = encaps(be, ek, m)
                kp_K, kp_c = ML_KEM_512._encaps_internal(ek, m)

                comp_ok = (K == kp_K and c == kp_c)
                oracle_ok = (kp_K == exp_K and kp_c == exp_c)
                nist_ok = (K == exp_K and c == exp_c)

                if comp_ok and oracle_ok and nist_ok:
                    n_pass += 1
                    if verbose:
                        print(f"  EN tcId={t['tcId']:3d}: PASS")
                else:
                    n_fail += 1
                    print(f"  EN tcId={t['tcId']:3d}: FAIL "
                          f"comp={comp_ok} oracle={oracle_ok} nist={nist_ok}")
            else:  # decapsulation
                dk = _hx(t.get("dk") or tg_p.get("dk"))
                c = _hx(t["c"])
                exp_K = _hx(exp["k"])

                K = decaps(be, dk, c)
                kp_K = ML_KEM_512._decaps_internal(dk, c)

                comp_ok = (K == kp_K)
                oracle_ok = (kp_K == exp_K)
                nist_ok = (K == exp_K)

                if comp_ok and oracle_ok and nist_ok:
                    n_pass += 1
                    if verbose:
                        print(f"  DE tcId={t['tcId']:3d}: PASS")
                else:
                    n_fail += 1
                    print(f"  DE tcId={t['tcId']:3d}: FAIL "
                          f"comp={comp_ok} oracle={oracle_ok} nist={nist_ok}")

    return n_pass, n_fail


def main() -> int:
    verbose = ("-v" in sys.argv) or ("--verbose" in sys.argv)
    print("M32e ML-KEM-512 transliteration cross-check")
    print("-" * 60)
    print("Axes:")
    print("  1. composer HostBackend  ==  kyber-py       (KG + Enc + Dec)")
    print("  2. kyber-py              ==  NIST ACVP KAT  (KG + Enc + Dec)")
    print("  3. composer HostBackend  ==  NIST ACVP KAT  (KG + Enc + Dec)")
    print("-" * 60)

    n_pass, n_fail = check_all(verbose=verbose)

    print("-" * 60)
    print(f"Result: {n_pass} PASS, {n_fail} FAIL over 60 NIST KATs "
          "(25 KeyGen + 25 Encap + 10 Decap)")
    if n_fail == 0:
        print("-> M32e composer transliteration is trustworthy for silicon gates.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
