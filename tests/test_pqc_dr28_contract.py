# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR28:
NIST SP 800-208 / RFC 8554 Leighton-Micali Signatures (LMS/HSS) Stateless Verification on AMD Phoenix AIE2.
"""

import unittest
from pathlib import Path
import numpy as np

from phoenix_sdr_dsp.pqc.dr28_lms_verifier_abi import (
    MAGIC_DESC_DR28,
    LMS_SHA256_M32_H5,
    LMOTS_SHA256_N32_W4,
    MODE_VERIFY_LMS_SIGNATURE,
    MODE_RECOVER_LMOTS_LEAF,
    MODE_MERKLE_PATH_TRAVERSE,
    pack_dr28_descriptor,
    unpack_dr28_descriptor,
)
from phoenix_sdr_dsp.pqc.dr28_lms_verifier_graph import (
    get_kernel_artifact_info,
    ref_lms_generate_test_fixture,
    ref_lms_verify,
)


class DR28LmsVerifierContractTests(unittest.TestCase):

    def test_01_descriptor_packing(self):
        """Validates 32-byte hardware descriptor serialization for DR28."""
        desc = pack_dr28_descriptor(
            operation_mode=MODE_VERIFY_LMS_SIGNATURE,
            msg_len=128,
            epoch=99,
        )
        self.assertEqual(len(desc), 32)
        parsed = unpack_dr28_descriptor(desc)
        self.assertEqual(parsed.magic, MAGIC_DESC_DR28)
        self.assertEqual(parsed.operation_mode, MODE_VERIFY_LMS_SIGNATURE)
        self.assertEqual(parsed.msg_len, 128)
        self.assertEqual(parsed.epoch, 99)
        self.assertEqual(parsed.lms_type, LMS_SHA256_M32_H5)
        self.assertEqual(parsed.lmots_type, LMOTS_SHA256_N32_W4)

    def test_02_kernel_artifact_info(self):
        """Validates DR28 AIE2 kernel source artifact digest."""
        repo_root = Path(__file__).resolve().parents[1]
        info = get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_ref_lms_valid_signature(self):
        """Validates reference LMS verification with valid signature fixture."""
        rng = np.random.default_rng(seed=0x2801)
        I = rng.bytes(16)
        q = 3
        msg = b"AIE2 Bitstream Header Authentication Test"
        C, y_sigs, auth_path, root = ref_lms_generate_test_fixture(I, q, msg, rng, h=5)

        is_valid = ref_lms_verify(I, root, q, C, y_sigs, auth_path, msg, h=5)
        self.assertTrue(is_valid)

    def test_04_ref_lms_corrupted_message(self):
        """Validates that corrupted message is rejected."""
        rng = np.random.default_rng(seed=0x2802)
        I = rng.bytes(16)
        q = 5
        msg = b"Original bitstream"
        C, y_sigs, auth_path, root = ref_lms_generate_test_fixture(I, q, msg, rng, h=5)

        corrupt_msg = b"Tampered bitstream"
        is_valid = ref_lms_verify(I, root, q, C, y_sigs, auth_path, corrupt_msg, h=5)
        self.assertFalse(is_valid)

    def test_05_ref_lms_corrupted_path(self):
        """Validates that corrupted Merkle path is rejected."""
        rng = np.random.default_rng(seed=0x2803)
        I = rng.bytes(16)
        q = 2
        msg = b"Immutable Secure Boot payload"
        C, y_sigs, auth_path, root = ref_lms_generate_test_fixture(I, q, msg, rng, h=5)

        corrupt_path = bytearray(auth_path)
        corrupt_path[10] ^= 0xFF
        is_valid = ref_lms_verify(I, root, q, C, y_sigs, bytes(corrupt_path), msg, h=5)
        self.assertFalse(is_valid)


if __name__ == "__main__":
    unittest.main()
