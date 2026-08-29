# SPDX-License-Identifier: Apache-2.0
"""
Device-Resident Silicon Test Suite: Milestone DR23 (Gate 24).
OpenSSL 3.x Native Provider Plugin & PKCS#11 v3.0 HSM Cryptoki Token on AMD Phoenix NPU (AIE2 / XDNA1).

Standards & Resource Citations:
1. OpenSSL 3.0+ Provider API Specification (OSSL_PROVIDER, OSSL_DISPATCH, OSSL_ALGORITHM)
2. OASIS PKCS #11 Cryptographic Token Interface Standard (v3.0)
3. NIST FIPS 203 (ML-KEM) & NIST FIPS 204 (ML-DSA)
4. ETSI GS QKD 014 v1.1.1 & NIST SP 800-56C Rev. 2
5. AMD Phoenix AIE2 Architecture: Zero Host Fallback Silicon Execution
6. DOI: 10.5281/zenodo.22162273
"""

import os
import sys
import unittest

# Ensure repository root is on path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from phoenix_sdr_dsp.pqc.dr23_openssl_provider import (
    get_phoenix_pqc_provider,
    OSSL_OP_KEYMGMT,
    OSSL_OP_KEM,
    OSSL_OP_SIGNATURE,
)
from phoenix_sdr_dsp.pqc.dr23_pkcs11_hsm import (
    get_phoenix_pkcs11_hsm,
    CKR_OK,
    CKR_PIN_INCORRECT,
    CKR_USER_NOT_LOGGED_IN,
    CKR_SIGNATURE_INVALID,
    CKM_ML_KEM_KEY_PAIR_GEN,
    CKM_ML_KEM_ENCAPSULATE,
    CKM_ML_KEM_DECAPSULATE,
    CKM_ML_DSA_KEY_PAIR_GEN,
    CKM_ML_DSA,
    CKU_USER,
)

class TestDR23OpenSslProviderSilicon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = get_phoenix_pqc_provider()
        cls.hsm = get_phoenix_pkcs11_hsm()

    def setUp(self):
        # Reset HSM state
        self.hsm.C_Finalize()
        self.hsm.C_Initialize()

    def tearDown(self):
        self.hsm.C_Finalize()

    def test_01_provider_discovery_and_algorithm_query(self):
        """Validates OpenSSL 3.x Provider parameter query and algorithm tables."""
        params = self.provider.get_params()
        self.assertEqual(params["name"], "phoenix_pqc_provider")
        self.assertEqual(params["version"], "1.2.0")
        self.assertTrue(params["zero_host_fallback"])
        self.assertEqual(params["status"], "ACTIVE_SILICON")

        kem_algos = self.provider.query_operation(OSSL_OP_KEM)
        kem_names = [a["algorithm"] for a in kem_algos]
        self.assertIn("ML-KEM-512", kem_names)
        self.assertIn("ML-KEM-768", kem_names)
        self.assertIn("ML-KEM-1024", kem_names)
        self.assertIn("QKD-ML-KEM-768", kem_names)

        sig_algos = self.provider.query_operation(OSSL_OP_SIGNATURE)
        sig_names = [a["algorithm"] for a in sig_algos]
        self.assertIn("ML-DSA-44", sig_names)
        self.assertIn("ML-DSA-65", sig_names)
        self.assertIn("ML-DSA-87", sig_names)

    def test_02_evp_kem_full_lifecycle_silicon(self):
        """Validates OpenSSL EVP_KEM KeyGen, Encaps, and Decaps on physical AIE2 silicon."""
        for kem_name in ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]:
            with self.subTest(algorithm=kem_name):
                # 1. KeyGen on hardware
                key = self.provider.kem_keygen(kem_name)
                self.assertIsNotNone(key.pubkey)
                self.assertIsNotNone(key.privkey)

                # 2. Encapsulate on hardware
                ct, ss_enc = self.provider.kem_encapsulate(key)
                self.assertGreater(len(ct), 0)
                self.assertEqual(len(ss_enc), 32)

                # 3. Decapsulate on hardware
                ss_dec = self.provider.kem_decapsulate(key, ct)
                self.assertEqual(ss_enc, ss_dec, f"Shared secret mismatch for {kem_name}")

                # 4. Zeroize private key
                key.zeroize()
                self.assertIsNone(key.privkey)

    def test_03_evp_signature_full_lifecycle_silicon(self):
        """Validates OpenSSL EVP_SIGNATURE KeyGen, Sign, and Verify on physical AIE2 silicon."""
        msg = b"OpenSSL 3.x Hardware Signature Validation Payload on AMD Phoenix NPU"
        for sig_name in ["ML-DSA-44", "ML-DSA-65"]:
            with self.subTest(algorithm=sig_name):
                # 1. KeyGen on hardware
                key = self.provider.signature_keygen(sig_name)
                self.assertIsNotNone(key.pubkey)
                self.assertIsNotNone(key.privkey)

                # 2. Sign on hardware
                sig = self.provider.signature_sign(key, msg)
                self.assertGreater(len(sig), 0)

                # 3. Verify on hardware
                valid = self.provider.signature_verify(key, msg, sig)
                self.assertTrue(valid, f"Signature verification failed for {sig_name}")

                # 4. Tampered message rejection
                bad_valid = self.provider.signature_verify(key, msg + b"_tamper", sig)
                self.assertFalse(bad_valid, f"Tampered message was not rejected for {sig_name}")

        # ML-DSA-87 KeyGen & Sign evaluation
        key87 = self.provider.signature_keygen("ML-DSA-87")
        self.assertEqual(len(key87.pubkey), 2592)
        self.assertEqual(len(key87.privkey), 4896)
        sig87 = self.provider.signature_sign(key87, msg)
        self.assertEqual(len(sig87), 4627)

    def test_04_evp_hybrid_qkd_kem_exchange_silicon(self):
        """Validates OpenSSL EVP_KEM QKD-ML-KEM-768 hybrid exchange on AIE2 hardware."""
        res = self.provider.hybrid_qkd_kem_exchange(kem_param="ML-KEM-768")
        self.assertTrue(res["is_key_matched"])
        self.assertTrue(res["is_authenticated"])
        self.assertEqual(len(res["k_final_master"]), 64) # 32 bytes hex = 64 hex chars
        self.assertEqual(res["k_final_master"], res["k_final_slave"])

    def test_05_pkcs11_token_session_and_authentication(self):
        """Validates PKCS#11 v3.0 Cryptoki token sessions and PIN authentication."""
        rv, info = self.hsm.C_GetInfo()
        self.assertEqual(rv, CKR_OK)
        self.assertEqual(info["cryptokiVersion"], (3, 0))

        rv, slots = self.hsm.C_GetSlotList()
        self.assertEqual(rv, CKR_OK)
        self.assertIn(0, slots)

        rv, tok_info = self.hsm.C_GetTokenInfo(0)
        self.assertEqual(rv, CKR_OK)
        self.assertEqual(tok_info["label"], "Phoenix AIE2 PQC/QKD HSM Token")

        # Open Session
        rv, session = self.hsm.C_OpenSession(0)
        self.assertEqual(rv, CKR_OK)

        # Generate key without login -> CKR_USER_NOT_LOGGED_IN
        rv, _, _ = self.hsm.C_GenerateKeyPair(session, CKM_ML_KEM_KEY_PAIR_GEN, "ML-KEM-768")
        self.assertEqual(rv, CKR_USER_NOT_LOGGED_IN)

        # Bad PIN Login
        rv = self.hsm.C_Login(session, CKU_USER, "wrong_pin")
        self.assertEqual(rv, CKR_PIN_INCORRECT)

        # Correct PIN Login
        rv = self.hsm.C_Login(session, CKU_USER, "123456")
        self.assertEqual(rv, CKR_OK)

        # Close session
        rv = self.hsm.C_CloseSession(session)
        self.assertEqual(rv, CKR_OK)

    def test_06_pkcs11_kem_and_signature_operations_silicon(self):
        """Validates PKCS#11 Cryptoki C_GenerateKeyPair, C_Sign/Verify, and C_DeriveKey on silicon."""
        rv, session = self.hsm.C_OpenSession(0)
        self.assertEqual(rv, CKR_OK)
        self.assertEqual(self.hsm.C_Login(session, CKU_USER, "123456"), CKR_OK)

        # 1. PKCS#11 ML-KEM-768 KeyGen & Key Derivation (Encaps/Decaps)
        rv, pub_k, priv_k = self.hsm.C_GenerateKeyPair(session, CKM_ML_KEM_KEY_PAIR_GEN, "ML-KEM-768")
        self.assertEqual(rv, CKR_OK)

        # Encapsulate using public key handle
        rv, ct, ss_enc = self.hsm.C_DeriveKey(session, CKM_ML_KEM_ENCAPSULATE, pub_k)
        self.assertEqual(rv, CKR_OK)

        # Decapsulate using private key handle
        rv, _, ss_dec = self.hsm.C_DeriveKey(session, CKM_ML_KEM_DECAPSULATE, priv_k, ciphertext_in=ct)
        self.assertEqual(rv, CKR_OK)
        self.assertEqual(ss_enc, ss_dec)

        # 2. PKCS#11 ML-DSA-65 KeyGen, Sign, and Verify
        rv, pub_s, priv_s = self.hsm.C_GenerateKeyPair(session, CKM_ML_DSA_KEY_PAIR_GEN, "ML-DSA-65")
        self.assertEqual(rv, CKR_OK)

        msg = b"PKCS#11 v3.0 HSM Hardware Sign Test Payload"
        rv = self.hsm.C_SignInit(session, CKM_ML_DSA, priv_s)
        self.assertEqual(rv, CKR_OK)
        rv, sig = self.hsm.C_Sign(session, msg)
        self.assertEqual(rv, CKR_OK)

        rv = self.hsm.C_VerifyInit(session, CKM_ML_DSA, pub_s)
        self.assertEqual(rv, CKR_OK)
        rv = self.hsm.C_Verify(session, msg, sig)
        self.assertEqual(rv, CKR_OK)

        # Tampered verification
        rv = self.hsm.C_VerifyInit(session, CKM_ML_DSA, pub_s)
        self.assertEqual(rv, CKR_OK)
        rv = self.hsm.C_Verify(session, msg + b"_tamper", sig)
        self.assertEqual(rv, CKR_SIGNATURE_INVALID)

        # Clean session close
        self.hsm.C_CloseSession(session)

if __name__ == "__main__":
    unittest.main()
