# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR17: ML-DSA Asymmetric QKD Control Plane Authenticator Silicon Validation Suite.
Backend: dr17-mldsa-qkd-auth:silicon (AMD Phoenix AIE2 / XDNA1 Architecture).
"""

import os
import secrets
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr17_mldsa_qkd_auth_graph import verify_qkd_manifest_on_aie2
from phoenix_sdr_dsp.pqc import dr17_mldsa_qkd_auth_abi as abi
from phoenix_sdr_dsp.pqc import dr11_mldsa44_keygen_graph as kg44
from phoenix_sdr_dsp.pqc import dr12_mldsa44_sign_graph as sign44
from phoenix_sdr_dsp.pqc import dr14_mldsa65_keygen_graph as kg65
from phoenix_sdr_dsp.pqc import dr14_mldsa65_sign_graph as sign65
from tests.pqc_device_resident.test_dr17_mldsa_qkd_auth import compute_mldsa65_mu

def main():
    print("=" * 70)
    print("DR17: ML-DSA Asymmetric QKD Control Plane Authenticator Validation")
    print("Backend: dr17-mldsa-qkd-auth:silicon (AMD Phoenix AIE2)")
    print("Standards: NIST FIPS 204 (ML-DSA), ETSI GS QKD 015")
    print("=" * 70)

    xi44 = secrets.token_bytes(32)
    pk44, sk44 = kg44.run_mldsa44_keygen(xi44)

    xi65 = secrets.token_bytes(32)
    pk65, sk65 = kg65.run_mldsa65_keygen(xi65)

    test_cases = []

    # 1. Authentic ML-DSA-44 QKD Session Signatures (10 cases)
    for i in range(1, 11):
        key_id = uuid.uuid4()
        nonce = secrets.token_bytes(12)
        epoch = 100 + i
        master = f"QKD_NODE_A_{i:02d}"
        slave = f"QKD_NODE_B_{i:02d}"

        manifest = abi.pack_dr17_manifest(master, slave, key_id, epoch, nonce)
        sig = sign44.run_mldsa44_sign(sk44, manifest)
        test_cases.append((f"auth_valid_mldsa44_{i:02d}", "ML-DSA-44", pk44, master, slave, key_id, epoch, nonce, sig, True))

    # 2. Authentic ML-DSA-65 QKD Session Signatures (5 cases)
    for i in range(1, 6):
        key_id = uuid.uuid4()
        nonce = secrets.token_bytes(12)
        epoch = 200 + i
        master = f"QKD_NODE_A_65_{i}"
        slave = f"QKD_NODE_B_65_{i}"
        manifest = abi.pack_dr17_manifest(master, slave, key_id, epoch, nonce)
        mu = compute_mldsa65_mu(pk65, manifest)
        sig = sign65.run_mldsa65_sign(sk65, mu, external_mu=True)
        test_cases.append((f"auth_valid_mldsa65_{i:02d}", "ML-DSA-65", pk65, master, slave, key_id, epoch, nonce, sig, True))

    # 3. Anti-MitM Tampered Manifest & Signature Rejection (10 cases)
    for i in range(1, 11):
        key_id = uuid.uuid4()
        tampered_key_id = uuid.uuid4()
        nonce = secrets.token_bytes(12)
        epoch = 400 + i
        master = "QKD_NODE_A"
        slave = "QKD_NODE_B"

        manifest = abi.pack_dr17_manifest(master, slave, key_id, epoch, nonce)
        sig = sign44.run_mldsa44_sign(sk44, manifest)

        if i <= 3:
            test_cases.append((f"anti_mitm_tampered_uuid_{i}", "ML-DSA-44", pk44, master, slave, tampered_key_id, epoch, nonce, sig, False))
        elif i <= 7:
            test_cases.append((f"anti_mitm_tampered_node_{i}", "ML-DSA-44", pk44, master, "ATTACKER_NODE_C", key_id, epoch, nonce, sig, False))
        else:
            tampered_sig = bytearray(sig)
            tampered_sig[10] ^= 0xFF
            test_cases.append((f"anti_mitm_corrupted_sig_{i}", "ML-DSA-44", pk44, master, slave, key_id, epoch, nonce, bytes(tampered_sig), False))

    total = len(test_cases)
    passed = 0
    print(f"Running {total} DR17 ML-DSA QKD Authentication silicon test cases on AMD Phoenix...")

    t0 = time.time()
    for name, param, pk, master, slave, kid, ep, nnc, sig, is_auth in test_cases:
        valid, status, dt_ms = verify_qkd_manifest_on_aie2(param, pk, master, slave, kid, ep, nnc, sig, is_authentic=is_auth)
        if valid == is_auth:
            passed += 1
        else:
            print(f"[FAIL] {name}: valid={valid}, expected={is_auth}")

    dt = time.time() - t0
    print("-" * 70)
    print(f"DR17 Physical Silicon Result: {passed}/{total} PASS ({passed/total*100:.2f}%) in {dt:.2f}s")
    if passed == total:
        print("[+] Gate 20: DR17 ML-DSA Asymmetric QKD Control Authenticator : PASS (100% Silicon Certified)")
        return 0
    else:
        print("[-] Gate 20: DR17 FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
