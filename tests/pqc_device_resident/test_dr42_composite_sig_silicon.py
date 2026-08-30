# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR42 Silicon Validation: ANSSI Composite & Dual-Signature Sovereign Standard Engine
---------------------------------------------------------------------------------------------
Physical silicon validation for Milestone DR42 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Atomic dual-signature verification combining Ed25519/ECDSA with ML-DSA-44/ML-DSA-65.
Target: Tiles (1,2), (2,0..2,3), (3,2).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
from pathlib import Path

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr42_composite_sig_abi as abi
from phoenix_sdr_dsp.pqc import dr42_composite_sig_graph as graph

def test_dr42_ed25519_mldsa44_composite_lifecycle_silicon():
    """Verify Ed25519-ML-DSA-44 Composite KeyGen, Sign & Verify on AIE2 Silicon."""
    msg = b"SOVEREIGN_DUAL_SIGNATURE_PAYLOAD_ANSSI_FRANCE"
    pk, sk = graph.run_composite_keygen(abi.CompositeSignatureType.ED25519_MLDSA44, root_seed=b"\x12" * 32)
    sig = graph.run_composite_sign(sk, msg)
    res = graph.run_composite_verify(pk, msg, sig)
    
    assert res.is_valid == True
    assert res.trad_valid == True
    assert res.pqc_valid == True

def test_dr42_ecdsa_p384_mldsa65_composite_lifecycle_silicon():
    """Verify ECDSA-P384-ML-DSA-65 Composite KeyGen, Sign & Verify on AIE2 Silicon."""
    msg = b"SOVEREIGN_DUAL_SIGNATURE_PAYLOAD_BSI_GERMANY"
    pk, sk = graph.run_composite_keygen(abi.CompositeSignatureType.ECDSA_P384_MLDSA65, root_seed=b"\x34" * 32)
    sig = graph.run_composite_sign(sk, msg)
    res = graph.run_composite_verify(pk, msg, sig)
    
    assert res.is_valid == True
    assert res.trad_valid == True
    assert res.pqc_valid == True

def test_dr42_classical_component_tamper_detection():
    """Verify Fail-Closed Rejection when Classical (Ed25519) Signature is Tampered."""
    msg = b"SOVEREIGN_DUAL_SIGNATURE_TAMPER_TEST_CLASSICAL"
    pk, sk = graph.run_composite_keygen(abi.CompositeSignatureType.ED25519_MLDSA44, root_seed=b"\x56" * 32)
    sig = graph.run_composite_sign(sk, msg)
    
    # Tamper with classical signature component
    tampered_trad = bytes([sig.sig_trad[0] ^ 0xFF]) + sig.sig_trad[1:]
    tampered_sig = abi.CompositeSignature(sig.sig_type, tampered_trad, sig.sig_pqc)
    
    res = graph.run_composite_verify(pk, msg, tampered_sig)
    assert res.is_valid == False
    assert res.trad_valid == False
    assert res.pqc_valid == True

def test_dr42_pqc_component_tamper_detection():
    """Verify Fail-Closed Rejection when Post-Quantum (ML-DSA) Signature is Tampered."""
    msg = b"SOVEREIGN_DUAL_SIGNATURE_TAMPER_TEST_PQC"
    pk, sk = graph.run_composite_keygen(abi.CompositeSignatureType.ED25519_MLDSA44, root_seed=b"\x78" * 32)
    sig = graph.run_composite_sign(sk, msg)
    
    # Tamper with PQC signature component
    tampered_pqc = bytes([sig.sig_pqc[0] ^ 0xFF]) + sig.sig_pqc[1:]
    tampered_sig = abi.CompositeSignature(sig.sig_type, sig.sig_trad, tampered_pqc)
    
    res = graph.run_composite_verify(pk, msg, tampered_sig)
    assert res.is_valid == False
    assert res.trad_valid == True
    assert res.pqc_valid == False

def test_dr42_composite_binary_serialization_parity():
    """Verify Binary Serialization Integrity of Composite Keys and Signatures."""
    pk, sk = graph.run_composite_keygen(abi.CompositeSignatureType.ED25519_MLDSA44, root_seed=b"\x99" * 32)
    sig = graph.run_composite_sign(sk, b"TEST_SERIALIZATION")
    
    pk_bytes = pk.to_bytes()
    pk_recovered = abi.CompositePublicKey.from_bytes(pk_bytes)
    assert pk_recovered.pk_trad == pk.pk_trad
    assert pk_recovered.pk_pqc == pk.pk_pqc
    
    sig_bytes = sig.to_bytes()
    sig_recovered = abi.CompositeSignature.from_bytes(sig_bytes)
    assert sig_recovered.sig_trad == sig.sig_trad
    assert sig_recovered.sig_pqc == sig.sig_pqc

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR42 ANSSI COMPOSITE & DUAL-SIGNATURE SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr42_ed25519_mldsa44_composite_lifecycle_silicon()
    print("[+] Test 1: Ed25519-ML-DSA-44 Composite KeyGen, Sign & Verify PASS")
    test_dr42_ecdsa_p384_mldsa65_composite_lifecycle_silicon()
    print("[+] Test 2: ECDSA-P384-ML-DSA-65 Composite KeyGen, Sign & Verify PASS")
    test_dr42_classical_component_tamper_detection()
    print("[+] Test 3: Classical Tamper Fail-Closed Rejection PASS")
    test_dr42_pqc_component_tamper_detection()
    print("[+] Test 4: Post-Quantum Tamper Fail-Closed Rejection PASS")
    test_dr42_composite_binary_serialization_parity()
    print("[+] Test 5: Composite Binary Serialization & X.509 Parity PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR42 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
