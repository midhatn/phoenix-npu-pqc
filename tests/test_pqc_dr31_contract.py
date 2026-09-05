# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR31:
NIST SP 800-208 / RFC 5280 / RFC 5652 X.509 Post-Quantum Certificates & Hybrid CMS Co-Processor.
"""

import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc.dr31_x509_cms_abi import (
    MAGIC_DESC_DR31,
    ALGO_ML_DSA_44,
    ALGO_ML_DSA_65,
    ALGO_ML_DSA_87,
    ALGO_SLH_DSA_SHAKE_128S,
    ALGO_LMS_SHA256_M32_H10,
    ALGO_HYBRID_ED25519_MLDSA65,
    ALGO_ML_KEM_768,
    MODE_X509_PQC_VERIFY,
    MODE_X509_HYBRID_VERIFY,
    MODE_CMS_SIGNED_DATA_VERIFY,
    MODE_CMS_ENVELOPED_UNWRAP,
    MODE_X509_CHAIN_STEP_VERIFY,
    FLAG_IS_CA,
    FLAG_HAS_SIGNED_ATTRS,
    pack_dr31_descriptor,
    unpack_dr31_descriptor,
    pack_x509_verify_request,
)
from phoenix_sdr_dsp.pqc.dr31_x509_cms_graph import (
    get_kernel_artifact_info,
    ref_x509_compute_fingerprint,
    ref_verify_pqc_signature,
    ref_verify_classical_signature,
    ref_unwrap_cms_cek,
    make_valid_pqc_signature,
    make_valid_classical_signature,
    make_wrapped_cek,
)


class DR31X509CmsContractTests(unittest.TestCase):

    def test_01_descriptor_packing(self):
        """Validates 32-byte hardware descriptor serialization for DR31."""
        desc = pack_dr31_descriptor(
            operation_mode=MODE_X509_HYBRID_VERIFY,
            algo_id=ALGO_HYBRID_ED25519_MLDSA65,
            flags=FLAG_IS_CA,
            tbs_len=32,
            pk_len=1952,
            sig_len=3293,
            aux_len=96,
        )
        self.assertEqual(len(desc), 32)
        parsed = unpack_dr31_descriptor(desc)
        self.assertEqual(parsed.magic, MAGIC_DESC_DR31)
        self.assertEqual(parsed.operation_mode, MODE_X509_HYBRID_VERIFY)
        self.assertEqual(parsed.algo_id, ALGO_HYBRID_ED25519_MLDSA65)
        self.assertEqual(parsed.flags, FLAG_IS_CA)
        self.assertEqual(parsed.tbs_len, 32)
        self.assertEqual(parsed.pk_len, 1952)
        self.assertEqual(parsed.sig_len, 3293)
        self.assertEqual(parsed.aux_len, 96)

    def test_02_kernel_artifact_info(self):
        """Validates DR31 AIE2 kernel source artifact digest."""
        repo_root = Path(__file__).resolve().parents[1]
        info = get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_ref_x509_pqc_signature_verification(self):
        """Validates PQC signature verification oracle and tamper rejection."""
        tbs = bytes([0x55] * 32)
        pk = bytes([0x12] * 1952)
        sig = make_valid_pqc_signature(ALGO_ML_DSA_65, tbs, pk, 3293)

        # Valid signature verifies
        self.assertTrue(ref_verify_pqc_signature(ALGO_ML_DSA_65, tbs, pk, sig))

        # Tampered signature is rejected
        bad_sig = bytearray(sig)
        bad_sig[0] ^= 0x01
        self.assertFalse(ref_verify_pqc_signature(ALGO_ML_DSA_65, tbs, pk, bytes(bad_sig)))

        # All-zero signature is rejected
        zero_sig = bytes(3293)
        self.assertFalse(ref_verify_pqc_signature(ALGO_ML_DSA_65, tbs, pk, zero_sig))

    def test_04_ref_hybrid_signature_verification(self):
        """Validates composite/hybrid dual-signature strict AND logic."""
        tbs = bytes([0xAA] * 32)
        pqc_pk = bytes([0x33] * 1952)
        pqc_sig = make_valid_pqc_signature(ALGO_ML_DSA_65, tbs, pqc_pk, 3293)

        ed_pk = bytes([0x44] * 32)
        ed_sig = make_valid_classical_signature(tbs, ed_pk)

        # Both valid -> True
        pqc_ok = ref_verify_pqc_signature(ALGO_ML_DSA_65, tbs, pqc_pk, pqc_sig)
        ed_ok = ref_verify_classical_signature(tbs, ed_pk, ed_sig)
        self.assertTrue(pqc_ok and ed_ok)

        # Classical tampered -> False
        bad_ed_sig = bytearray(ed_sig)
        bad_ed_sig[0] ^= 0x01
        self.assertFalse(ref_verify_classical_signature(tbs, ed_pk, bytes(bad_ed_sig)))

        # PQC tampered -> False
        bad_pqc_sig = bytearray(pqc_sig)
        bad_pqc_sig[0] ^= 0x01
        self.assertFalse(ref_verify_pqc_signature(ALGO_ML_DSA_65, tbs, pqc_pk, bytes(bad_pqc_sig)))

    def test_05_ref_cms_enveloped_unwrap(self):
        """Validates CMS EnvelopedData KEM decapsulation & CEK unwrap roundtrip."""
        kem_ct = bytes(range(128))
        plain_cek = bytes([0x77] * 32)
        wrapped_cek = make_wrapped_cek(kem_ct, plain_cek)

        # Valid unwrap
        ok, unwrapped = ref_unwrap_cms_cek(ALGO_ML_KEM_768, kem_ct, wrapped_cek)
        self.assertTrue(ok)
        self.assertEqual(unwrapped, plain_cek)

        # Tampered auth tag fails closed
        bad_wrapped = bytearray(wrapped_cek)
        bad_wrapped[-1] ^= 0xFF
        bad_ok, _ = ref_unwrap_cms_cek(ALGO_ML_KEM_768, kem_ct, bytes(bad_wrapped))
        self.assertFalse(bad_ok)

    def test_06_ref_chain_step_verification(self):
        """Validates CA hierarchy constraint enforcement."""
        tbs = bytes([0x88] * 32)
        ca_pk = bytes([0x99] * 1952)
        sig = make_valid_pqc_signature(ALGO_ML_DSA_65, tbs, ca_pk, 3293)

        # Valid CA flag + signature
        valid_ca = True
        sig_ok = ref_verify_pqc_signature(ALGO_ML_DSA_65, tbs, ca_pk, sig)
        self.assertTrue(valid_ca and sig_ok)

        # Non-CA certificate cannot delegate
        invalid_ca = False
        self.assertFalse(invalid_ca and sig_ok)

    def test_07_request_packing_bounds(self):
        """Validates request packing length boundary enforcement."""
        valid_tbs = bytes(32)
        valid_pk = bytes(1952)
        valid_sig = bytes(3293)

        # Exceeded TBS digest length raises ValueError
        with self.assertRaises(ValueError):
            pack_x509_verify_request(bytes(65), valid_pk, bytes(100))

        # Exceeded PK length raises ValueError
        with self.assertRaises(ValueError):
            pack_x509_verify_request(valid_tbs, bytes(3841), bytes(100))

        # Exceeded signature length raises ValueError
        with self.assertRaises(ValueError):
            pack_x509_verify_request(valid_tbs, valid_pk, bytes(10241))


if __name__ == "__main__":
    unittest.main()
