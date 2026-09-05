# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR39:
dudect Side-Channel Timing & TVLA Constant-Time Diagnostic Engine.
"""

import unittest
import struct
import numpy as np

from phoenix_sdr_dsp.pqc.dr39_dudect_abi import (
    MAGIC_HEADER,
    MAGIC_RESULT,
    MODE_BENCH_CONSTANT_TIME_SELECT,
    MODE_BENCH_VARIABLE_TIME_BRANCH,
    MODE_BENCH_MONTGOMERY_REDUCTION,
    MODE_BENCH_POLYNOMIAL_ADD_SUB,
    MODE_BENCH_VARIABLE_TIME_EARLY_EXIT,
    MODE_BENCH_FULL_SUITE,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_INSUFFICIENT_LEN,
    STATUS_ERR_TIMING_LEAKAGE,
    STATUS_ERR_PARAM_OUT_OF_BOUNDS,
    DESC_TOTAL_BYTES,
    REQ_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    DUDECT_T_THRESHOLD,
    pack_dr39_descriptor,
    pack_dr39_request,
    unpack_dr39_result,
    compute_welch_t_statistic,
    dudect_evaluate_classes,
    reference_dr39_oracle,
)


class DR39DudectContractTests(unittest.TestCase):

    def test_01_constants_and_magic(self):
        """Validates architectural constants, magic headers, and buffer geometries."""
        self.assertEqual(MAGIC_HEADER, 0x54443901)
        self.assertEqual(MAGIC_RESULT, 0x39334454)
        self.assertEqual(DESC_TOTAL_BYTES, 64)
        self.assertEqual(REQ_TOTAL_BYTES, 4096)
        self.assertEqual(RESULT_TOTAL_BYTES, 2048)
        self.assertEqual(DUDECT_T_THRESHOLD, 4.5)

        self.assertEqual(MODE_BENCH_CONSTANT_TIME_SELECT, 1)
        self.assertEqual(MODE_BENCH_VARIABLE_TIME_BRANCH, 2)
        self.assertEqual(MODE_BENCH_MONTGOMERY_REDUCTION, 3)
        self.assertEqual(MODE_BENCH_POLYNOMIAL_ADD_SUB, 4)
        self.assertEqual(MODE_BENCH_VARIABLE_TIME_EARLY_EXIT, 5)
        self.assertEqual(MODE_BENCH_FULL_SUITE, 6)

    def test_02_pack_unpack_descriptor(self):
        """Validates 64-byte descriptor layout and field packing."""
        desc = pack_dr39_descriptor(
            op_mode=MODE_BENCH_FULL_SUITE,
            num_trials=1000,
            warmup_trials=50,
            flags=0x01,
            seq_id=42,
        )
        self.assertEqual(len(desc), DESC_TOTAL_BYTES)
        magic, mode, n_trials, warmup, flg, _, _, _ = struct.unpack_from("<IIIIIIII", desc, 0)
        seq = struct.unpack_from("<I", desc, 32)[0]

        self.assertEqual(magic, MAGIC_HEADER)
        self.assertEqual(mode, MODE_BENCH_FULL_SUITE)
        self.assertEqual(n_trials, 1000)
        self.assertEqual(warmup, 50)
        self.assertEqual(flg, 0x01)
        self.assertEqual(seq, 42)

    def test_03_request_packing(self):
        """Validates 4KB request tensor packing and seed bounds."""
        s0 = b"\x11" * 32
        s1 = b"\x22" * 32
        req = pack_dr39_request(class0_seed=s0, class1_seed=s1, seq_id=7)
        self.assertEqual(len(req), REQ_TOTAL_BYTES)
        self.assertEqual(req[:32], s0)
        self.assertEqual(req[32:64], s1)

    def test_04_constant_time_select_pass(self):
        """Validates constant-time selection passes without timing leakage (|t| <= 4.5)."""
        desc = pack_dr39_descriptor(op_mode=MODE_BENCH_CONSTANT_TIME_SELECT, num_trials=500)
        req = pack_dr39_request()
        raw_res = reference_dr39_oracle(req, desc)
        self.assertEqual(len(raw_res), RESULT_TOTAL_BYTES)

        res = unpack_dr39_result(raw_res)
        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(res["op_mode"], MODE_BENCH_CONSTANT_TIME_SELECT)
        self.assertEqual(res["verification_outcome"], 1)
        self.assertFalse(res["leakage_detected"])
        self.assertLessEqual(abs(res["max_t_statistic"]), DUDECT_T_THRESHOLD)

    def test_05_variable_time_branch_leakage_detected(self):
        """Validates variable-time branch correctly triggers leakage detection (|t| > 4.5)."""
        desc = pack_dr39_descriptor(op_mode=MODE_BENCH_VARIABLE_TIME_BRANCH, num_trials=500)
        req = pack_dr39_request()
        raw_res = reference_dr39_oracle(req, desc)
        res = unpack_dr39_result(raw_res)

        self.assertEqual(res["status"], STATUS_ERR_TIMING_LEAKAGE)
        self.assertEqual(res["op_mode"], MODE_BENCH_VARIABLE_TIME_BRANCH)
        self.assertEqual(res["verification_outcome"], 0)
        self.assertTrue(res["leakage_detected"])
        self.assertGreater(abs(res["max_t_statistic"]), DUDECT_T_THRESHOLD)

    def test_06_montgomery_reduction_constant_time(self):
        """Validates Montgomery reduction passes constant-time verification."""
        desc = pack_dr39_descriptor(op_mode=MODE_BENCH_MONTGOMERY_REDUCTION, num_trials=500)
        req = pack_dr39_request()
        raw_res = reference_dr39_oracle(req, desc)
        res = unpack_dr39_result(raw_res)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertFalse(res["leakage_detected"])
        self.assertLessEqual(abs(res["max_t_statistic"]), DUDECT_T_THRESHOLD)

    def test_07_polynomial_vector_arithmetic_constant_time(self):
        """Validates polynomial vector addition passes constant-time verification."""
        desc = pack_dr39_descriptor(op_mode=MODE_BENCH_POLYNOMIAL_ADD_SUB, num_trials=500)
        req = pack_dr39_request()
        raw_res = reference_dr39_oracle(req, desc)
        res = unpack_dr39_result(raw_res)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertFalse(res["leakage_detected"])
        self.assertLessEqual(abs(res["max_t_statistic"]), DUDECT_T_THRESHOLD)

    def test_08_variable_time_early_exit_leakage_detected(self):
        """Validates early-exit compare correctly triggers leakage detection (|t| > 4.5)."""
        desc = pack_dr39_descriptor(op_mode=MODE_BENCH_VARIABLE_TIME_EARLY_EXIT, num_trials=500)
        req = pack_dr39_request()
        raw_res = reference_dr39_oracle(req, desc)
        res = unpack_dr39_result(raw_res)

        self.assertEqual(res["status"], STATUS_ERR_TIMING_LEAKAGE)
        self.assertEqual(res["verification_outcome"], 0)
        self.assertTrue(res["leakage_detected"])
        self.assertGreater(abs(res["max_t_statistic"]), DUDECT_T_THRESHOLD)

    def test_09_full_suite_constant_time(self):
        """Validates full suite passes for verified constant-time routines."""
        desc = pack_dr39_descriptor(op_mode=MODE_BENCH_FULL_SUITE, num_trials=500)
        req = pack_dr39_request()
        raw_res = reference_dr39_oracle(req, desc)
        res = unpack_dr39_result(raw_res)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(res["verification_outcome"], 1)
        self.assertFalse(res["leakage_detected"])

    def test_10_percentile_cropping_evaluator(self):
        """Validates dudect percentile cropping evaluator on synthetic distributions."""
        rng = np.random.default_rng(seed=0x39393939)
        # Identical normal distributions with outliers
        base0 = rng.normal(loc=100.0, scale=2.0, size=1000).astype(int).tolist()
        base1 = rng.normal(loc=100.0, scale=2.0, size=1000).astype(int).tolist()

        is_ct, max_t, _ = dudect_evaluate_classes(base0, base1)
        self.assertTrue(is_ct)
        self.assertLessEqual(max_t, DUDECT_T_THRESHOLD)

        # Divergent distributions
        leaky1 = rng.normal(loc=120.0, scale=2.0, size=1000).astype(int).tolist()
        is_ct_bad, max_t_bad, _ = dudect_evaluate_classes(base0, leaky1)
        self.assertFalse(is_ct_bad)
        self.assertGreater(max_t_bad, DUDECT_T_THRESHOLD)

    def test_11_invalid_magic_handling(self):
        """Validates fail-closed rejection of corrupted descriptor magic."""
        bad_desc = bytearray(pack_dr39_descriptor(op_mode=MODE_BENCH_FULL_SUITE))
        struct.pack_into("<I", bad_desc, 0, 0xBAD00003)

        raw_res = reference_dr39_oracle(bytes(REQ_TOTAL_BYTES), bytes(bad_desc))
        res = unpack_dr39_result(raw_res)
        self.assertEqual(res["status"], STATUS_ERR_INVALID_MAGIC)
        self.assertEqual(res["verification_outcome"], 0)


if __name__ == "__main__":
    unittest.main()
