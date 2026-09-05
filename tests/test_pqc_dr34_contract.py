# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR34:
Hardware Root of Trust, TCG DICE / TPM Attestation & Enclave Security Boundaries.
"""

import unittest
import struct

from phoenix_sdr_dsp.pqc.dr34_dice_tpm_abi import (
    MAGIC_DESC_DR34,
    MODE_DICE_DERIVE_CDI,
    MODE_DICE_EXTEND_PCR,
    MODE_DICE_GENERATE_QUOTE,
    MODE_DICE_VERIFY_QUOTE,
    MODE_DICE_ENCLAVE_SEAL,
    PCR_0_FIRMWARE_BASE,
    PCR_1_TILE_DESCRIPTOR,
    PCR_2_SECURITY_CONFIG,
    PCR_COUNT,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_PCR_OUT_OF_BOUNDS,
    STATUS_ERR_QUOTE_VERIFY_FAIL,
    REQ_TOTAL_BYTES,
    DESC_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr34_descriptor,
    pack_dr34_request,
    unpack_dr34_result,
    reference_dr34_oracle,
)


class DR34DiceTpmAttestationContractTests(unittest.TestCase):

    def test_01_constants_and_magic(self):
        """Validates architectural constants, magic, and buffer geometries."""
        self.assertEqual(MAGIC_DESC_DR34, 0x44494345)
        self.assertEqual(REQ_TOTAL_BYTES, 16384)
        self.assertEqual(DESC_TOTAL_BYTES, 64)
        self.assertEqual(RESULT_TOTAL_BYTES, 2048)
        self.assertEqual(PCR_COUNT, 8)

    def test_02_pack_unpack_descriptor(self):
        """Validates descriptor structure packing and field layout."""
        desc = pack_dr34_descriptor(
            op_mode=MODE_DICE_GENERATE_QUOTE,
            pcr_index=PCR_1_TILE_DESCRIPTOR,
            pcr_mask=0x07,
            nonce_len=32,
            sig_len=64,
            flags=0x02,
            seq_id=12,
        )
        self.assertEqual(len(desc), DESC_TOTAL_BYTES)
        magic, mode, idx, mask, nlen, slen, flg, seq = struct.unpack_from("<IIIIIIII", desc, 0)
        self.assertEqual(magic, MAGIC_DESC_DR34)
        self.assertEqual(mode, MODE_DICE_GENERATE_QUOTE)
        self.assertEqual(idx, PCR_1_TILE_DESCRIPTOR)
        self.assertEqual(mask, 0x07)
        self.assertEqual(nlen, 32)
        self.assertEqual(slen, 64)
        self.assertEqual(flg, 0x02)
        self.assertEqual(seq, 12)

    def test_03_request_packing(self):
        """Validates request tensor packing and PCR bank offsets."""
        meas = b"\xAA" * 32
        nonce = b"\xBB" * 32
        exp_comp = b"\xCC" * 32
        pcr_bank = [bytes([p] * 32) for p in range(8)]
        uds = b"\xDD" * 32
        sig = b"\xEE" * 64

        req = pack_dr34_request(
            measurement=meas,
            nonce=nonce,
            expected_composite=exp_comp,
            initial_pcr_bank=pcr_bank,
            uds_key=uds,
            signature=sig,
            seq_id=5,
        )
        self.assertEqual(len(req), REQ_TOTAL_BYTES)
        magic, seq, mlen, nlen = struct.unpack_from("<IIII", req, 0)
        self.assertEqual(magic, MAGIC_DESC_DR34)
        self.assertEqual(seq, 5)
        self.assertEqual(req[32:64], meas)
        self.assertEqual(req[64:96], nonce)
        self.assertEqual(req[96:128], exp_comp)
        self.assertEqual(req[128:160], pcr_bank[0])
        self.assertEqual(req[384:416], uds)
        self.assertEqual(req[416:480], sig)

    def test_04_cdi_derivation(self):
        """Validates Compound Device Identifier (CDI) derivation from UDS and measurement."""
        uds = b"\x12\x34\x56\x78" * 8
        meas = b"\xFE\xDC\xBA\x98" * 8
        desc = pack_dr34_descriptor(op_mode=MODE_DICE_DERIVE_CDI)
        req = pack_dr34_request(measurement=meas, uds_key=uds)

        oracle_res = reference_dr34_oracle(desc, req)
        unpacked = unpack_dr34_result(oracle_res)

        self.assertEqual(unpacked["status"], STATUS_SUCCESS)
        self.assertEqual(unpacked["op_mode"], MODE_DICE_DERIVE_CDI)
        self.assertNotEqual(unpacked["cdi_or_seal"], bytes(32))
        self.assertTrue(unpacked["canary"].startswith(b"PQC34DICE_TPM_OK"))

    def test_05_pcr_extend_and_composite(self):
        """Validates PCR register extension and composite digest update."""
        init_pcr = [bytes(32) for _ in range(8)]
        meas = b"\x42" * 32
        desc = pack_dr34_descriptor(
            op_mode=MODE_DICE_EXTEND_PCR,
            pcr_index=PCR_0_FIRMWARE_BASE,
            pcr_mask=0x01,
        )
        req = pack_dr34_request(
            measurement=meas,
            initial_pcr_bank=init_pcr,
        )
        oracle_res = reference_dr34_oracle(desc, req)
        unpacked = unpack_dr34_result(oracle_res)

        self.assertEqual(unpacked["status"], STATUS_SUCCESS)
        self.assertNotEqual(unpacked["pcr_bank"][0], bytes(32))
        self.assertEqual(unpacked["pcr_bank"][1], bytes(32))
        self.assertNotEqual(unpacked["composite_digest"], bytes(32))

    def test_06_generate_and_verify_quote_success(self):
        """Validates round-trip quote generation and successful verification."""
        pcr_bank = [bytes([p + 1] * 32) for p in range(8)]
        nonce = b"\x77" * 32
        mask = 0x0F

        # 1. Generate Quote
        desc_gen = pack_dr34_descriptor(
            op_mode=MODE_DICE_GENERATE_QUOTE,
            pcr_mask=mask,
        )
        req_gen = pack_dr34_request(
            nonce=nonce,
            initial_pcr_bank=pcr_bank,
        )
        gen_res = reference_dr34_oracle(desc_gen, req_gen)
        unpacked_gen = unpack_dr34_result(gen_res)
        self.assertEqual(unpacked_gen["status"], STATUS_SUCCESS)

        comp_digest = unpacked_gen["composite_digest"]
        quote_digest = unpacked_gen["quote_digest"]

        # 2. Verify Quote with matching expected composite
        desc_ver = pack_dr34_descriptor(
            op_mode=MODE_DICE_VERIFY_QUOTE,
            pcr_mask=mask,
        )
        req_ver = pack_dr34_request(
            nonce=nonce,
            expected_composite=comp_digest,
            initial_pcr_bank=pcr_bank,
            signature=b"\x01" * 64,
        )
        ver_res = reference_dr34_oracle(desc_ver, req_ver)
        unpacked_ver = unpack_dr34_result(ver_res)

        self.assertEqual(unpacked_ver["status"], STATUS_SUCCESS)
        self.assertEqual(unpacked_ver["verification_outcome"], 1)
        self.assertEqual(unpacked_ver["quote_digest"], quote_digest)

    def test_07_verify_quote_mismatch_fails_closed(self):
        """Validates fail-closed behavior when expected composite PCR digest mismatches."""
        pcr_bank = [bytes([p + 1] * 32) for p in range(8)]
        nonce = b"\x77" * 32
        mask = 0x0F

        desc = pack_dr34_descriptor(op_mode=MODE_DICE_VERIFY_QUOTE, pcr_mask=mask)
        req = pack_dr34_request(
            nonce=nonce,
            expected_composite=b"\x99" * 32, # Incorrect expected composite
            initial_pcr_bank=pcr_bank,
        )
        ver_res = reference_dr34_oracle(desc, req)
        unpacked = unpack_dr34_result(ver_res)

        self.assertEqual(unpacked["status"], STATUS_ERR_QUOTE_VERIFY_FAIL)
        self.assertEqual(unpacked["verification_outcome"], 0)

    def test_08_tampered_signature_fails_closed(self):
        """Validates fail-closed behavior when attestation signature is tampered."""
        pcr_bank = [bytes([p + 1] * 32) for p in range(8)]
        nonce = b"\x77" * 32
        mask = 0x0F

        # Get golden composite
        desc_gen = pack_dr34_descriptor(op_mode=MODE_DICE_GENERATE_QUOTE, pcr_mask=mask)
        req_gen = pack_dr34_request(nonce=nonce, initial_pcr_bank=pcr_bank)
        gen_res = reference_dr34_oracle(desc_gen, req_gen)
        comp = unpack_dr34_result(gen_res)["composite_digest"]

        # Verify with tampered signature (0xFF marker)
        desc_ver = pack_dr34_descriptor(op_mode=MODE_DICE_VERIFY_QUOTE, pcr_mask=mask)
        req_ver = pack_dr34_request(
            nonce=nonce,
            expected_composite=comp,
            initial_pcr_bank=pcr_bank,
            signature=b"\xFF" + b"\x00" * 63,
        )
        ver_res = reference_dr34_oracle(desc_ver, req_ver)
        unpacked = unpack_dr34_result(ver_res)

        self.assertEqual(unpacked["status"], STATUS_ERR_QUOTE_VERIFY_FAIL)
        self.assertEqual(unpacked["verification_outcome"], 0)

    def test_09_negative_invalid_magic(self):
        """Validates fail-closed behavior on invalid magic descriptor."""
        bad_desc = bytearray(pack_dr34_descriptor())
        bad_desc[0:4] = b"NOPE"
        oracle_res = reference_dr34_oracle(bytes(bad_desc), bytes(REQ_TOTAL_BYTES))
        unpacked = unpack_dr34_result(oracle_res)
        self.assertEqual(unpacked["magic"], STATUS_ERR_INVALID_MAGIC)
        self.assertEqual(unpacked["status"], 1)


if __name__ == "__main__":
    unittest.main()
