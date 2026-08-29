# SPDX-License-Identifier: Apache-2.0
"""
Device-Resident Silicon Test Suite: Milestone DR32.
Post-Quantum X.509 PKI Certificate Authority & TLS 1.3 Handshake on AMD Phoenix AIE2.

Standards & Resource Citations:
1. ITU-T X.509 (10/2019) / IETF RFC 5280: Public-Key Infrastructure Certificate Profile.
2. IETF RFC 8446: The Transport Layer Security (TLS) Protocol Version 1.3.
3. IETF RFC 9370: Multiple Key Encapsulation Mechanisms (KEMs) in TLS 1.3.
4. NIST FIPS 203 (ML-KEM), NIST FIPS 204 (ML-DSA), NIST FIPS 205 (SLH-DSA).
5. ETSI GS QKD 014 v1.1.1 & NIST SP 800-56C Rev. 2 (Hybrid Dual Combiner).
6. DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from phoenix_sdr_dsp.pqc import dr32_pki_tls_abi as pki

class TestDR32PkiTlsSilicon(unittest.TestCase):

    def test_01_generate_root_ca_mldsa65(self):
        """Validates Root CA certificate generation using ML-DSA-65 on AIE2."""
        ca = pki.generate_pq_x509_certificate("Phoenix Sovereign Root CA", algorithm="ML-DSA-65", is_ca=True)
        self.assertEqual(ca["subject"], "Phoenix Sovereign Root CA")
        self.assertEqual(ca["issuer"], "Phoenix Sovereign Root CA")
        self.assertTrue(ca["is_ca"])
        self.assertTrue(ca["pem"].startswith("-----BEGIN CERTIFICATE-----"))
        self.assertTrue(ca["pem"].endswith("-----END CERTIFICATE-----"))
        self.assertTrue(ca["hardware_certified"])

    def test_02_issue_intermediate_and_leaf_certificates(self):
        """Validates 3-tier PKI certificate hierarchy (Root CA -> Intermediate CA -> Server Leaf)."""
        root_ca = pki.generate_pq_x509_certificate("Root CA Level 5", algorithm="ML-DSA-87", is_ca=True)
        int_ca = pki.generate_pq_x509_certificate(
            "Regional Enterprise Intermediate CA",
            algorithm="ML-DSA-65",
            is_ca=True,
            issuer_cert=root_ca,
            issuer_sk_hex=root_ca["secret_key_hex"]
        )
        self.assertEqual(int_ca["issuer"], "Root CA Level 5")

        leaf = pki.generate_pq_x509_certificate(
            "api.sovereign.bank.internal",
            algorithm="ML-DSA-44",
            is_ca=False,
            issuer_cert=int_ca,
            issuer_sk_hex=int_ca["secret_key_hex"],
            san_list=["api.sovereign.bank.internal", "gateway.bank.internal"]
        )
        self.assertEqual(leaf["issuer"], "Regional Enterprise Intermediate CA")
        self.assertFalse(leaf["is_ca"])
        self.assertIn("api.sovereign.bank.internal", leaf["san"])

    def test_03_tls13_quantum_safe_handshake_standard(self):
        """Validates RFC 8446 TLS 1.3 Key Exchange with ML-KEM-768 and ML-DSA-65."""
        tls = pki.simulate_tls13_pq_handshake("gateway.enterprise.internal", kem_group="MLKEM768", sig_algorithm="ML-DSA-65", qkd_enabled=False)
        self.assertEqual(tls["status"], "HANDSHAKE_ESTABLISHED")
        self.assertEqual(len(tls["handshake_steps"]), 5)
        self.assertIsNotNone(tls["secrets"]["client_application_traffic_secret_0"])
        self.assertIsNotNone(tls["secrets"]["server_application_traffic_secret_0"])
        self.assertTrue(tls["zero_host_fallback"])

    def test_04_tls13_hybrid_qkd_dual_combiner_handshake(self):
        """Validates RFC 9370 Hybrid QKD-PQC TLS 1.3 Handshake using NIST SP 800-56C Dual Combiner."""
        tls = pki.simulate_tls13_pq_handshake("defense.secure.node", kem_group="X25519MLKEM768", sig_algorithm="ML-DSA-87", qkd_enabled=True)
        self.assertEqual(tls["status"], "HANDSHAKE_ESTABLISHED")
        self.assertTrue(tls["qkd_hybrid_enabled"])
        self.assertIsNotNone(tls["qkd_key_id"])
        self.assertEqual(len(tls["secrets"]["final_hybrid_key"]), 64) # 32 bytes hex
        self.assertTrue(tls["zero_host_fallback"])

if __name__ == "__main__":
    unittest.main()
