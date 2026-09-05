# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR30:
3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor on AMD Phoenix AIE2.
"""

import unittest
from pathlib import Path
import numpy as np

from phoenix_sdr_dsp.pqc.dr30_3gpp_suci_abi import (
    MAGIC_DESC_DR30,
    PROFILE_NULL,
    PROFILE_A_CURVE25519,
    PROFILE_C_MLKEM768,
    PROFILE_D_MLKEM1024,
    MODE_SUCI_PARSE_VALIDATE,
    MODE_SUCI_DECAPSULATE_DERIVE,
    MODE_SUCI_DECONCEAL_VERIFY,
    MODE_SUCI_PIPELINE_FULL,
    pack_dr30_descriptor,
    unpack_dr30_descriptor,
)
from phoenix_sdr_dsp.pqc.dr30_3gpp_suci_graph import (
    get_kernel_artifact_info,
    ref_suci_validate_header,
    ref_derive_suci_keys,
    ref_compute_suci_mac,
    ref_decrypt_supi,
    ref_full_deconceal,
)


class DR30SuciContractTests(unittest.TestCase):

    def test_01_descriptor_packing(self):
        """Validates 32-byte hardware descriptor serialization for DR30."""
        desc = pack_dr30_descriptor(
            operation_mode=MODE_SUCI_PIPELINE_FULL,
            profile_id=PROFILE_C_MLKEM768,
            hn_key_id=42,
            suci_len=1120,
            epoch=777,
            routing_indicator=0x1234,
            mcc_mnc=0x0310260,
        )
        self.assertEqual(len(desc), 32)
        parsed = unpack_dr30_descriptor(desc)
        self.assertEqual(parsed.magic, MAGIC_DESC_DR30)
        self.assertEqual(parsed.operation_mode, MODE_SUCI_PIPELINE_FULL)
        self.assertEqual(parsed.profile_id, PROFILE_C_MLKEM768)
        self.assertEqual(parsed.hn_key_id, 42)
        self.assertEqual(parsed.suci_len, 1120)
        self.assertEqual(parsed.epoch, 777)
        self.assertEqual(parsed.routing_indicator, 0x1234)
        self.assertEqual(parsed.mcc_mnc, 0x0310260)

    def test_02_kernel_artifact_info(self):
        """Validates DR30 AIE2 kernel source artifact digest."""
        repo_root = Path(__file__).resolve().parents[1]
        info = get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_ref_suci_header_validation(self):
        """Validates 3GPP wire-format header validation rules."""
        # Valid Profile C
        self.assertTrue(ref_suci_validate_header(PROFILE_C_MLKEM768, hn_key_id=1, suci_len=64))
        # Valid Profile D
        self.assertTrue(ref_suci_validate_header(PROFILE_D_MLKEM1024, hn_key_id=2, suci_len=128))
        # Invalid Profile (Null or non-PQC)
        self.assertFalse(ref_suci_validate_header(PROFILE_NULL, hn_key_id=1, suci_len=64))
        # Invalid hn_key_id
        self.assertFalse(ref_suci_validate_header(PROFILE_C_MLKEM768, hn_key_id=0, suci_len=64))
        # Truncated length
        self.assertFalse(ref_suci_validate_header(PROFILE_C_MLKEM768, hn_key_id=1, suci_len=16))

    def test_04_ref_derive_suci_keys(self):
        """Validates reference key derivation determinism and uniqueness."""
        ss1 = bytes([0x11] * 32)
        ephem1 = bytes([0x22] * 32)
        keys1 = ref_derive_suci_keys(ss1, ephem1)
        self.assertEqual(len(keys1["k_enc"]), 16)
        self.assertEqual(len(keys1["k_mac"]), 16)
        self.assertNotEqual(keys1["k_enc"], keys1["k_mac"])

        # Repeat to verify determinism
        keys2 = ref_derive_suci_keys(ss1, ephem1)
        self.assertEqual(keys1["k_enc"], keys2["k_enc"])
        self.assertEqual(keys1["k_mac"], keys2["k_mac"])

        # Different input yields different keys
        ss2 = bytes([0x33] * 32)
        keys3 = ref_derive_suci_keys(ss2, ephem1)
        self.assertNotEqual(keys1["k_enc"], keys3["k_enc"])

    def test_05_ref_suci_mac_computation(self):
        """Validates MAC calculation over payload."""
        k_mac = bytes([0xAA] * 16)
        payload = b"310260123456789"  # IMSI string
        mac1 = ref_compute_suci_mac(k_mac, payload)
        self.assertEqual(len(mac1), 16)

        # Tampered payload yields different MAC
        tampered = b"310260123456788"
        mac2 = ref_compute_suci_mac(k_mac, tampered)
        self.assertNotEqual(mac1, mac2)

    def test_06_ref_full_deconceal_roundtrip(self):
        """Validates complete reference SUCI conceal and de-conceal pipeline."""
        ss = bytes(range(32))
        ephem = bytes(range(32, 64))
        keys = ref_derive_suci_keys(ss, ephem)

        original_supi = b"IMSI310260999888"
        # Encrypt with k_enc
        enc_payload = ref_decrypt_supi(keys["k_enc"], original_supi)
        # Compute valid MAC
        mac = ref_compute_suci_mac(keys["k_mac"], enc_payload)

        # Successful de-concealment
        ok, dec_supi = ref_full_deconceal(ss, ephem, mac, enc_payload)
        self.assertTrue(ok)
        self.assertEqual(dec_supi, original_supi)

        # Tampered MAC fails closed
        bad_mac = bytearray(mac)
        bad_mac[0] ^= 0xFF
        ok_bad, _ = ref_full_deconceal(ss, ephem, bytes(bad_mac), enc_payload)
        self.assertFalse(ok_bad)


if __name__ == "__main__":
    unittest.main()
