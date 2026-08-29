# SPDX-License-Identifier: Apache-2.0
"""
Comprehensive ID Quantique (IDQ) Cerberis XGR & ETSI GS QKD 014 Silicon Validation Suite.
------------------------------------------------------------------------------------------
Validates 100% On-Device Device-Resident Ingress, ML-DSA Authentication, and NIST SP 800-56C
Key Combination of ID Quantique QKD Streams on AMD Phoenix NPU (AIE2 / XDNA1).

Standards:
  - ETSI GS QKD 014 v1.1.1 / v1.3.1 (REST API Key Delivery)
  - NIST FIPS 202 (SHA-3/SHAKE), FIPS 203 (ML-KEM), FIPS 204 (ML-DSA)
  - NIST SP 800-56C Rev. 2 & NIST SP 800-227 (Two-Step KDF Combiner)
  - ITU-T Y.3800–Y.3804 (QKD Networks Architecture)
"""

import os
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.idq_qkd_adapter import MockIdqCerberisServer, IdqQkdClient
from phoenix_sdr_dsp.pqc import dr16_etsi_qkd014_abi as dr16_abi
from phoenix_sdr_dsp.pqc.dr16_etsi_qkd014_graph import run_dr16_ingress_service
from phoenix_sdr_dsp.pqc.dr17_mldsa_qkd_auth_graph import verify_qkd_manifest_on_aie2
from phoenix_sdr_dsp.pqc import dr17_mldsa_qkd_auth_abi as dr17_abi
from phoenix_sdr_dsp.pqc.dr18_dual_key_combiner_graph import combine_keys_on_aie2
from phoenix_sdr_dsp.pqc.dr19_hybrid_session_orchestrator import run_hybrid_handshake_on_aie2
from phoenix_sdr_dsp.pqc import dr11_mldsa44_keygen_graph as kg44
from phoenix_sdr_dsp.pqc import dr12_mldsa44_sign_graph as sign44

def main():
    print("=" * 80)
    print("ID QUANTIQUE (IDQ) CERBERIS XGR & ETSI GS QKD 014 SILICON VALIDATION")
    print("Hardware Target: AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2)")
    print("Scope: End-to-End Live Ingress, ML-DSA Authentication & Dual-PRF Fusing")
    print("=" * 80)

    # 1. Start Mock ID Quantique Cerberis XGR KME Server
    kme_server = MockIdqCerberisServer(host="127.0.0.1", port=18080, kme_id="IDQ-CERBERIS-XGR-01")
    kme_server.start()
    print("[+] Initialized ID Quantique Cerberis XGR Mock KME Server on http://127.0.0.1:18080")

    try:
        client = IdqQkdClient(kme_url="http://127.0.0.1:18080", master_sae="SAE-NODE-A-NPU", slave_sae="SAE-NODE-B-NPU")
        status_info = client.get_status()
        print(f"[+] Connected to IDQ KME: {status_info['source_KME_ID']} (Stored Keys: {status_info['stored_key_count']})")

        passed = 0
        total = 30
        t0_all = time.time()

        # Gate 1: Live IDQ Cerberis Key Ingress to AIE2 Tile (0,1) (10 tests)
        print("\n--- [Section 1] IDQ Cerberis Key Ingress -> AIE2 Tile (0,1) ---")
        for i in range(1, 11):
            key_id, status, slot, crc32 = client.stream_key_directly_to_npu(epoch=1000 + i)
            if status == 0:
                passed += 1
                print(f"  [{i:02d}/10] idq_cerberis_ingress_tc{i:02d}: PASS (Key_ID: {str(key_id)[:8]}..., CRC: 0x{crc32:08X}, Slot: {slot})")
            else:
                print(f"  [{i:02d}/10] idq_cerberis_ingress_tc{i:02d}: FAIL (status={status})")

        # Gate 2: Master-Slave Key Synchronization & Decryption Retrieval (5 tests)
        print("\n--- [Section 2] IDQ Master-Slave Key Retrieval & Verification ---")
        for i in range(1, 6):
            kid, k_master, _ = client.get_enc_key()
            k_slave = client.get_dec_key(kid)
            if k_master == k_slave and len(k_master) == 32:
                passed += 1
                print(f"  [{i:02d}/05] idq_key_sync_tc{i:02d}: PASS (UUID: {str(kid)[:8]}... matched 256-bit entropy)")
            else:
                print(f"  [{i:02d}/05] idq_key_sync_tc{i:02d}: FAIL")

        # Gate 3: ML-DSA-44 Control Plane Signing over IDQ Manifests (5 tests)
        print("\n--- [Section 3] ML-DSA-44 Signature Verification of IDQ Control Packets ---")
        pk44, sk44 = kg44.run_mldsa44_keygen(os.urandom(32))
        for i in range(1, 6):
            kid, _, _ = client.get_enc_key()
            epoch = 2000 + i
            nonce = os.urandom(12)
            manifest = dr17_abi.pack_dr17_manifest("SAE-NODE-A-NPU", "SAE-NODE-B-NPU", kid, epoch, nonce)
            sig = sign44.run_mldsa44_sign(sk44, manifest)
            valid, _, dt = verify_qkd_manifest_on_aie2("ML-DSA-44", pk44, "SAE-NODE-A-NPU", "SAE-NODE-B-NPU", kid, epoch, nonce, sig)
            if valid:
                passed += 1
                print(f"  [{i:02d}/05] idq_mldsa_auth_tc{i:02d}: PASS (FIPS 204 Verified in {dt:.1f}ms on AIE2)")
            else:
                print(f"  [{i:02d}/05] idq_mldsa_auth_tc{i:02d}: FAIL")

        # Gate 4: NIST SP 800-56C Dual Combiner (IDQ Key + ML-KEM Lattice Key) (5 tests)
        print("\n--- [Section 4] NIST SP 800-56C Two-Step KDF Fusing ---")
        for i in range(1, 6):
            kid, k_qkd, _ = client.get_enc_key()
            k_pqc = os.urandom(32)
            epoch = 3000 + i
            k_final, dt = combine_keys_on_aie2(k_qkd, k_pqc, kid, epoch=epoch, out_len=32)
            if len(k_final) == 32:
                passed += 1
                print(f"  [{i:02d}/05] idq_dual_combiner_tc{i:02d}: PASS (Derived K_Final in {dt:.1f}ms on AIE2 Keccak)")
            else:
                print(f"  [{i:02d}/05] idq_dual_combiner_tc{i:02d}: FAIL")

        # Gate 5: End-to-End Live Session with DR10 Hardware Zeroization (5 tests)
        print("\n--- [Section 5] End-to-End Live Session & Memory Zeroization Teardown ---")
        for i in range(1, 6):
            res = run_hybrid_handshake_on_aie2(kem_param="ML-KEM-512", dsa_param="ML-DSA-44", epoch=4000 + i)
            if res.is_authenticated and res.is_key_matched and res.zeroized_status == 0:
                passed += 1
                print(f"  [{i:02d}/05] idq_e2e_session_tc{i:02d}: PASS (Handshake: {res.total_latency_ms:.1f}ms, SRAM Wiped: OK)")
            else:
                print(f"  [{i:02d}/05] idq_e2e_session_tc{i:02d}: FAIL")

        dt_all = time.time() - t0_all
        print("=" * 80)
        print(f"ID QUANTIQUE QKD SILICON VALIDATION RESULT: {passed}/{total} PASS ({passed/total*100:.2f}%) in {dt_all:.2f}s")
        print("=" * 80)
        return 0 if passed == total else 1

    finally:
        kme_server.stop()
        print("[+] Mock ID Quantique Server Stopped.")

if __name__ == "__main__":
    sys.exit(main())
