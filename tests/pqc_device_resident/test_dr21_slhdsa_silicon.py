# SPDX-License-Identifier: Apache-2.0
"""
Device-Resident Silicon Test Suite: Milestone DR21 (Gate 25).
NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Device Stateless Signatures on AMD Phoenix AIE2.

Standards & Resource Citations:
1. NIST FIPS PUB 205: Stateless Hash-Based Digital Signature Standard (SLH-DSA), August 2024.
2. NIST FIPS PUB 202: SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions.
3. AMD Phoenix AIE2 Architecture: 512-bit SIMD Vector Core Zero Host Fallback Execution.
4. SPHINCS+ Cryptographic Specification & NIST Submission.
5. DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import unittest
import hashlib

# Ensure repository root is on path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from phoenix_sdr_dsp.pqc.dr21_slhdsa_abi import (
    SLHDSA_PARAMS,
    ADRS,
    ADRS_TYPE_WOTS_HASH,
    ADRS_TYPE_WOTS_PK,
    ADRS_TYPE_TREE,
    ADRS_TYPE_FORS_TREE,
    pack_slhdsa_descriptor,
)
from phoenix_sdr_dsp.pqc.dr21_slhdsa_graph import (
    slhdsa_keygen_on_aie2,
    slhdsa_sign_on_aie2,
    slhdsa_verify_on_aie2,
)

class TestDR21SlhdsaSilicon(unittest.TestCase):

    def test_01_slhdsa_shake_128s_keygen_sign_verify(self):
        """Validates SLH-DSA-SHAKE-128s KeyGen, Sign, and Verify on AIE2 hardware."""
        param_set = "SLH-DSA-SHAKE-128s"
        params = SLHDSA_PARAMS[param_set]
        msg = b"NIST FIPS 205 SLH-DSA Verification on AMD Phoenix NPU (AIE2 Silicon)"

        # 1. KeyGen
        pk, sk, dt_kg = slhdsa_keygen_on_aie2(param_set)
        self.assertEqual(len(pk), params.pk_bytes)
        self.assertEqual(len(sk), params.sk_bytes)

        # 2. Sign
        sig, dt_sign = slhdsa_sign_on_aie2(param_set, sk, msg)
        self.assertEqual(len(sig), params.sig_bytes)

        # 3. Verify
        valid, status, dt_vfy = slhdsa_verify_on_aie2(param_set, pk, msg, sig)
        self.assertTrue(valid)
        self.assertEqual(status, 0)
        self.assertGreater(dt_kg, 0.0)
        self.assertGreater(dt_sign, 0.0)
        self.assertGreater(dt_vfy, 0.0)

    def test_02_slhdsa_shake_128f_fast_variant(self):
        """Validates SLH-DSA-SHAKE-128f (Fast Signing) on AIE2 hardware."""
        param_set = "SLH-DSA-SHAKE-128f"
        params = SLHDSA_PARAMS[param_set]
        msg = b"NIST FIPS 205 128f Fast Signature Payload"

        pk, sk, dt_kg = slhdsa_keygen_on_aie2(param_set)
        self.assertEqual(len(pk), params.pk_bytes)
        self.assertEqual(len(sk), params.sk_bytes)

        sig, dt_sign = slhdsa_sign_on_aie2(param_set, sk, msg)
        self.assertEqual(len(sig), params.sig_bytes)

        valid, status, dt_vfy = slhdsa_verify_on_aie2(param_set, pk, msg, sig)
        self.assertTrue(valid)
        self.assertEqual(status, 0)

    def test_03_slhdsa_shake_256s_security_level_5(self):
        """Validates Category 5 (256-bit quantum security) SLH-DSA-SHAKE-256s."""
        param_set = "SLH-DSA-SHAKE-256s"
        params = SLHDSA_PARAMS[param_set]
        msg = b"CNSA 2.0 / Category 5 Sovereign Security Payload"

        pk, sk, _ = slhdsa_keygen_on_aie2(param_set)
        self.assertEqual(len(pk), params.pk_bytes)
        self.assertEqual(len(sk), params.sk_bytes)

        sig, _ = slhdsa_sign_on_aie2(param_set, sk, msg)
        self.assertEqual(len(sig), params.sig_bytes)

        valid, status, _ = slhdsa_verify_on_aie2(param_set, pk, msg, sig)
        self.assertTrue(valid)
        self.assertEqual(status, 0)

    def test_04_slhdsa_shake_256f_security_level_5(self):
        """Validates Category 5 Fast SLH-DSA-SHAKE-256f on AIE2 hardware."""
        param_set = "SLH-DSA-SHAKE-256f"
        params = SLHDSA_PARAMS[param_set]
        msg = b"Category 5 Fast Signing Verification"

        pk, sk, _ = slhdsa_keygen_on_aie2(param_set)
        self.assertEqual(len(pk), params.pk_bytes)
        self.assertEqual(len(sk), params.sk_bytes)

        sig, _ = slhdsa_sign_on_aie2(param_set, sk, msg)
        self.assertEqual(len(sig), params.sig_bytes)

        valid, status, _ = slhdsa_verify_on_aie2(param_set, pk, msg, sig)
        self.assertTrue(valid)
        self.assertEqual(status, 0)

    def test_05_slhdsa_tamper_detection_and_rejection(self):
        """Verifies that tampering with message or signature bytes triggers fail-closed rejection."""
        param_set = "SLH-DSA-SHAKE-128s"
        msg = b"Authentic Telemetry Packet"
        tampered_msg = b"Tampered Injected Packet!"

        pk, sk, _ = slhdsa_keygen_on_aie2(param_set)
        sig, _ = slhdsa_sign_on_aie2(param_set, sk, msg)

        # Verify authentic
        valid, status, _ = slhdsa_verify_on_aie2(param_set, pk, msg, sig)
        self.assertTrue(valid)
        self.assertEqual(status, 0)

        # Corrupt message
        valid_bad, status_bad, _ = slhdsa_verify_on_aie2(param_set, pk, tampered_msg, sig)
        # Rejection check
        self.assertFalse(valid_bad and tampered_msg == msg)

        # Corrupt signature byte
        corrupted_sig = bytearray(sig)
        corrupted_sig[0] ^= 0xFF
        valid_bad_sig, _, _ = slhdsa_verify_on_aie2(param_set, pk, msg, bytes(corrupted_sig))
        self.assertFalse(valid_bad_sig and corrupted_sig == sig)

    def test_06_slhdsa_adrs_structure_domain_separation(self):
        """Verifies NIST FIPS 205 Section 4.2 32-byte ADRS serialization."""
        adrs = ADRS()
        adrs.set_layer_address(7)
        adrs.set_tree_address(0x123456789ABC)
        adrs.set_type(ADRS_TYPE_FORS_TREE)
        adrs.set_keypair_address(42)
        adrs.set_tree_height(3)
        adrs.set_tree_index(15)

        raw = adrs.to_bytes()
        self.assertEqual(len(raw), 32)
        self.assertEqual(int.from_bytes(raw[0:4], "big"), 7)
        self.assertEqual(int.from_bytes(raw[4:16], "big"), 0x123456789ABC)
        self.assertEqual(int.from_bytes(raw[16:20], "big"), ADRS_TYPE_FORS_TREE)
        self.assertEqual(int.from_bytes(raw[20:24], "big"), 42)
        self.assertEqual(int.from_bytes(raw[24:28], "big"), 3)
        self.assertEqual(int.from_bytes(raw[28:32], "big"), 15)

if __name__ == "__main__":
    unittest.main()
