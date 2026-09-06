# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR38:
NIST SP 800-22 Randomness Statistical Battery & BSI AIS 31 Hardware Diagnostic.
"""

import unittest
import struct
import numpy as np

from phoenix_sdr_dsp.pqc.dr38_randomness_abi import (
    MAGIC_HEADER,
    MAGIC_RESULT,
    MODE_EVAL_MONOBIT,
    MODE_EVAL_POKER,
    MODE_EVAL_RUNS_LONGEST,
    MODE_EVAL_SHANNON_ENTROPY,
    MODE_EVAL_FULL_BATTERY,
    MODE_EVAL_HEALTH_TEST,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_INSUFFICIENT_LEN,
    STATUS_ERR_TEST_FAILED,
    STATUS_ERR_HEALTH_FAILURE,
    DESC_TOTAL_BYTES,
    REQ_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr38_descriptor,
    pack_dr38_request,
    unpack_dr38_result,
    reference_dr38_oracle,
    compute_monobit_p_value,
    compute_runs_p_value,
    compute_poker_statistic,
    compute_shannon_entropy,
)


class DR38RandomnessBatteryContractTests(unittest.TestCase):

    def test_01_constants_and_magic(self):
        """Validates architectural constants, magic headers, and buffer geometries."""
        self.assertEqual(MAGIC_HEADER, 0x54533801)
        self.assertEqual(MAGIC_RESULT, 0x38335354)
        self.assertEqual(DESC_TOTAL_BYTES, 64)
        self.assertEqual(REQ_TOTAL_BYTES, 16384)
        self.assertEqual(RESULT_TOTAL_BYTES, 2048)

        self.assertEqual(MODE_EVAL_MONOBIT, 1)
        self.assertEqual(MODE_EVAL_POKER, 2)
        self.assertEqual(MODE_EVAL_RUNS_LONGEST, 3)
        self.assertEqual(MODE_EVAL_SHANNON_ENTROPY, 4)
        self.assertEqual(MODE_EVAL_FULL_BATTERY, 5)
        self.assertEqual(MODE_EVAL_HEALTH_TEST, 6)

    def test_02_pack_unpack_descriptor(self):
        """Validates 64-byte descriptor layout and field packing."""
        desc = pack_dr38_descriptor(
            op_mode=MODE_EVAL_FULL_BATTERY,
            sample_bytes_len=16384,
            block_size=128,
            flags=0x01,
            seq_id=99,
        )
        self.assertEqual(len(desc), DESC_TOTAL_BYTES)
        magic, mode, slen, bsize, flg, _, _, _ = struct.unpack_from("<IIIIIIII", desc, 0)
        seq = struct.unpack_from("<I", desc, 32)[0]

        self.assertEqual(magic, MAGIC_HEADER)
        self.assertEqual(mode, MODE_EVAL_FULL_BATTERY)
        self.assertEqual(slen, 16384)
        self.assertEqual(bsize, 128)
        self.assertEqual(flg, 0x01)
        self.assertEqual(seq, 99)

    def test_03_request_packing(self):
        """Validates 16KB request tensor packing and bounds."""
        sample = b"\x5A" * 1000
        req = pack_dr38_request(sample_bytes=sample, seq_id=1)
        self.assertEqual(len(req), REQ_TOTAL_BYTES)
        self.assertEqual(req[:1000], sample)
        self.assertTrue(all(b == 0 for b in req[1000:]))

    def test_04_monobit_and_poker_uniform(self):
        """Validates Monobit and Poker tests on pseudorandom sample block."""
        rng = np.random.default_rng(seed=0x12345678)
        sample = bytes(rng.integers(0, 256, size=16384, dtype=np.uint8))

        desc = pack_dr38_descriptor(op_mode=MODE_EVAL_MONOBIT, sample_bytes_len=16384)
        req = pack_dr38_request(sample)
        raw_res = reference_dr38_oracle(req, desc)
        self.assertEqual(len(raw_res), RESULT_TOTAL_BYTES)

        res = unpack_dr38_result(raw_res)
        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(res["op_mode"], MODE_EVAL_MONOBIT)
        self.assertEqual(res["verification_outcome"], 1)
        self.assertTrue(res["monobit_passed"])
        self.assertTrue(res["poker_passed"])

    def test_05_runs_and_longest_run_uniform(self):
        """Validates Runs and Longest Run tests on pseudorandom sample block."""
        rng = np.random.default_rng(seed=0x87654321)
        sample = bytes(rng.integers(0, 256, size=16384, dtype=np.uint8))

        desc = pack_dr38_descriptor(op_mode=MODE_EVAL_RUNS_LONGEST, sample_bytes_len=16384)
        req = pack_dr38_request(sample)
        raw_res = reference_dr38_oracle(req, desc)
        res = unpack_dr38_result(raw_res)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertTrue(res["runs_passed"])
        self.assertTrue(res["longest_run_passed"])
        self.assertLessEqual(res["longest_run_ones"], 34)
        self.assertLessEqual(res["longest_run_zeros"], 34)

    def test_06_shannon_entropy_calculation(self):
        """Validates Shannon entropy calculation on uniform random distribution."""
        rng = np.random.default_rng(seed=0xCAFEF00D)
        sample = bytes(rng.integers(0, 256, size=16384, dtype=np.uint8))

        desc = pack_dr38_descriptor(op_mode=MODE_EVAL_SHANNON_ENTROPY, sample_bytes_len=16384)
        req = pack_dr38_request(sample)
        raw_res = reference_dr38_oracle(req, desc)
        res = unpack_dr38_result(raw_res)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertTrue(res["entropy_passed"])

        entropy = compute_shannon_entropy(res["histogram_256"], 16384)
        self.assertGreaterEqual(entropy, 7.95)

    def test_07_biased_stream_rejection(self):
        """Validates fail-closed rejection of non-random, heavily biased bitstreams."""
        # 90% zeros, 10% ones
        biased_sample = bytes([0x00] * 14000 + [0xFF] * 2384)

        desc = pack_dr38_descriptor(op_mode=MODE_EVAL_FULL_BATTERY, sample_bytes_len=16384)
        req = pack_dr38_request(biased_sample)
        raw_res = reference_dr38_oracle(req, desc)
        res = unpack_dr38_result(raw_res)

        self.assertEqual(res["status"], STATUS_ERR_TEST_FAILED)
        self.assertEqual(res["verification_outcome"], 0)
        self.assertFalse(res["monobit_passed"])

    def test_08_health_test_repetition_failure(self):
        """Validates continuous health test detection of stuck byte / catastrophic collapse."""
        stuck_sample = bytes([0x42] * 16384)

        desc = pack_dr38_descriptor(op_mode=MODE_EVAL_HEALTH_TEST, sample_bytes_len=16384)
        req = pack_dr38_request(stuck_sample)
        raw_res = reference_dr38_oracle(req, desc)
        res = unpack_dr38_result(raw_res)

        self.assertEqual(res["status"], STATUS_ERR_HEALTH_FAILURE)
        self.assertEqual(res["verification_outcome"], 0)
        self.assertEqual(res["health_flags"], 1)

    def test_09_invalid_magic_handling(self):
        """Validates fail-closed rejection of corrupted descriptor magic."""
        bad_desc = bytearray(pack_dr38_descriptor(op_mode=MODE_EVAL_FULL_BATTERY))
        struct.pack_into("<I", bad_desc, 0, 0xBAD00002)

        raw_res = reference_dr38_oracle(bytes(REQ_TOTAL_BYTES), bytes(bad_desc))
        res = unpack_dr38_result(raw_res)
        self.assertEqual(res["status"], STATUS_ERR_INVALID_MAGIC)
        self.assertEqual(res["verification_outcome"], 0)

    def test_10_sixty_four_symbol_stream_fail_closed_rejection(self):
        """Validates fail-closed rejection of 64-symbol stream (H=6.0 bits/byte) that evaded old heuristic."""
        # 64 unique symbols each occurring 256 times in 16384 bytes
        stream_64 = bytes([i % 64 for i in range(16384)])
        desc = pack_dr38_descriptor(op_mode=MODE_EVAL_SHANNON_ENTROPY, sample_bytes_len=16384)
        req = pack_dr38_request(stream_64)
        raw_res = reference_dr38_oracle(req, desc)
        res = unpack_dr38_result(raw_res)

        self.assertEqual(res["status"], STATUS_ERR_TEST_FAILED)
        self.assertEqual(res["verification_outcome"], 0)
        self.assertFalse(res["entropy_passed"])
        entropy = compute_shannon_entropy(res["histogram_256"], 16384)
        self.assertAlmostEqual(entropy, 6.0, places=4)


if __name__ == "__main__":
    unittest.main()
