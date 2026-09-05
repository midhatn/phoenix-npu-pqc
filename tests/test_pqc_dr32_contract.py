# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR32:
Post-Quantum X.509 PKI & TLS 1.3 Handshake Formatting Utility [HOST FORMATTER].
"""

import unittest

from phoenix_sdr_dsp.pqc.dr32_pki_tls_abi import (
    BACKEND_LABEL,
    OID_ML_DSA_44,
    OID_ML_DSA_65,
    OID_ML_DSA_87,
    OID_SLH_DSA_SHAKE_128S,
    OID_ML_KEM_768,
    OID_X25519_ML_KEM_768,
    generate_pq_x509_certificate,
    simulate_tls13_pq_handshake,
)


class DR32X509TlsFormatterContractTests(unittest.TestCase):

    def test_01_backend_label(self):
        """Validates truthful [HOST FORMATTER] execution boundary label."""
        self.assertEqual(BACKEND_LABEL, "[HOST FORMATTER]")

    def test_02_certificate_generation_and_pem_formatting(self):
        """Validates X.509 certificate packaging, TBS generation, and PEM structure."""
        cert = generate_pq_x509_certificate(
            subject_cn="gateway.sovereign.local",
            algorithm="ML-DSA-65",
            is_ca=True,
            validity_days=90,
            use_hardware=False,
        )
        self.assertEqual(cert["subject"], "gateway.sovereign.local")
        self.assertEqual(cert["issuer"], "gateway.sovereign.local")
        self.assertTrue(cert["is_ca"])
        self.assertEqual(cert["algorithm"], "ML-DSA-65")
        self.assertEqual(cert["execution_label"], "[HOST FORMATTER]")
        self.assertTrue(cert["pem"].startswith("-----BEGIN CERTIFICATE-----\n"))
        self.assertTrue(cert["pem"].endswith("\n-----END CERTIFICATE-----"))
        self.assertGreater(len(cert["public_key_hex"]), 0)
        self.assertGreater(len(cert["signature_hex"]), 0)

    def test_03_certificate_chain_issuance(self):
        """Validates CA to Leaf certificate issuance and subject/issuer linkage."""
        root_ca = generate_pq_x509_certificate(
            subject_cn="Root CA Sovereignty",
            algorithm="ML-DSA-87",
            is_ca=True,
            use_hardware=False,
        )
        leaf_cert = generate_pq_x509_certificate(
            subject_cn="node-01.edge.sovereign",
            algorithm="ML-DSA-87",
            is_ca=False,
            issuer_cert=root_ca,
            issuer_sk_hex=root_ca["secret_key_hex"],
            use_hardware=False,
        )
        self.assertEqual(leaf_cert["issuer"], "Root CA Sovereignty")
        self.assertEqual(leaf_cert["subject"], "node-01.edge.sovereign")
        self.assertFalse(leaf_cert["is_ca"])
        self.assertEqual(leaf_cert["execution_label"], "[HOST FORMATTER]")

    def test_04_tls13_handshake_simulation_without_qkd(self):
        """Validates TLS 1.3 handshake sequence without hybrid QKD."""
        hs = simulate_tls13_pq_handshake(
            server_cn="api.sovereign.gateway",
            kem_group="X25519MLKEM768",
            sig_algorithm="ML-DSA-65",
            qkd_enabled=False,
            use_hardware=False,
        )
        self.assertEqual(hs["status"], "HANDSHAKE_ESTABLISHED")
        self.assertEqual(hs["execution_label"], "[HOST FORMATTER]")
        self.assertFalse(hs["qkd_hybrid_enabled"])
        self.assertIsNone(hs["qkd_key_id"])
        self.assertEqual(len(hs["handshake_steps"]), 5)
        self.assertIn("client_application_traffic_secret_0", hs["secrets"])
        self.assertIn("server_application_traffic_secret_0", hs["secrets"])

    def test_05_tls13_handshake_simulation_with_hybrid_qkd(self):
        """Validates TLS 1.3 handshake sequence with hybrid QKD fusion."""
        hs = simulate_tls13_pq_handshake(
            server_cn="hsm.sovereign.gateway",
            kem_group="X25519MLKEM768",
            sig_algorithm="ML-DSA-87",
            qkd_enabled=True,
            use_hardware=False,
        )
        self.assertEqual(hs["status"], "HANDSHAKE_ESTABLISHED")
        self.assertEqual(hs["execution_label"], "[HOST FORMATTER]")
        self.assertTrue(hs["qkd_hybrid_enabled"])
        self.assertIsNotNone(hs["qkd_key_id"])
        self.assertEqual(len(hs["handshake_steps"]), 5)
        self.assertIn("final_hybrid_key", hs["secrets"])


if __name__ == "__main__":
    unittest.main()
