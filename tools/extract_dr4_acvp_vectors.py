import json
from pathlib import Path
from tests.pqc_device_resident.dr3_reference import kpke_encrypt_reference
from tests.pqc_device_resident.dr4_reference import kpke_decrypt_reference

REPO_ROOT = Path(".")
KG_PATH = REPO_ROOT / "tests" / "pqc_device_resident" / "data" / "dr2d_nist_acvp_mlkem512_kpke_keygen_25.json"
ENC_PATH = REPO_ROOT / "tests" / "pqc_device_resident" / "data" / "dr3_nist_acvp_mlkem512_kpke_encrypt_25.json"
OUTPUT_PATH = REPO_ROOT / "tests" / "pqc_device_resident" / "data" / "dr4_nist_acvp_mlkem512_kpke_decrypt_25.json"

kg_doc = json.loads(KG_PATH.read_text(encoding="utf-8"))
enc_doc = json.loads(ENC_PATH.read_text(encoding="utf-8"))

kg_tests = {t["tcId"]: t for t in kg_doc["tests"]}
enc_cases = {c["tcId"]: c for c in enc_doc["cases"]}

cases = []
for tc_id in range(1, 26):
    kt = kg_tests[tc_id]
    ec = enc_cases[tc_id]

    ek_pke = bytes.fromhex(kt["ekPKE"])
    dk_pke = bytes.fromhex(kt["dkPKE"])
    m = bytes.fromhex(ec["m"])
    r = bytes.fromhex(ec["r"])

    # Compute ciphertext under this exact ACVP keypair
    c = kpke_encrypt_reference(ek_pke, m, r)
    assert len(c) == 768

    # Decrypt and verify roundtrip
    m_dec = kpke_decrypt_reference(dk_pke, c)
    assert m_dec == m, f"Roundtrip failed for tcId {tc_id}"

    cases.append({
        "tcId": tc_id,
        "dkPke": dk_pke.hex(),
        "c": c.hex(),
        "m": m.hex(),
    })

OUTPUT_PATH.write_text(json.dumps({
    "description": "NIST ACVP ML-KEM-512 K-PKE.Decrypt 25 test cases",
    "parameterSet": "ML-KEM-512",
    "total": len(cases),
    "cases": cases,
}, indent=2), encoding="utf-8")

print(f"Successfully generated {len(cases)} verified ACVP roundtrip cases in {OUTPUT_PATH}")
