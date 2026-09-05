# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR37:
Dual-Scheme Hybrid Classical / Quantum-Safe KEM Engine on AMD Phoenix AIE2.
Compliant with ETSI TS 103 744, BSI TR-02102-1, IETF RFC 9180 (HPKE), and NIST SP 800-56C Rev. 2.
"""

import unittest
import struct
import hashlib

from phoenix_sdr_dsp.pqc.dr37_hybrid_kem_abi import (
    MAGIC_HEADER,
    MAGIC_RESULT,
    MODE_HYBRID_ENCAPS_COMBINE,
    MODE_HYBRID_DECAPS_COMBINE,
    MODE_HYBRID_SPLIT_SECRET,
    MODE_HYBRID_POLICY_ENFORCE,
    MODE_HYBRID_ZEROIZE,
    PROFILE_X25519_MLKEM768,
    PROFILE_SECP384R1_MLKEM1024,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_DEGENERATE_KEY,
    STATUS_ERR_POLICY_VIOLATION,
    STATUS_ERR_INVALID_PROFILE,
    STATUS_ERR_INTEGRITY_FAIL,
    DESC_TOTAL_BYTES,
    REQ_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr37_descriptor,
    pack_dr37_request,
    unpack_dr37_result,
    reference_dr37_oracle,
    hkdf_extract_and_expand_sha256,
)


class DR37HybridKemContractTests(unittest.TestCase):

    def test_01_constants_and_magic(self):
        """Validates architectural constants, magic headers, and buffer geometries."""
        self.assertEqual(MAGIC_HEADER, 0x454B3701)
        self.assertEqual(MAGIC_RESULT, 0x3733454B)
        self.assertEqual(DESC_TOTAL_BYTES, 64)
        self.assertEqual(REQ_TOTAL_BYTES, 16384)
        self.assertEqual(RESULT_TOTAL_BYTES, 2048)

        self.assertEqual(MODE_HYBRID_ENCAPS_COMBINE, 1)
        self.assertEqual(MODE_HYBRID_DECAPS_COMBINE, 2)
        self.assertEqual(MODE_HYBRID_SPLIT_SECRET, 3)
        self.assertEqual(MODE_HYBRID_POLICY_ENFORCE, 4)
        self.assertEqual(MODE_HYBRID_ZEROIZE, 5)

        self.assertEqual(PROFILE_X25519_MLKEM768, 1)
        self.assertEqual(PROFILE_SECP384R1_MLKEM1024, 2)

    def test_02_pack_unpack_descriptor(self):
        """Validates 64-byte descriptor layout and field packing."""
        desc = pack_dr37_descriptor(
            op_mode=MODE_HYBRID_ENCAPS_COMBINE,
            profile_id=PROFILE_X25519_MLKEM768,
            ss_c_len=32,
            ss_pqc_len=32,
            ct_c_len=32,
            ct_pqc_len=1088,
            flags=0x01,
            seq_id=42,
        )
        self.assertEqual(len(desc), DESC_TOTAL_BYTES)
        magic, mode, prof, ssc_l, sspqc_l, ctc_l, ctpqc_l, flg = struct.unpack_from("<IIIIIIII", desc, 0)
        seq = struct.unpack_from("<I", desc, 32)[0]

        self.assertEqual(magic, MAGIC_HEADER)
        self.assertEqual(mode, MODE_HYBRID_ENCAPS_COMBINE)
        self.assertEqual(prof, PROFILE_X25519_MLKEM768)
        self.assertEqual(ssc_l, 32)
        self.assertEqual(sspqc_l, 32)
        self.assertEqual(ctc_l, 32)
        self.assertEqual(ctpqc_l, 1088)
        self.assertEqual(flg, 0x01)
        self.assertEqual(seq, 42)

    def test_03_request_packing(self):
        """Validates 16KB request tensor packing and memory offsets."""
        c_ss = b"\x11" * 32
        pqc_ss = b"\x22" * 32
        c_ct = b"\x33" * 32
        salt = b"\x44" * 32
        pqc_ct = b"\x55" * 1088

        req = pack_dr37_request(
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
        )
        self.assertEqual(len(req), REQ_TOTAL_BYTES)
        self.assertEqual(req[0:32], c_ss)
        self.assertEqual(req[32:64], pqc_ss)
        self.assertEqual(req[64:96], c_ct)
        self.assertEqual(req[96:128], salt)
        self.assertEqual(req[128:128 + 1088], pqc_ct)

    def test_04_hybrid_combine_x25519_mlkem768(self):
        """Validates X25519 + ML-KEM-768 hybrid combiner derivation in reference oracle."""
        c_ss = bytes.fromhex("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
        pqc_ss = bytes.fromhex("fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210")
        c_ct = bytes.fromhex("a0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebf")
        salt = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
        pqc_ct = bytes([i % 256 for i in range(1088)])

        desc = pack_dr37_descriptor(
            op_mode=MODE_HYBRID_ENCAPS_COMBINE,
            profile_id=PROFILE_X25519_MLKEM768,
            ct_pqc_len=1088,
        )
        req = pack_dr37_request(
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
        )

        raw_res = reference_dr37_oracle(req, desc)
        self.assertEqual(len(raw_res), RESULT_TOTAL_BYTES)

        res = unpack_dr37_result(raw_res)
        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(res["op_mode"], MODE_HYBRID_ENCAPS_COMBINE)
        self.assertEqual(res["verification_outcome"], 1)
        self.assertEqual(res["cycle_estimate"], 720)

        # Check key sizes
        self.assertEqual(len(res["final_shared_secret"]), 32)
        self.assertEqual(len(res["derived_enc_key"]), 32)
        self.assertEqual(len(res["derived_mac_key"]), 32)
        self.assertEqual(len(res["derived_iv"]), 16)
        self.assertEqual(len(res["transcript_binding_digest"]), 32)

        # Ensure keys are non-zero and mutually distinct
        self.assertFalse(all(b == 0 for b in res["final_shared_secret"]))
        self.assertFalse(all(b == 0 for b in res["derived_enc_key"]))
        self.assertFalse(all(b == 0 for b in res["derived_mac_key"]))
        self.assertNotEqual(res["final_shared_secret"], res["derived_enc_key"])
        self.assertNotEqual(res["derived_enc_key"], res["derived_mac_key"])

    def test_05_hybrid_combine_secp384r1_mlkem1024(self):
        """Validates SecP384R1 + ML-KEM-1024 hybrid combiner derivation in reference oracle."""
        c_ss = bytes([0x77] * 32)
        pqc_ss = bytes([0x88] * 32)
        c_ct = bytes([0x99] * 32)
        salt = bytes([0xAA] * 32)
        pqc_ct = bytes([i % 251 for i in range(1568)])

        desc = pack_dr37_descriptor(
            op_mode=MODE_HYBRID_DECAPS_COMBINE,
            profile_id=PROFILE_SECP384R1_MLKEM1024,
            ct_pqc_len=1568,
        )
        req = pack_dr37_request(
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
        )

        raw_res = reference_dr37_oracle(req, desc)
        res = unpack_dr37_result(raw_res)
        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(res["op_mode"], MODE_HYBRID_DECAPS_COMBINE)
        self.assertEqual(res["cycle_estimate"], 950)
        self.assertEqual(len(res["final_shared_secret"]), 32)

    def test_06_degenerate_key_rejection(self):
        """Validates BSI TR-02102-1 fail-closed rejection of degenerate all-zero shared secrets."""
        zero_ss = bytes(32)
        valid_ss = bytes([0x42] * 32)

        # Case A: Classical shared secret is all zero
        desc = pack_dr37_descriptor(op_mode=MODE_HYBRID_ENCAPS_COMBINE)
        req = pack_dr37_request(classical_ss=zero_ss, pqc_ss=valid_ss)
        raw_res = reference_dr37_oracle(req, desc)
        res = unpack_dr37_result(raw_res)
        self.assertEqual(res["status"], STATUS_ERR_DEGENERATE_KEY)
        self.assertEqual(res["verification_outcome"], 0)

        # Case B: PQC shared secret is all zero
        req2 = pack_dr37_request(classical_ss=valid_ss, pqc_ss=zero_ss)
        raw_res2 = reference_dr37_oracle(req2, desc)
        res2 = unpack_dr37_result(raw_res2)
        self.assertEqual(res2["status"], STATUS_ERR_DEGENERATE_KEY)
        self.assertEqual(res2["verification_outcome"], 0)

    def test_07_zeroize_mode(self):
        """Validates Zeroize mode unconditionally sets all secret keys to zero."""
        desc = pack_dr37_descriptor(op_mode=MODE_HYBRID_ZEROIZE)
        req = pack_dr37_request(classical_ss=bytes([0xFF] * 32), pqc_ss=bytes([0xFF] * 32))
        raw_res = reference_dr37_oracle(req, desc)
        res = unpack_dr37_result(raw_res)
        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(res["op_mode"], MODE_HYBRID_ZEROIZE)
        self.assertTrue(all(b == 0 for b in res["final_shared_secret"]))
        self.assertTrue(all(b == 0 for b in res["derived_enc_key"]))
        self.assertTrue(all(b == 0 for b in res["derived_mac_key"]))
        self.assertTrue(all(b == 0 for b in res["derived_iv"]))

    def test_08_invalid_magic_and_profile(self):
        """Validates fail-closed handling of malformed magic headers and invalid profile IDs."""
        bad_desc = bytearray(pack_dr37_descriptor(op_mode=MODE_HYBRID_ENCAPS_COMBINE))
        struct.pack_into("<I", bad_desc, 0, 0xBAD00001)
        req = pack_dr37_request(classical_ss=bytes([1] * 32), pqc_ss=bytes([2] * 32))

        raw_res = reference_dr37_oracle(req, bytes(bad_desc))
        res = unpack_dr37_result(raw_res)
        self.assertEqual(res["status"], STATUS_ERR_INVALID_MAGIC)
        self.assertEqual(res["verification_outcome"], 0)

        bad_desc2 = bytearray(pack_dr37_descriptor(op_mode=MODE_HYBRID_ENCAPS_COMBINE, profile_id=99))
        raw_res2 = reference_dr37_oracle(req, bytes(bad_desc2))
        res2 = unpack_dr37_result(raw_res2)
        self.assertEqual(res2["status"], STATUS_ERR_INVALID_PROFILE)
        self.assertEqual(res2["verification_outcome"], 0)

    def test_09_hkdf_rfc5869_consistency(self):
        """Validates HKDF Extract-and-Expand against official RFC 5869 Test Case 1."""
        ikm = bytes.fromhex("0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b")
        salt = bytes.fromhex("000102030405060708090a0b0c")
        info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
        okm = hkdf_extract_and_expand_sha256(salt, ikm, info, 42)
        expected_okm = bytes.fromhex(
            "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"
        )
        self.assertEqual(okm, expected_okm)


if __name__ == "__main__":
    unittest.main()
