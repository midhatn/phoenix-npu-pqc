# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+).
Validates parameter encodings, ADRS domain separation, descriptor packing,
and independent reference oracles for KeyGen, Sign, and Verify.
"""

import unittest
import os
import hashlib
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr21_slhdsa_abi as abi
from phoenix_sdr_dsp.pqc import dr21_slhdsa_graph as graph


class DR21SlhdsaContractTests(unittest.TestCase):

    def test_01_parameter_definitions(self):
        """Validates standard FIPS 205 parameters for SHAKE parameter sets."""
        p128s = abi.SLHDSA_PARAMS["SLH-DSA-SHAKE-128s"]
        self.assertEqual(p128s.n, 16)
        self.assertEqual(p128s.pk_bytes, 32)
        self.assertEqual(p128s.sk_bytes, 64)
        self.assertEqual(p128s.sig_bytes, 7856)

        p256s = abi.SLHDSA_PARAMS["SLH-DSA-SHAKE-256s"]
        self.assertEqual(p256s.n, 32)
        self.assertEqual(p256s.pk_bytes, 64)
        self.assertEqual(p256s.sk_bytes, 128)
        self.assertEqual(p256s.sig_bytes, 29792)

    def test_02_adrs_structure(self):
        """Validates 32-byte ADRS domain separation serialization."""
        adrs = abi.ADRS()
        adrs.set_layer_address(7)
        adrs.set_tree_address(42)
        adrs.set_type(abi.ADRS_TYPE_WOTS_HASH)
        adrs.set_keypair_address(10)
        adrs.set_chain_address(5)
        adrs.set_hash_address(12)

        adrs_bytes = adrs.to_bytes()
        self.assertEqual(len(adrs_bytes), 32)
        self.assertEqual(int.from_bytes(adrs_bytes[0:4], "big"), 7)
        self.assertEqual(int.from_bytes(adrs_bytes[4:16], "big"), 42)
        self.assertEqual(int.from_bytes(adrs_bytes[16:20], "big"), abi.ADRS_TYPE_WOTS_HASH)
        self.assertEqual(int.from_bytes(adrs_bytes[20:24], "big"), 10)
        self.assertEqual(int.from_bytes(adrs_bytes[24:28], "big"), 5)
        self.assertEqual(int.from_bytes(adrs_bytes[28:32], "big"), 12)

    def test_03_descriptor_packing(self):
        """Validates 32-byte header descriptor serialization."""
        desc = abi.pack_slhdsa_descriptor("SLH-DSA-SHAKE-128s", operation_mode=1, msg_len=128, epoch=99)
        self.assertEqual(len(desc), 32)
        self.assertEqual(desc[0:4], abi.MAGIC_DESC_DR21)
        self.assertEqual(desc[4], 0)  # 128s mode id
        self.assertEqual(desc[5], 1)  # Sign op mode
        self.assertEqual(int.from_bytes(desc[6:8], "little"), 16)  # n = 16
        self.assertEqual(int.from_bytes(desc[8:12], "little"), 128)  # msg_len = 128
        self.assertEqual(int.from_bytes(desc[12:16], "little"), 99)  # epoch = 99
        self.assertEqual(int.from_bytes(desc[16:20], "little"), 7856)  # sig_bytes = 7856

    def test_04_kernel_artifact_info(self):
        """Validates that the AIE2 kernel source exists and has a valid hash."""
        repo_root = Path(__file__).resolve().parents[1]
        info = graph.get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)
        self.assertEqual(len(info["sha256"]), 64)

    def test_05_reference_keygen_sign_verify_128s(self):
        """Validates round-trip correctness of independent reference oracle on SLH-DSA-SHAKE-128s."""
        sk_seed = b"\x01" * 16
        pk_seed = b"\x02" * 16
        sk_prf = b"\x03" * 16
        opt_rand = b"\x04" * 16
        msg = b"NIST FIPS 205 Test Message on AMD Phoenix NPU"

        pk, sk = graph.ref_slhdsa_keygen("SLH-DSA-SHAKE-128s", sk_seed, pk_seed, sk_prf)
        self.assertEqual(len(pk), 32)
        self.assertEqual(len(sk), 64)

        sig = graph.ref_slhdsa_sign("SLH-DSA-SHAKE-128s", sk, msg, opt_rand)
        self.assertEqual(len(sig), 7856)

        is_valid = graph.ref_slhdsa_verify("SLH-DSA-SHAKE-128s", pk, msg, sig)
        self.assertTrue(is_valid)

        # Tampered message must fail verification
        tampered_msg = b"Tampered Message on AMD Phoenix NPU"
        self.assertFalse(graph.ref_slhdsa_verify("SLH-DSA-SHAKE-128s", pk, tampered_msg, sig))

        # Tampered signature must fail verification
        tampered_sig = bytearray(sig)
        tampered_sig[100] ^= 0xFF
        self.assertFalse(graph.ref_slhdsa_verify("SLH-DSA-SHAKE-128s", pk, msg, bytes(tampered_sig)))

        # Tampered public key must fail verification
        tampered_pk = bytearray(pk)
        tampered_pk[5] ^= 0x01
        self.assertFalse(graph.ref_slhdsa_verify("SLH-DSA-SHAKE-128s", bytes(tampered_pk), msg, sig))


if __name__ == "__main__":
    unittest.main()
