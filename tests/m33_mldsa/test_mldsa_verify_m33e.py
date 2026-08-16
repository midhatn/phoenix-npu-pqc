"""M33e - ML-DSA Verify gate (FIPS 204, Post-Quantum Cryptography).

Targets NIST ACVP-Server `ML-DSA-sigVer-FIPS204` internal-interface test
groups (tgIds 7-12, 15 tests per group across ML-DSA-44 / 65 / 87 x
externalMu=True/False). Each group mixes must-pass (valid) and must-reject
(tampered pk / z / h / signature) test cases; the composer must return the
`testPassed` value that ACVP specifies for each tcId.

This is the negative-branch surface for the ML-DSA silicon composer:
- must-pass vectors exercise the correct-path silicon dispatch,
- must-reject vectors exercise the norm-check (M33b MODE 4) and popcount
  early exits.

References
    FIPS 204: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
    NIST ACVP-Server ML-DSA test vectors:
      https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files
    dilithium-py: https://github.com/GiacomoPope/dilithium-py
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.m33_mldsa.mldsa_composer import MLDSAComposer, SiliconBackend

VECTOR_DIR = REPO / "tests" / "m33_mldsa" / "vectors"
PROMPT = VECTOR_DIR / "ML-DSA-sigVer-FIPS204_prompt.json"
EXPECTED = VECTOR_DIR / "ML-DSA-sigVer-FIPS204_expectedResults.json"

TARGET_TGIDS = {7, 8, 9, 10, 11, 12}


def _try_silicon_backend() -> tuple[SiliconBackend, str]:
    m33a = None
    m33b = None
    tags = []
    try:
        mod_a = importlib.import_module("phoenix_sdr_dsp.silicon.m33a_runner")
        m33a = mod_a.run
        tags.append("m33a:silicon")
    except Exception:  # noqa: BLE001
        tags.append("m33a:reference")
    try:
        mod_b = importlib.import_module("phoenix_sdr_dsp.silicon.m33b_runner")
        m33b = mod_b.run
        tags.append("m33b:silicon")
    except Exception:  # noqa: BLE001
        tags.append("m33b:reference")
    return SiliconBackend(m33a=m33a, m33b=m33b), ", ".join(tags)


def main() -> int:
    prompt = json.loads(PROMPT.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    exp_by_tc = {t["tcId"]: t for g in expected["testGroups"] for t in g["tests"]}

    backend, backend_tag = _try_silicon_backend()

    print("=" * 72)
    print("M33e - ML-DSA Verify_internal gate (FIPS 204, Post-Quantum Crypto)")
    print(f"  vectors: {PROMPT.name}")
    print(f"  scope:   tgIds {sorted(TARGET_TGIDS)} (internal, mixed pass/fail)")
    print(f"  backend: {backend_tag}")
    print("=" * 72)

    total_ok = 0
    total = 0
    failures: list[str] = []

    for tg in prompt["testGroups"]:
        if tg["tgId"] not in TARGET_TGIDS:
            continue
        ps = tg["parameterSet"]
        ex_mu = tg.get("externalMu", False)
        comp = MLDSAComposer(ps, backend=backend)
        set_ok = 0
        set_pass = 0
        set_fail_expected = 0
        set_total = 0
        for t in tg["tests"]:
            pk = bytes.fromhex(t["pk"])
            m = bytes.fromhex(t["mu"]) if ex_mu else bytes.fromhex(t["message"])
            sig = bytes.fromhex(t["signature"])
            got = comp.verify_internal(pk, m, sig, external_mu=ex_mu)
            want = exp_by_tc[t["tcId"]]["testPassed"]
            set_total += 1
            total += 1
            if want:
                set_pass += 1
            else:
                set_fail_expected += 1
            if got == want:
                set_ok += 1
                total_ok += 1
            else:
                failures.append(
                    f"tcId={t['tcId']} {ps} ex_mu={ex_mu} want={want} got={got}"
                )
        status = "PASS" if set_ok == set_total else "FAIL"
        print(
            f"  tg={tg['tgId']:<2}  {ps:<10}  ex_mu={ex_mu!s:<5}  "
            f"{set_ok}/{set_total}   ({set_pass} valid, {set_fail_expected} reject)  {status}"
        )

    print("-" * 72)
    status = "PASS" if total_ok == total else "FAIL"
    print(f"  TOTAL                                             {total_ok}/{total}   {status}")
    print("=" * 72)

    if failures:
        print()
        print("Failures (first 10):")
        for line in failures[:10]:
            print("  " + line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
