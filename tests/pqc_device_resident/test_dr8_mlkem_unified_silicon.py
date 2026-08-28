# SPDX-License-Identifier: Apache-2.0
"""DR8 Silicon Validation Suite: NIST FIPS 203 ML-KEM Parameter-Set Expansion (512, 768, 1024)."""
import json
import os
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phoenix_sdr_dsp.pqc.dr8_mlkem_service import mlkem_keygen, mlkem_encaps, mlkem_decaps

def test_dr8_mlkem768_silicon():
    dataset_path = Path(__file__).resolve().parent / "data" / "dr8_nist_acvp_mlkem768_25.json"
    data = json.loads(dataset_path.read_text())
    cases = data["cases"]
    passed = 0
    print(f"=== DR8 ML-KEM-768 Physical Silicon Test ({len(cases)} cases) ===")
    for idx, case in enumerate(cases):
        tc = case.get("tcId") or case.get("tc_id", f"case_{idx+1}")
        is_paired = "dr8_paired" in tc or case.get("is_rejection", False)

        if not is_paired and "d" in case and "m" in case:
            # KeyGen
            d = bytes.fromhex(case["d"])
            z = bytes.fromhex(case["z"])
            ek_exp = bytes.fromhex(case["ek"])
            dk_exp = bytes.fromhex(case["dk"])
            ek_act, dk_act = mlkem_keygen(d, z, "ML-KEM-768", idx + 1)
            assert ek_act == ek_exp, f"KeyGen ek mismatch on {tc}"
            assert dk_act == dk_exp, f"KeyGen dk mismatch on {tc}"

            # Encaps
            m = bytes.fromhex(case["m"])
            c_exp = bytes.fromhex(case["c"])
            k_exp = bytes.fromhex(case["k"])
            c_act, k_act = mlkem_encaps(ek_act, m, "ML-KEM-768", idx + 1)
            assert c_act == c_exp, f"Encaps c mismatch on {tc}"
            assert k_act == k_exp, f"Encaps k mismatch on {tc}"

            # Decaps
            k_dec = mlkem_decaps(dk_act, c_act, "ML-KEM-768", idx + 1)
            assert k_dec == k_exp, f"Decaps k mismatch on {tc}"
        else:
            # Decaps (includes paired valid and invalid ciphertexts)
            dk = bytes.fromhex(case["dk"])
            c = bytes.fromhex(case["c"])
            k_exp = bytes.fromhex(case["k"])
            k_dec = mlkem_decaps(dk, c, "ML-KEM-768", idx + 1)
            assert k_dec == k_exp, f"Decaps k mismatch on {tc}"

        print(f"  [{idx+1:02d}/{len(cases):02d}] {tc:24s}: PASS")
        passed += 1

    print(f"DR8 ML-KEM-768 Result: {passed}/{len(cases)} PASS\n")
    return passed, len(cases)

def test_dr8_mlkem1024_silicon():
    dataset_path = Path(__file__).resolve().parent / "data" / "dr8_nist_acvp_mlkem1024_25.json"
    data = json.loads(dataset_path.read_text())
    cases = data["cases"]
    passed = 0
    print(f"=== DR8 ML-KEM-1024 Physical Silicon Test ({len(cases)} cases) ===")
    for idx, case in enumerate(cases):
        tc = case.get("tcId") or case.get("tc_id", f"case_{idx+1}")
        is_paired = "dr8_paired" in tc or case.get("is_rejection", False)

        if not is_paired and "d" in case and "m" in case:
            # KeyGen
            d = bytes.fromhex(case["d"])
            z = bytes.fromhex(case["z"])
            ek_exp = bytes.fromhex(case["ek"])
            dk_exp = bytes.fromhex(case["dk"])
            ek_act, dk_act = mlkem_keygen(d, z, "ML-KEM-1024", idx + 1)
            assert ek_act == ek_exp, f"KeyGen ek mismatch on {tc}"
            assert dk_act == dk_exp, f"KeyGen dk mismatch on {tc}"

            # Encaps
            m = bytes.fromhex(case["m"])
            c_exp = bytes.fromhex(case["c"])
            k_exp = bytes.fromhex(case["k"])
            c_act, k_act = mlkem_encaps(ek_act, m, "ML-KEM-1024", idx + 1)
            assert c_act == c_exp, f"Encaps c mismatch on {tc}"
            assert k_act == k_exp, f"Encaps k mismatch on {tc}"

            # Decaps
            k_dec = mlkem_decaps(dk_act, c_act, "ML-KEM-1024", idx + 1)
            assert k_dec == k_exp, f"Decaps k mismatch on {tc}"
        else:
            # Decaps (includes paired valid and invalid ciphertexts)
            dk = bytes.fromhex(case["dk"])
            c = bytes.fromhex(case["c"])
            k_exp = bytes.fromhex(case["k"])
            k_dec = mlkem_decaps(dk, c, "ML-KEM-1024", idx + 1)
            assert k_dec == k_exp, f"Decaps k mismatch on {tc}"

        print(f"  [{idx+1:02d}/{len(cases):02d}] {tc:24s}: PASS")
        passed += 1

    print(f"DR8 ML-KEM-1024 Result: {passed}/{len(cases)} PASS\n")
    return passed, len(cases)

def test_dr8_mlkem512_silicon():
    dataset_path = Path(__file__).resolve().parent / "data" / "dr7_nist_acvp_mlkem512_decaps_25.json"
    data = json.loads(dataset_path.read_text())
    cases = data["cases"]
    passed = 0
    print(f"=== DR8 ML-KEM-512 Regression Test ({len(cases)} cases) ===")
    for idx, case in enumerate(cases):
        tc = case.get("tcId") or case.get("tc_id", f"case_{idx+1}")
        is_paired = "dr7_paired" in tc or case.get("is_rejection", False)

        if not is_paired and "d" in case and "m" in case:
            # KeyGen
            d = bytes.fromhex(case["d"])
            z = bytes.fromhex(case["z"])
            ek_exp = bytes.fromhex(case["ek"])
            dk_exp = bytes.fromhex(case["dk"])
            ek_act, dk_act = mlkem_keygen(d, z, "ML-KEM-512", idx + 1)
            assert ek_act == ek_exp, f"KeyGen ek mismatch on {tc}"
            assert dk_act == dk_exp, f"KeyGen dk mismatch on {tc}"

            # Encaps
            m = bytes.fromhex(case["m"])
            c_exp = bytes.fromhex(case["c"])
            k_exp = bytes.fromhex(case["k"])
            c_act, k_act = mlkem_encaps(ek_act, m, "ML-KEM-512", idx + 1)
            assert c_act == c_exp, f"Encaps c mismatch on {tc}"
            assert k_act == k_exp, f"Encaps k mismatch on {tc}"

            # Decaps
            k_dec = mlkem_decaps(dk_act, c_act, "ML-KEM-512", idx + 1)
            assert k_dec == k_exp, f"Decaps k mismatch on {tc}"
        else:
            dk = bytes.fromhex(case["dk"])
            c = bytes.fromhex(case["c"])
            k_exp = bytes.fromhex(case["k"])
            k_dec = mlkem_decaps(dk, c, "ML-KEM-512", idx + 1)
            assert k_dec == k_exp, f"Decaps k mismatch on {tc}"

        print(f"  [{idx+1:02d}/{len(cases):02d}] {tc:24s}: PASS")
        passed += 1

    print(f"DR8 ML-KEM-512 Result: {passed}/{len(cases)} PASS\n")
    return passed, len(cases)

if __name__ == "__main__":
    p512, t512 = test_dr8_mlkem512_silicon()
    p768, t768 = test_dr8_mlkem768_silicon()
    p1024, t1024 = test_dr8_mlkem1024_silicon()
    total_p = p512 + p768 + p1024
    total_t = t512 + t768 + t1024
    print(f"===========================================================")
    print(f"ALL DR8 ML-KEM PARAMETER SETS (512, 768, 1024) PHYSICAL SILICON RESULT:")
    print(f"TOTAL: {total_p}/{total_t} PASS (100% BIT-EXACT MATCH)")
    print(f"===========================================================")
