"""Offline extraction and verification for Milestone DR5 ACVP corpus (ML-KEM-512 ML-KEM.KeyGen)."""
from __future__ import annotations

import json
from pathlib import Path
import hashlib

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = REPO_ROOT / "tests" / "m32_mlkem" / "vectors" / "keygen_prompt.json"
EXPECTED_PATH = REPO_ROOT / "tests" / "m32_mlkem" / "vectors" / "keygen_expected.json"
OUTPUT_PATH = REPO_ROOT / "tests" / "pqc_device_resident" / "data" / "dr5_nist_acvp_mlkem512_keygen_25.json"

def main() -> None:
    prompt_doc = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    expected_doc = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    prompt_tests = {t["tcId"]: t for t in prompt_doc["testGroups"][0]["tests"]}
    expected_tests = {t["tcId"]: t for t in expected_doc["testGroups"][0]["tests"]}

    cases = []
    for tc_id in range(1, 26):
        pt = prompt_tests[tc_id]
        et = expected_tests[tc_id]

        d_hex = pt["d"]
        z_hex = pt["z"]
        ek_hex = et["ek"]
        dk_hex = et["dk"]

        assert len(bytes.fromhex(d_hex)) == 32
        assert len(bytes.fromhex(z_hex)) == 32
        assert len(bytes.fromhex(ek_hex)) == 800
        assert len(bytes.fromhex(dk_hex)) == 1632

        cases.append({
            "tcId": tc_id,
            "d": d_hex,
            "z": z_hex,
            "ek": ek_hex,
            "dk": dk_hex,
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "description": "NIST ACVP ML-KEM-512 ML-KEM.KeyGen 25 test cases",
        "parameterSet": "ML-KEM-512",
        "total": len(cases),
        "cases": cases,
    }
    OUTPUT_PATH.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
    print(f"Extracted {len(cases)} DR5 test cases to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
