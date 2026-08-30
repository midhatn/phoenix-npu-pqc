# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR37 Silicon Validation: ETSI TS 103 744 & BSI TR-02102-1 Hybrid KEM Engine
-------------------------------------------------------------------------------------
Physical silicon validation for Milestone DR37 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Dual-Scheme Hybrid Key Encapsulation (X25519MLKEM768 & SecP384R1MLKEM1024).
Target: Tiles (1,2), (2,0..2,3), (3,2).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
import hashlib
from pathlib import Path

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr37_hybrid_kem_abi as abi
from phoenix_sdr_dsp.pqc import dr37_hybrid_kem_graph as graph

def test_dr37_x25519_mlkem768_keygen_silicon():
    """Verify X25519MLKEM768 Dual KeyPair Generation on AIE2 Hardware."""
    seed = hashlib.sha256(b"ALICE_KEYGEN_SEED_001").digest()
    kp = graph.run_dr37_hybrid_kem_keygen(abi.PROFILE_X25519_MLKEM768, seed)
    
    assert len(kp.classical_pk) == 32
    assert len(kp.classical_sk) == 32
    assert len(kp.pqc_pk) == 1184
    assert len(kp.pqc_sk) == 2400
    assert len(kp.public_key_bytes()) == 1216

def test_dr37_x25519_mlkem768_encaps_decaps_agreement():
    """Verify X25519MLKEM768 Encapsulation, Decapsulation, and Exact Shared Secret Agreement."""
    alice_seed = hashlib.sha256(b"ALICE_HYBRID_KEY_PAIR_002").digest()
    alice_kp = graph.run_dr37_hybrid_kem_keygen(abi.PROFILE_X25519_MLKEM768, alice_seed)
    
    bob_eph = hashlib.sha256(b"BOB_EPHEMERAL_SEED_002").digest()
    bob_ct, bob_ss = graph.run_dr37_hybrid_kem_encaps(alice_kp, bob_eph)
    
    assert len(bob_ct.classical_ct) == 32
    assert len(bob_ct.pqc_ct) == 1088
    assert len(bob_ct.to_bytes()) == 1120
    assert len(bob_ss.shared_secret) == 32
    
    alice_ss = graph.run_dr37_hybrid_kem_decaps(alice_kp, bob_ct)
    assert len(alice_ss.shared_secret) == 32
    assert alice_ss.shared_secret == bob_ss.shared_secret

def test_dr37_secp384r1_mlkem1024_cnsa_agreement():
    """Verify SecP384R1MLKEM1024 CNSA 2.0 / BSI High-Assurance Hybrid Agreement."""
    alice_seed = hashlib.sha256(b"ALICE_CNSA_HIGH_ASSURANCE_003").digest()
    alice_kp = graph.run_dr37_hybrid_kem_keygen(abi.PROFILE_SECP384R1_MLKEM1024, alice_seed)
    
    bob_eph = hashlib.sha256(b"BOB_CNSA_EPHEMERAL_003").digest()
    bob_ct, bob_ss = graph.run_dr37_hybrid_kem_encaps(alice_kp, bob_eph)
    
    alice_ss = graph.run_dr37_hybrid_kem_decaps(alice_kp, bob_ct)
    assert alice_ss.shared_secret == bob_ss.shared_secret

def test_dr37_classical_tamper_rejection():
    """Verify Classical Ciphertext Tamper Rejection & Secret Disagreement."""
    alice_seed = hashlib.sha256(b"ALICE_TAMPER_TEST_004").digest()
    alice_kp = graph.run_dr37_hybrid_kem_keygen(abi.PROFILE_X25519_MLKEM768, alice_seed)
    
    bob_eph = hashlib.sha256(b"BOB_TAMPER_TEST_004").digest()
    bob_ct, bob_ss = graph.run_dr37_hybrid_kem_encaps(alice_kp, bob_eph)
    
    # Tamper 1 byte of classical ciphertext
    tampered_c_ct = bytearray(bob_ct.classical_ct)
    tampered_c_ct[0] ^= 0xFF
    tampered_ct = abi.HybridCiphertext(
        profile_id=bob_ct.profile_id,
        classical_ct=bytes(tampered_c_ct),
        pqc_ct=bob_ct.pqc_ct
    )
    
    alice_ss = graph.run_dr37_hybrid_kem_decaps(alice_kp, tampered_ct)
    assert alice_ss.shared_secret != bob_ss.shared_secret

def test_dr37_pqc_tamper_rejection():
    """Verify Post-Quantum Ciphertext Tamper Rejection & ML-KEM Implicit Rejection."""
    alice_seed = hashlib.sha256(b"ALICE_TAMPER_TEST_005").digest()
    alice_kp = graph.run_dr37_hybrid_kem_keygen(abi.PROFILE_X25519_MLKEM768, alice_seed)
    
    bob_eph = hashlib.sha256(b"BOB_TAMPER_TEST_005").digest()
    bob_ct, bob_ss = graph.run_dr37_hybrid_kem_encaps(alice_kp, bob_eph)
    
    # Tamper 1 byte of ML-KEM ciphertext
    tampered_pqc_ct = bytearray(bob_ct.pqc_ct)
    tampered_pqc_ct[10] ^= 0xAA
    tampered_ct = abi.HybridCiphertext(
        profile_id=bob_ct.profile_id,
        classical_ct=bob_ct.classical_ct,
        pqc_ct=bytes(tampered_pqc_ct)
    )
    
    alice_ss = graph.run_dr37_hybrid_kem_decaps(alice_kp, tampered_ct)
    assert alice_ss.shared_secret != bob_ss.shared_secret

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR37 ETSI TS 103 744 & BSI TR-02102-1 HYBRID KEM SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr37_x25519_mlkem768_keygen_silicon()
    print("[+] Test 1: X25519MLKEM768 Dual KeyPair Generation on Silicon PASS")
    test_dr37_x25519_mlkem768_encaps_decaps_agreement()
    print("[+] Test 2: X25519MLKEM768 Encapsulation, Decapsulation & Exact Agreement PASS")
    test_dr37_secp384r1_mlkem1024_cnsa_agreement()
    print("[+] Test 3: SecP384R1MLKEM1024 CNSA 2.0 / BSI High-Assurance Agreement PASS")
    test_dr37_classical_tamper_rejection()
    print("[+] Test 4: Classical Ciphertext Tamper Rejection & Secret Disagreement PASS")
    test_dr37_pqc_tamper_rejection()
    print("[+] Test 5: Post-Quantum Ciphertext Tamper Rejection & Implicit Rejection PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR37 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
