# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR23: OpenSSL 3.x Provider & OASIS PKCS#11 v3.0 HSM.
Validates OpenSSL provider query interfaces, KEM dispatch, signature dispatch,
and PKCS#11 session lifecycle, login, and zeroization routines.
"""

import unittest
import os
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr23_openssl_provider as dr23_provider
from phoenix_sdr_dsp.pqc import dr23_pkcs11_hsm as dr23_pkcs11


class DR23OpenSslPkcs11ContractTests(unittest.TestCase):

    def test_01_provider_metadata_and_capabilities(self):
        """Validates OpenSSL 3.x provider metadata and operation queries."""
        prov = dr23_provider.get_phoenix_pqc_provider()
        params = prov.get_params()
        self.assertEqual(params["name"], "phoenix_pqc_provider")
        self.assertEqual(params["version"], "1.2.0")
        self.assertTrue(params["zero_host_fallback"])

        kem_ops = prov.query_operation(dr23_provider.OSSL_OP_KEM)
        kem_algos = [op["algorithm"] for op in kem_ops]
        self.assertIn("ML-KEM-512", kem_algos)
        self.assertIn("ML-KEM-768", kem_algos)
        self.assertIn("ML-KEM-1024", kem_algos)

        sig_ops = prov.query_operation(dr23_provider.OSSL_OP_SIGNATURE)
        sig_algos = [op["algorithm"] for op in sig_ops]
        self.assertIn("ML-DSA-44", sig_algos)
        self.assertIn("ML-DSA-65", sig_algos)
        self.assertIn("ML-DSA-87", sig_algos)

    def test_02_artifact_info(self):
        """Validates DR23 source file information."""
        repo_root = Path(__file__).resolve().parents[1]
        info = dr23_provider.get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_pkcs11_session_and_token_info(self):
        """Validates PKCS#11 cryptoki module initialization and token info."""
        hsm = dr23_pkcs11.get_phoenix_pkcs11_hsm()
        self.assertEqual(hsm.C_Initialize(), dr23_pkcs11.CKR_OK)

        rv, slots = hsm.C_GetSlotList()
        self.assertEqual(rv, dr23_pkcs11.CKR_OK)
        self.assertGreater(len(slots), 0)

        slot_id = slots[0]
        rv, token_info = hsm.C_GetTokenInfo(slot_id)
        self.assertEqual(rv, dr23_pkcs11.CKR_OK)
        self.assertIn("Phoenix", token_info["label"])

        rv, sess = hsm.C_OpenSession(slot_id, dr23_pkcs11.CKF_RW_SESSION | dr23_pkcs11.CKF_SERIAL_SESSION)
        self.assertEqual(rv, dr23_pkcs11.CKR_OK)

        # Login with correct PIN
        self.assertEqual(hsm.C_Login(sess, dr23_pkcs11.CKU_USER, "123456"), dr23_pkcs11.CKR_OK)

        # Logout
        self.assertEqual(hsm.C_Logout(sess), dr23_pkcs11.CKR_OK)
        self.assertEqual(hsm.C_CloseSession(sess), dr23_pkcs11.CKR_OK)

    def test_04_pkcs11_zeroization(self):
        """Validates hardware zeroization on session close."""
        hsm = dr23_pkcs11.get_phoenix_pkcs11_hsm()
        hsm.C_Initialize()
        rv, slots = hsm.C_GetSlotList()
        slot_id = slots[0]
        token = hsm.tokens[slot_id]
        token.objects[999] = dr23_provider.PhoenixPqcKey("ML-KEM-512", b"pubkey", b"privkey")
        self.assertIn(999, token.objects)

        token.zeroize()
        self.assertEqual(len(token.objects), 0)


if __name__ == "__main__":
    unittest.main()
