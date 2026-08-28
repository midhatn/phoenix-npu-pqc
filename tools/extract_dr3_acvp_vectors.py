"""Offline extraction and verification for the pinned DR3 ACVP corpus (ML-KEM-512 K-PKE.Encrypt)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = REPO_ROOT / "tests" / "m32_mlkem" / "vectors" / "encapdecap_prompt.json"
EXPECTED_PATH = REPO_ROOT / "tests" / "m32_mlkem" / "vectors" / "encapdecap_expected.json"
OUTPUT_PATH = REPO_ROOT / "tests" / "pqc_device_resident" / "data" / "dr3_nist_acvp_mlkem512_kpke_encrypt_25.json"


def main() -> None:
    prompt_doc = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    expected_doc = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    prompt_groups = [g for g in prompt_doc["testGroups"] if g.get("parameterSet") == "ML-KEM-512" and g.get("function") == "encapsulation"]
    expected_groups = [g for g in expected_doc["testGroups"] if g.get("tgId") == prompt_groups[0]["tgId"]]

    prompt_tests = {t["tcId"]: t for t in prompt_groups[0]["tests"]}
    expected_tests = {t["tcId"]: t for t in expected_groups[0]["tests"]}

    cases = []
    for tc_id in range(1, 26):
        pt = prompt_tests[tc_id]
        et = expected_tests[tc_id]

        ek_bytes = bytes.fromhex(pt["ek"])
        m_bytes = bytes.fromhex(pt["m"])
        c_bytes = bytes.fromhex(et["c"])

        assert len(ek_bytes) == 800
        assert len(m_bytes) == 32
        assert len(c_bytes) == 768

        # In FIPS 203 Encaps: (K_bar, r) = G(m || H(ek))
        h_ek = hashlib.sha3_256(ek_bytes).digest()
        g_out = hashlib.sha3_512(m_bytes + h_ek).digest()
        k_bar = g_out[:32]
        r = g_out[32:]
        assert len(r) == 32

        cases.append({
            "tcId": tc_id,
            "ek": ek_bytes.hex(),
            "m": m_bytes.hex(),
            "r": r.hex(),
            "c": c_bytes.hex(),
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "description": "NIST ACVP ML-KEM-512 K-PKE.Encrypt 25 test cases",
        "parameterSet": "ML-KEM-512",
        "total": len(cases),
        "cases": cases,
    }
    OUTPUT_PATH.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
    print(f"Extracted {len(cases)} DR3 test cases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
