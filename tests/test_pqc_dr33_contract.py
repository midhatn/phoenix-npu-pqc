# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR33:
Physical Side-Channel Power/EM Trace Acquisition & TVLA Framework.
"""

import unittest
import numpy as np

from phoenix_sdr_dsp.pqc.dr33_side_channel_tvla_abi import (
    MAGIC_DESC_DR33,
    MODE_TVLA_TRIGGER_EMIT,
    MODE_TVLA_FIXED_VS_RANDOM,
    MODE_TVLA_CALIBRATION_PULSE,
    MODE_TVLA_MASKED_PIPELINE,
    TARGET_ML_KEM_NTT,
    TARGET_ML_DSA_POLY,
    TARGET_KECCAK_F1600,
    TARGET_MASKED_MULT,
    PHASE_STOP_TRIGGER,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    REQ_TOTAL_BYTES,
    DESC_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    TVLA_DEFAULT_THRESHOLD,
    pack_dr33_descriptor,
    pack_dr33_request,
    unpack_dr33_result,
    compute_welch_ttest,
    generate_tvla_synthetic_traces,
    reference_dr33_oracle,
)


class DR33SideChannelTVLAContractTests(unittest.TestCase):

    def test_01_constants_and_magic(self):
        """Validates DR33 architectural constants, magic, and buffer geometries."""
        self.assertEqual(MAGIC_DESC_DR33, 0x54564C41)
        self.assertEqual(REQ_TOTAL_BYTES, 16384)
        self.assertEqual(DESC_TOTAL_BYTES, 64)
        self.assertEqual(RESULT_TOTAL_BYTES, 2048)
        self.assertEqual(TVLA_DEFAULT_THRESHOLD, 4.5)

    def test_02_pack_unpack_descriptor(self):
        """Validates descriptor structure packing and field layout."""
        desc = pack_dr33_descriptor(
            op_mode=MODE_TVLA_TRIGGER_EMIT,
            target_algo=TARGET_ML_KEM_NTT,
            seq_id=42,
            input_len=512,
            sample_rate_khz=50000,
            flags=0x01,
            trace_points=16,
        )
        self.assertEqual(len(desc), DESC_TOTAL_BYTES)
        import struct
        magic, mode, algo, seq, in_len, srate, flags, pts = struct.unpack_from("<IIIIIIII", desc, 0)
        self.assertEqual(magic, MAGIC_DESC_DR33)
        self.assertEqual(mode, MODE_TVLA_TRIGGER_EMIT)
        self.assertEqual(algo, TARGET_ML_KEM_NTT)
        self.assertEqual(seq, 42)
        self.assertEqual(in_len, 512)
        self.assertEqual(srate, 50000)
        self.assertEqual(flags, 0x01)
        self.assertEqual(pts, 16)

    def test_03_request_packing(self):
        """Validates request tensor packing and 32-byte alignment."""
        payload = b"\x11\x22\x33\x44" * 128
        req = pack_dr33_request(payload, seq_id=7, target_algo=TARGET_ML_DSA_POLY)
        self.assertEqual(len(req), REQ_TOTAL_BYTES)
        import struct
        magic, seq, algo, length = struct.unpack_from("<IIII", req, 0)
        self.assertEqual(magic, MAGIC_DESC_DR33)
        self.assertEqual(seq, 7)
        self.assertEqual(algo, TARGET_ML_DSA_POLY)
        self.assertEqual(length, len(payload))
        self.assertEqual(req[32 : 32 + len(payload)], payload)

    def test_04_welch_ttest_no_leakage(self):
        """Validates Welch's t-test over balanced fixed-vs-random traces with no leakage."""
        fixed_traces, random_traces = generate_tvla_synthetic_traces(
            num_traces=500,
            points_per_trace=64,
            inject_leakage=False,
        )
        res = compute_welch_ttest(fixed_traces, random_traces, threshold=4.5)
        self.assertEqual(res["execution_label"], "[HOST RUNTIME]")
        self.assertEqual(res["status"], "NO_LEAKAGE_DETECTED")
        self.assertFalse(res["leak_detected"])
        self.assertLess(res["max_abs_t"], 4.5)
        self.assertEqual(res["n_fixed"], 500)
        self.assertEqual(res["n_random"], 500)
        self.assertEqual(res["trace_points"], 64)

    def test_05_welch_ttest_with_injected_leakage(self):
        """Validates Welch's t-test successfully detects secret-dependent leakage above 4.5 threshold."""
        leak_idx = 28
        fixed_traces, random_traces = generate_tvla_synthetic_traces(
            num_traces=600,
            points_per_trace=64,
            inject_leakage=True,
            leak_point=leak_idx,
            leakage_magnitude=0.9,
        )
        res = compute_welch_ttest(fixed_traces, random_traces, threshold=4.5)
        self.assertEqual(res["execution_label"], "[HOST RUNTIME]")
        self.assertEqual(res["status"], "LEAKAGE_DETECTED")
        self.assertTrue(res["leak_detected"])
        self.assertGreater(res["max_abs_t"], 4.5)
        self.assertEqual(res["leakage_point"], leak_idx)

    def test_06_reference_oracle_and_result_unpack(self):
        """Validates reference oracle bit-exact generation and structured result unpacking."""
        desc = pack_dr33_descriptor(
            op_mode=MODE_TVLA_FIXED_VS_RANDOM,
            target_algo=TARGET_ML_KEM_NTT,
            seq_id=99,
            input_len=512,
        )
        req = pack_dr33_request(
            input_coeffs_or_seed=bytes([k % 256 for k in range(512)]),
            seq_id=99,
            target_algo=TARGET_ML_KEM_NTT,
        )
        oracle_out = reference_dr33_oracle(desc, req)
        self.assertEqual(len(oracle_out), RESULT_TOTAL_BYTES)

        unpacked = unpack_dr33_result(oracle_out)
        self.assertEqual(unpacked["magic"], MAGIC_DESC_DR33)
        self.assertEqual(unpacked["status"], STATUS_SUCCESS)
        self.assertEqual(unpacked["target_algo"], TARGET_ML_KEM_NTT)
        self.assertEqual(unpacked["seq_id"], 99)
        self.assertEqual(unpacked["trigger_phase"], PHASE_STOP_TRIGGER)
        self.assertTrue(unpacked["canary"].startswith(b"PQC33TVL"))
        self.assertEqual(len(unpacked["output_poly_bytes"]), 512)
        self.assertEqual(len(unpacked["trace_samples"]), 16)

    def test_07_negative_invalid_magic(self):
        """Validates fail-closed behavior on invalid magic descriptor."""
        bad_desc = bytearray(pack_dr33_descriptor())
        bad_desc[0:4] = b"BAD!"
        req = pack_dr33_request(b"\x00" * 512)
        oracle_out = reference_dr33_oracle(bytes(bad_desc), req)
        unpacked = unpack_dr33_result(oracle_out)
        self.assertEqual(unpacked["magic"], STATUS_ERR_INVALID_MAGIC)
        self.assertEqual(unpacked["status"], 1)


if __name__ == "__main__":
    unittest.main()
