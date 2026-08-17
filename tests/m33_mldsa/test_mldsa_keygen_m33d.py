"""M33d - ML-DSA KeyGen gate (FIPS 204, Post-Quantum Cryptography).

Native-only gate against NIST ACVP-Server ML-DSA-keyGen-FIPS204 vectors. The
M33a and M33b tile runners must bit-match all 75 ACVP KAT (pk, sk) tuples
across ML-DSA-44, ML-DSA-65, ML-DSA-87 (25 vectors each). A missing native
runtime is an explicit nonzero failure, never a Python-reference pass.

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
PROMPT = VECTOR_DIR / "ML-DSA-keyGen-FIPS204_prompt.json"
EXPECTED = VECTOR_DIR / "ML-DSA-keyGen-FIPS204_expectedResults.json"


def _try_silicon_backend() -> tuple[SiliconBackend | None, str]:
    """Build an all-native backend; partial/reference composition is forbidden."""
    try:
        mod_a = importlib.import_module("phoenix_sdr_dsp.silicon.m33a_runner")
        mod_b = importlib.import_module("phoenix_sdr_dsp.silicon.m33b_runner")
        mod_a.require_hardware_runtime()
        mod_b.require_hardware_runtime()
        return SiliconBackend(m33a=mod_a.run, m33b=mod_b.run), (
            "m33a:silicon, m33b:silicon"
        )
    except Exception as exc:  # noqa: BLE001 - do not silently choose reference
        return None, f"m33:unavailable ({type(exc).__name__}: {exc})"


def main() -> int:
    prompt = json.loads(PROMPT.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    exp_by_tc = {t["tcId"]: t for g in expected["testGroups"] for t in g["tests"]}

    backend, backend_tag = _try_silicon_backend()

    print("=" * 72)
    print("M33d - ML-DSA KeyGen silicon gate (FIPS 204, Post-Quantum Crypto)")
    print(f"  vectors: {PROMPT.name}")
    print(f"Backend: {backend_tag}")
    print("=" * 72)
    if backend is None:
        print("FAIL: both native M33 runners are required; no reference composer ran.")
        return 2

    per_set: dict[str, list[int]] = {}
    total_ok = 0
    total = 0
    failures: list[str] = []

    for tg in prompt["testGroups"]:
        ps = tg["parameterSet"]
        comp = MLDSAComposer(ps, backend=backend)
        set_ok = 0
        set_total = 0
        for t in tg["tests"]:
            seed = bytes.fromhex(t["seed"])
            pk, sk = comp.keygen_internal(seed)
            ex = exp_by_tc[t["tcId"]]
            pk_hit = pk.hex().upper() == ex["pk"].upper()
            sk_hit = sk.hex().upper() == ex["sk"].upper()
            set_total += 1
            total += 1
            if pk_hit and sk_hit:
                set_ok += 1
                total_ok += 1
            else:
                failures.append(
                    f"tcId={t['tcId']} {ps}: pk_ok={pk_hit} sk_ok={sk_hit}"
                )
        per_set[ps] = [set_ok, set_total]
        status = "PASS" if set_ok == set_total else "FAIL"
        print(f"  {ps:<12}   {set_ok:>3}/{set_total:<3}   {status}")

    print("-" * 72)
    status = "PASS" if total_ok == total else "FAIL"
    print(f"  TOTAL         {total_ok:>3}/{total:<3}   {status}")
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
