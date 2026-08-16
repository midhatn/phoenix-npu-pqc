"""M33e - ML-DSA Sign gate (FIPS 204, Post-Quantum Cryptography).

Targets the NIST ACVP-Server `ML-DSA-sigGen-FIPS204` vectors, specifically
the internal-deterministic test groups (tgIds 7-12, 90 tests total, 15 per
group). These groups have `deterministic=True` and `signatureInterface=
"internal"`, meaning:

    - rnd is the all-zero 32-byte string,
    - signatureInterface="internal" -> the composer's `sign_internal` is the
      direct target (no external message-encoding wrapper),
    - externalMu=True variants provide `mu` directly; externalMu=False
      variants provide `message` and the composer derives mu = H(tr || m).

Comparison is bit-exact against `expectedResults.signature` from the ACVP
KAT database, i.e. the reference-C signature is fully reproduced.

Two backends run under the same harness: reference-Python fallback in
SiliconBackend, or hardware runners (`phoenix_sdr_dsp.silicon.m33{a,b}_runner`)
when importable. Sandbox always runs the reference path; laptop runs whichever
runners it has wired.

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
PROMPT = VECTOR_DIR / "ML-DSA-sigGen-FIPS204_prompt.json"
EXPECTED = VECTOR_DIR / "ML-DSA-sigGen-FIPS204_expectedResults.json"

# Internal + deterministic groups only.
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
    print("M33e - ML-DSA Sign_internal gate (FIPS 204, Post-Quantum Crypto)")
    print(f"  vectors: {PROMPT.name}")
    print(f"  scope:   tgIds {sorted(TARGET_TGIDS)} (internal, deterministic)")
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
        set_total = 0
        rnd = bytes(32)
        for t in tg["tests"]:
            m = bytes.fromhex(t["mu"]) if ex_mu else bytes.fromhex(t["message"])
            sk = bytes.fromhex(t["sk"])
            sig = comp.sign_internal(sk, m, rnd, external_mu=ex_mu)
            want = bytes.fromhex(exp_by_tc[t["tcId"]]["signature"])
            set_total += 1
            total += 1
            if sig == want:
                set_ok += 1
                total_ok += 1
            else:
                failures.append(f"tcId={t['tcId']} {ps} externalMu={ex_mu}")
        status = "PASS" if set_ok == set_total else "FAIL"
        print(f"  tg={tg['tgId']:<2}  {ps:<10}  ex_mu={ex_mu!s:<5}  {set_ok}/{set_total}  {status}")

    print("-" * 72)
    status = "PASS" if total_ok == total else "FAIL"
    print(f"  TOTAL                                       {total_ok}/{total}   {status}")
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
