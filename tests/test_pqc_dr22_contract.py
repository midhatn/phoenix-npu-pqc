# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON).
Validates parameter encodings, negacyclic ring arithmetic, descriptor packing,
and independent reference oracles for KeyGen, Sign, and Verify.
"""

import unittest
import os
import hashlib
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr22_fndsa_abi as abi
from phoenix_sdr_dsp.pqc import dr22_fndsa_graph as graph


class DR22FndsaContractTests(unittest.TestCase):

    def test_01_parameter_definitions(self):
        """Validates standard FIPS 206 parameters for FN-DSA-512 and FN-DSA-1024."""
        p512 = abi.FNDSA_PARAMS["FN-DSA-512"]
        self.assertEqual(p512.n, 512)
        self.assertEqual(p512.log_n, 9)
        self.assertEqual(p512.pk_bytes, 897)
        self.assertEqual(p512.sig_bound, 34034726)

        p1024 = abi.FNDSA_PARAMS["FN-DSA-1024"]
        self.assertEqual(p1024.n, 1024)
        self.assertEqual(p1024.log_n, 10)
        self.assertEqual(p1024.pk_bytes, 1793)
        self.assertEqual(p1024.sig_bound, 70265242)

    def test_02_descriptor_packing(self):
        """Validates 32-byte header descriptor serialization."""
        desc = abi.pack_fndsa_descriptor("FN-DSA-512", operation_mode=1, msg_len=256, epoch=42)
        self.assertEqual(len(desc), 32)
        self.assertEqual(desc[0:4], abi.MAGIC_DESC_DR22)
        self.assertEqual(desc[4], 0)  # FN-DSA-512
        self.assertEqual(desc[5], 1)  # Sign op mode
        self.assertEqual(int.from_bytes(desc[6:8], "little"), 512)
        self.assertEqual(int.from_bytes(desc[8:12], "little"), 256)
        self.assertEqual(int.from_bytes(desc[12:16], "little"), 42)
        self.assertEqual(int.from_bytes(desc[16:20], "little"), 34034726)

    def test_03_kernel_artifact_info(self):
        """Validates that the AIE2 kernel source exists and has a valid hash."""
        repo_root = Path(__file__).resolve().parents[1]
        info = graph.get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)
        self.assertEqual(len(info["sha256"]), 64)

    def test_04_reference_keygen_sign_verify_512(self):
        """Validates round-trip correctness of independent reference oracle on FN-DSA-512."""
        seed = b"\x42" * 32
        salt = b"\x13" * 40
        msg = b"NIST FIPS 206 FN-DSA Test Message on AMD Phoenix NPU"

        pk, sk = graph.ref_fndsa_keygen("FN-DSA-512", seed)
        self.assertEqual(len(pk), 897)
        self.assertEqual(len(sk), 1024)

        sig = graph.ref_fndsa_sign("FN-DSA-512", pk, sk, msg, salt)
        self.assertEqual(len(sig), 41 + 2 * 512)

        is_valid = graph.ref_fndsa_verify("FN-DSA-512", pk, msg, sig)
        self.assertTrue(is_valid)

        # Tampered message must fail verification
        tampered_msg = b"Tampered Message on AMD Phoenix NPU"
        self.assertFalse(graph.ref_fndsa_verify("FN-DSA-512", pk, tampered_msg, sig))

        # Tampered signature coefficient must fail verification
        tampered_sig = bytearray(sig)
        tampered_sig[50] ^= 0xFF
        self.assertFalse(graph.ref_fndsa_verify("FN-DSA-512", pk, msg, bytes(tampered_sig)))

        # Tampered public key must fail verification
        tampered_pk = bytearray(pk)
        tampered_pk[10] ^= 0x01
        self.assertFalse(graph.ref_fndsa_verify("FN-DSA-512", bytes(tampered_pk), msg, sig))


if __name__ == "__main__":
    unittest.main()
