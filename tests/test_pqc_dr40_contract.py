# SPDX-License-Identifier: Apache-2.0
"""Contract and Unit Tests for Milestone DR40:
Reproducible High-Throughput Hardware Benchmark Protocol & Profiling Battery.
Execution Boundary: [HOST RUNTIME] / [HOST REFERENCE].
"""

import math
import struct
import unittest

from phoenix_sdr_dsp.pqc.dr40_benchmark_abi import (
    MAGIC_HEADER,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_UNSUPPORTED_MODE,
    STATUS_ERR_INVALID_BATCH,
    MODE_BENCH_NTT_BUTTERFLY,
    MODE_BENCH_KECCAK_F1600,
    MODE_BENCH_VECTOR_MAC,
    MODE_BENCH_SAMPLE_NTT,
    DESCRIPTOR_SIZE,
    REQUEST_BUFFER_SIZE,
    RESULT_BUFFER_SIZE,
    MODULUS_Q,
    BenchmarkDescriptor,
    BenchmarkResultHeader,
    compute_reference_oracle,
    calculate_benchmark_metrics,
    montgomery_reduce,
    ntt_butterfly_layer_ref,
    vector_mac_ref,
    keccak_round_ref,
    sample_ntt_ref,
)
from phoenix_sdr_dsp.pqc.dr40_benchmark_graph import get_kernel_artifact_info


class TestDR40Contract(unittest.TestCase):

    def test_descriptor_pack_unpack_roundtrip(self):
        desc = BenchmarkDescriptor(
            op_mode=MODE_BENCH_NTT_BUTTERFLY,
            batch_size=16,
            warmup_iters=4,
            flags=0x12,
            param_0=100,
            param_1=200,
            seq_id=42,
        )
        packed = desc.pack()
        self.assertEqual(len(packed), DESCRIPTOR_SIZE)
        unpacked = BenchmarkDescriptor.unpack(packed)
        self.assertEqual(unpacked.magic, MAGIC_HEADER)
        self.assertEqual(unpacked.op_mode, MODE_BENCH_NTT_BUTTERFLY)
        self.assertEqual(unpacked.batch_size, 16)
        self.assertEqual(unpacked.warmup_iters, 4)
        self.assertEqual(unpacked.flags, 0x12)
        self.assertEqual(unpacked.param_0, 100)
        self.assertEqual(unpacked.param_1, 200)
        self.assertEqual(unpacked.seq_id, 42)

    def test_result_header_unpack(self):
        buf = bytearray(RESULT_BUFFER_SIZE)
        struct.pack_into("<IIIII", buf, 0, STATUS_SUCCESS, MODE_BENCH_VECTOR_MAC, 32, 34, 0xABCD1234)
        buf[32:36] = b"\x01\x02\x03\x04"
        res = BenchmarkResultHeader.unpack(bytes(buf))
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.op_mode, MODE_BENCH_VECTOR_MAC)
        self.assertEqual(res.batch_size, 32)
        self.assertEqual(res.iterations_completed, 34)
        self.assertEqual(res.checksum, 0xABCD1234)
        self.assertEqual(res.payload[:4], b"\x01\x02\x03\x04")

    def test_invalid_batch_size_oracle(self):
        req = bytes(REQUEST_BUFFER_SIZE)
        res = compute_reference_oracle(MODE_BENCH_NTT_BUTTERFLY, req, batch_size=0)
        self.assertEqual(res.status, STATUS_ERR_INVALID_BATCH)

        res_neg = compute_reference_oracle(MODE_BENCH_NTT_BUTTERFLY, req, batch_size=-5)
        self.assertEqual(res_neg.status, STATUS_ERR_INVALID_BATCH)

    def test_unsupported_mode_oracle(self):
        req = bytes(REQUEST_BUFFER_SIZE)
        res = compute_reference_oracle(0x9999, req, batch_size=10)
        self.assertEqual(res.status, STATUS_ERR_UNSUPPORTED_MODE)

    def test_ntt_butterfly_oracle_deterministic(self):
        # 256 uint16 test polynomial
        poly_in = [(i * 13 + 5) % MODULUS_Q for i in range(256)]
        req = bytearray(REQUEST_BUFFER_SIZE)
        for i, val in enumerate(poly_in):
            struct.pack_into("<H", req, i * 2, val)

        res1 = compute_reference_oracle(MODE_BENCH_NTT_BUTTERFLY, bytes(req), batch_size=4, warmup_iters=1)
        res2 = compute_reference_oracle(MODE_BENCH_NTT_BUTTERFLY, bytes(req), batch_size=4, warmup_iters=1)
        self.assertEqual(res1.status, STATUS_SUCCESS)
        self.assertEqual(res1.iterations_completed, 5)
        self.assertEqual(res1.checksum, res2.checksum)
        self.assertEqual(res1.payload[:512], res2.payload[:512])

    def test_keccak_f1600_oracle_deterministic(self):
        state_in = [i * 0x0123456789ABCDEF for i in range(25)]
        req = bytearray(REQUEST_BUFFER_SIZE)
        for i, val in enumerate(state_in):
            struct.pack_into("<Q", req, i * 8, val & 0xFFFFFFFFFFFFFFFF)

        res = compute_reference_oracle(MODE_BENCH_KECCAK_F1600, bytes(req), batch_size=2, warmup_iters=0, param_0=24)
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.iterations_completed, 2)
        self.assertNotEqual(res.checksum, 0)

    def test_vector_mac_oracle_deterministic(self):
        poly_a = [(i * 7 + 1) % MODULUS_Q for i in range(256)]
        poly_b = [(i * 11 + 3) % MODULUS_Q for i in range(256)]
        req = bytearray(REQUEST_BUFFER_SIZE)
        for i in range(256):
            struct.pack_into("<H", req, i * 2, poly_a[i])
            struct.pack_into("<H", req, 512 + i * 2, poly_b[i])

        res = compute_reference_oracle(MODE_BENCH_VECTOR_MAC, bytes(req), batch_size=8, warmup_iters=2)
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.iterations_completed, 10)
        self.assertNotEqual(res.checksum, 0)

    def test_sample_ntt_oracle_deterministic(self):
        seed = bytes([(i * 31) & 0xFF for i in range(768)])
        req = seed + bytes(REQUEST_BUFFER_SIZE - len(seed))
        res = compute_reference_oracle(MODE_BENCH_SAMPLE_NTT, req, batch_size=4, warmup_iters=1)
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.iterations_completed, 5)
        self.assertNotEqual(res.checksum, 0)

    def test_benchmark_metrics_calculation(self):
        durations = [100.0, 102.0, 98.0, 105.0, 95.0]  # mean = 100.0 us
        metrics = calculate_benchmark_metrics(
            op_mode=MODE_BENCH_NTT_BUTTERFLY,
            batch_size=10,
            durations_us=durations,
            bytes_per_op=512,
        )
        self.assertEqual(metrics.batch_size, 10)
        self.assertAlmostEqual(metrics.mean_us, 100.0, places=2)
        self.assertAlmostEqual(metrics.median_us, 100.0, places=2)
        self.assertEqual(metrics.min_us, 95.0)
        self.assertEqual(metrics.max_us, 105.0)
        self.assertLess(metrics.cv_percent, 10.0)  # low variation
        self.assertGreater(metrics.ops_per_second, 0.0)
        self.assertGreater(metrics.throughput_mbs, 0.0)

    def test_kernel_artifact_info(self):
        info = get_kernel_artifact_info()
        self.assertIn("path", info)
        self.assertIn("size_bytes", info)
        self.assertIn("sha256", info)
        self.assertGreater(info["size_bytes"], 0)
        self.assertEqual(len(info["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
