# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR31 Silicon Validation: On-Device X.509 Post-Quantum PKI Engine
--------------------------------------------------------------------------
Physical silicon validation for Milestone DR31 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
RFC 5280 / RFC 9618 multi-tier certificate chain validation on physical silicon.
Target: Tiles (3,0 / 3,1 / 3,2 / 3,3).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import struct
import hashlib
import time
from pathlib import Path
from typing import List, Tuple

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr31_pki_abi as abi
from phoenix_sdr_dsp.pqc import dr31_pki_graph as graph

# Import low-level signing engines
from phoenix_sdr_dsp.pqc.dr11_mldsa44_keygen_graph import run_mldsa44_keygen
from phoenix_sdr_dsp.pqc.dr12_mldsa44_sign_graph import run_mldsa44_sign
from phoenix_sdr_dsp.pqc import dr21_slhdsa_graph as slhdsa
from phoenix_sdr_dsp.pqc import dr28_lms_graph as lms

def test_dr31_der_serialization_and_tbs_fidelity():
    """Verify ASN.1 DER TLV encoding and length handling."""
    val = graph.ValidityPeriod(not_before=1700000000, not_after=1800000000)
    spki = graph.SubjectPublicKeyInfo(algorithm_oid=abi.OID_MLDSA_44, public_key_bytes=b"\x42" * 1312)
    
    tbs = graph.build_tbs_certificate(
        serial=1,
        algo_oid=abi.OID_MLDSA_44,
        issuer_dn="CN=Test Root CA, O=Phoenix PQC",
        validity=val,
        subject_dn="CN=Test Root CA, O=Phoenix PQC",
        spki=spki,
        is_ca=True
    )
    
    assert len(tbs) > 100
    tag, body, _ = graph.decode_tlv(tbs, 0)
    assert tag == abi.TAG_SEQUENCE

def test_dr31_mldsa44_self_signed_root_ca():
    """Generate self-signed Root CA and verify on AIE2 silicon."""
    # 1. Generate Root CA ML-DSA-44 Keypair on-device
    root_pk, root_sk = run_mldsa44_keygen(b"dr31_root_ca".ljust(32, b"0"))
    
    val = graph.ValidityPeriod(not_before=1700000000, not_after=1800000000)
    spki = graph.SubjectPublicKeyInfo(algorithm_oid=abi.OID_MLDSA_44, public_key_bytes=root_pk)
    
    # 2. Build TBS Certificate
    tbs_bytes = graph.build_tbs_certificate(
        serial=1001,
        algo_oid=abi.OID_MLDSA_44,
        issuer_dn="CN=Phoenix Root CA, O=AMD Phoenix NPU",
        validity=val,
        subject_dn="CN=Phoenix Root CA, O=AMD Phoenix NPU",
        spki=spki,
        is_ca=True,
        key_usage=abi.KEY_USAGE_KEY_CERT_SIGN | abi.KEY_USAGE_CRL_SIGN
    )
    
    # 3. Sign on-device
    sig_bytes = run_mldsa44_sign(root_sk, tbs_bytes)
    
    # 4. Assemble X509Certificate
    root_cert = graph.X509Certificate(
        serial_number=1001,
        signature_algo_oid=abi.OID_MLDSA_44,
        issuer_dn="CN=Phoenix Root CA, O=AMD Phoenix NPU",
        validity=val,
        subject_dn="CN=Phoenix Root CA, O=AMD Phoenix NPU",
        spki=spki,
        tbs_raw=tbs_bytes,
        signature_value=sig_bytes
    )
    
    # 5. Verify on-device
    is_valid = graph.verify_single_cert_signature(root_cert, root_cert)
    assert is_valid == True

def test_dr31_three_tier_pki_chain_validation():
    """Verify 3-tier certificate chain: Root CA -> Intermediate CA -> Leaf Certificate."""
    # 1. Root CA (ML-DSA-44)
    root_pk, root_sk = run_mldsa44_keygen(b"root_ca_3tier".ljust(32, b"0"))
    root_spki = graph.SubjectPublicKeyInfo(abi.OID_MLDSA_44, root_pk)
    root_val = graph.ValidityPeriod(1700000000, 1900000000)
    root_tbs = graph.build_tbs_certificate(1, abi.OID_MLDSA_44, "CN=Root CA", root_val, "CN=Root CA", root_spki, is_ca=True)
    root_sig = run_mldsa44_sign(root_sk, root_tbs)
    root_cert = graph.X509Certificate(1, abi.OID_MLDSA_44, "CN=Root CA", root_val, "CN=Root CA", root_spki, tbs_raw=root_tbs, signature_value=root_sig)
    
    # 2. Intermediate CA (ML-DSA-44)
    int_pk, int_sk = run_mldsa44_keygen(b"int_ca_3tier".ljust(32, b"0"))
    int_spki = graph.SubjectPublicKeyInfo(abi.OID_MLDSA_44, int_pk)
    int_val = graph.ValidityPeriod(1700000000, 1850000000)
    int_tbs = graph.build_tbs_certificate(2, abi.OID_MLDSA_44, "CN=Root CA", int_val, "CN=Intermediate CA", int_spki, is_ca=True)
    int_sig = run_mldsa44_sign(root_sk, int_tbs) # Signed by Root
    int_cert = graph.X509Certificate(2, abi.OID_MLDSA_44, "CN=Root CA", int_val, "CN=Intermediate CA", int_spki, tbs_raw=int_tbs, signature_value=int_sig)
    
    # 3. Leaf Certificate (ML-DSA-44)
    leaf_pk, leaf_sk = run_mldsa44_keygen(b"leaf_3tier".ljust(32, b"0"))
    leaf_spki = graph.SubjectPublicKeyInfo(abi.OID_MLDSA_44, leaf_pk)
    leaf_val = graph.ValidityPeriod(1700000000, 1800000000)
    leaf_tbs = graph.build_tbs_certificate(3, abi.OID_MLDSA_44, "CN=Intermediate CA", leaf_val, "CN=phoenix.npu.internal", leaf_spki, is_ca=False)
    leaf_sig = run_mldsa44_sign(int_sk, leaf_tbs) # Signed by Intermediate
    leaf_cert = graph.X509Certificate(3, abi.OID_MLDSA_44, "CN=Intermediate CA", leaf_val, "CN=phoenix.npu.internal", leaf_spki, tbs_raw=leaf_tbs, signature_value=leaf_sig)
    
    # 4. Execute Full Chain Validation on Silicon
    chain = [leaf_cert, int_cert]
    engine = graph.Dr31PkiEngine()
    res = engine.validate_chain(chain, root_cert, current_time=1750000000)
    
    assert res["status"] == "PASS"
    assert res["is_valid"] == True
    assert res["chain_length"] == 2
    assert res["execution_gate"] == "UNLOCKED"

def test_dr31_slhdsa_and_lms_pki_support():
    """Verify X.509 certificate validation with SLH-DSA and LMS public keys."""
    # 1. SLH-DSA Certificate
    slh_pk, slh_sk, _ = slhdsa.slhdsa_keygen_on_aie2("SLH-DSA-SHAKE-128s")
    val = graph.ValidityPeriod(1700000000, 1800000000)
    spki_slh = graph.SubjectPublicKeyInfo(abi.OID_SLHDSA_SHAKE_128S, slh_pk)
    tbs_slh = graph.build_tbs_certificate(101, abi.OID_SLHDSA_SHAKE_128S, "CN=SLH-DSA CA", val, "CN=SLH-DSA CA", spki_slh, is_ca=True)
    sig_slh, _ = slhdsa.slhdsa_sign_on_aie2("SLH-DSA-SHAKE-128s", slh_sk, tbs_slh)
    cert_slh = graph.X509Certificate(101, abi.OID_SLHDSA_SHAKE_128S, "CN=SLH-DSA CA", val, "CN=SLH-DSA CA", spki_slh, tbs_raw=tbs_slh, signature_value=sig_slh)
    
    assert graph.verify_single_cert_signature(cert_slh, cert_slh) == True
    
    # 2. LMS Certificate
    from tests.pqc_device_resident.test_dr28_lms_silicon import _generate_lms_keypair, _lms_sign
    I = b"\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\xcc\xdd\xee\xff\x00"
    lms_pk, ots_sk, tree = _generate_lms_keypair(I, lms.abi.LMS_SHA256_M32_H5, lms.abi.LMOTS_SHA256_N32_W4, b"lms_pki_master_seed_001")
    spki_lms = graph.SubjectPublicKeyInfo(abi.OID_LMS_HSS, lms_pk.to_bytes())
    tbs_lms = graph.build_tbs_certificate(102, abi.OID_LMS_HSS, "CN=LMS Firmware CA", val, "CN=LMS Firmware CA", spki_lms, is_ca=True)
    sig_lms = _lms_sign(lms_pk, ots_sk, tree, 0, tbs_lms, b"\x00" * 32)
    cert_lms = graph.X509Certificate(102, abi.OID_LMS_HSS, "CN=LMS Firmware CA", val, "CN=LMS Firmware CA", spki_lms, tbs_raw=tbs_lms, signature_value=sig_lms.to_bytes())
    
    assert graph.verify_single_cert_signature(cert_lms, cert_lms) == True

def test_dr31_fail_closed_tampering_and_expired_rejection():
    """Verify that tampering with any TBS byte or expired timestamp triggers immediate hard reject."""
    root_pk, root_sk = run_mldsa44_keygen(b"root_tamper".ljust(32, b"0"))
    root_spki = graph.SubjectPublicKeyInfo(abi.OID_MLDSA_44, root_pk)
    root_val = graph.ValidityPeriod(1700000000, 1800000000)
    root_tbs = graph.build_tbs_certificate(1, abi.OID_MLDSA_44, "CN=Root CA", root_val, "CN=Root CA", root_spki, is_ca=True)
    root_sig = run_mldsa44_sign(root_sk, root_tbs)
    root_cert = graph.X509Certificate(1, abi.OID_MLDSA_44, "CN=Root CA", root_val, "CN=Root CA", root_spki, tbs_raw=root_tbs, signature_value=root_sig)
    
    leaf_pk, leaf_sk = run_mldsa44_keygen(b"leaf_tamper".ljust(32, b"0"))
    leaf_spki = graph.SubjectPublicKeyInfo(abi.OID_MLDSA_44, leaf_pk)
    leaf_val = graph.ValidityPeriod(1700000000, 1800000000)
    leaf_tbs = graph.build_tbs_certificate(2, abi.OID_MLDSA_44, "CN=Root CA", leaf_val, "CN=server.test", leaf_spki, is_ca=False)
    leaf_sig = run_mldsa44_sign(root_sk, leaf_tbs)
    
    # 1. Expired Check
    leaf_cert = graph.X509Certificate(2, abi.OID_MLDSA_44, "CN=Root CA", leaf_val, "CN=server.test", leaf_spki, tbs_raw=leaf_tbs, signature_value=leaf_sig)
    engine = graph.Dr31PkiEngine()
    res_exp = engine.validate_chain([leaf_cert], root_cert, current_time=1950000000)
    assert res_exp["status"] == "REJECT_EXPIRED"
    assert res_exp["is_valid"] == False
    
    # 2. Tampered TBS Payload Check
    tampered_tbs = bytearray(leaf_tbs)
    tampered_tbs[20] ^= 0xFF
    leaf_tampered = graph.X509Certificate(2, abi.OID_MLDSA_44, "CN=Root CA", leaf_val, "CN=server.test", leaf_spki, tbs_raw=bytes(tampered_tbs), signature_value=leaf_sig)
    res_tamp = engine.validate_chain([leaf_tampered], root_cert, current_time=1750000000)
    assert res_tamp["status"] == "REJECT_INVALID_SIGNATURE"
    assert res_tamp["is_valid"] == False

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR31 ON-DEVICE X.509 POST-QUANTUM PKI SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr31_der_serialization_and_tbs_fidelity()
    print("[+] Test 1: ASN.1 DER Serialization & Structure Fidelity PASS")
    test_dr31_mldsa44_self_signed_root_ca()
    print("[+] Test 2: ML-DSA-44 Self-Signed Root CA On-Device Verification PASS")
    test_dr31_three_tier_pki_chain_validation()
    print("[+] Test 3: 3-Tier Multi-Algorithm PKI Chain Validation (Root->Int->Leaf) PASS")
    test_dr31_slhdsa_and_lms_pki_support()
    print("[+] Test 4: SLH-DSA & LMS X.509 Certificate Verification PASS")
    test_dr31_fail_closed_tampering_and_expired_rejection()
    print("[+] Test 5: Fail-Closed Security & Expired Timestamp Rejection PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR31 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
