# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR29:
NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine on AMD Phoenix AIE2.
"""

import unittest
from pathlib import Path
import numpy as np

from phoenix_sdr_dsp.pqc.dr29_cnsa_distributed_abi import (
    MAGIC_DESC_DR29,
    CNSA_ALGO_MLDSA87,
    CNSA_ALGO_MLKEM1024,
    MODE_DISTRIBUTED_PARTITION,
    MODE_DISTRIBUTED_ROW_ACCUM,
    MODE_CLUSTER_AGGREGATE,
    pack_dr29_descriptor,
    unpack_dr29_descriptor,
)
from phoenix_sdr_dsp.pqc.dr29_cnsa_distributed_graph import (
    get_kernel_artifact_info,
    ref_compute_partition_info,
    ref_compute_row_accum,
    ref_aggregate_cluster,
)


class DR29CnsaDistributedContractTests(unittest.TestCase):

    def test_01_descriptor_packing(self):
        """Validates 32-byte hardware descriptor serialization for DR29."""
        desc = pack_dr29_descriptor(
            operation_mode=MODE_DISTRIBUTED_ROW_ACCUM,
            algo_type=CNSA_ALGO_MLDSA87,
            tile_index=2,
            num_tiles=4,
            epoch=111,
        )
        self.assertEqual(len(desc), 32)
        parsed = unpack_dr29_descriptor(desc)
        self.assertEqual(parsed.magic, MAGIC_DESC_DR29)
        self.assertEqual(parsed.operation_mode, MODE_DISTRIBUTED_ROW_ACCUM)
        self.assertEqual(parsed.algo_type, CNSA_ALGO_MLDSA87)
        self.assertEqual(parsed.tile_index, 2)
        self.assertEqual(parsed.num_tiles, 4)
        self.assertEqual(parsed.epoch, 111)

    def test_02_kernel_artifact_info(self):
        """Validates DR29 AIE2 kernel source artifact digest."""
        repo_root = Path(__file__).resolve().parents[1]
        info = get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_ref_partition_mldsa87(self):
        """Validates 4-tile cluster partitioning for ML-DSA-87."""
        # Tile 0 covers rows 0-1 (2 rows * 7 columns = 14 polynomials)
        t0 = ref_compute_partition_info(CNSA_ALGO_MLDSA87, tile_index=0, num_tiles=4)
        self.assertEqual(t0["start_row"], 0)
        self.assertEqual(t0["num_rows"], 2)
        self.assertEqual(t0["polys_on_tile"], 14)
        self.assertTrue(t0["is_under_44kb_bound"])
        self.assertLessEqual(t0["total_sram_kb"], 44)

        # Tile 3 covers rows 6-7
        t3 = ref_compute_partition_info(CNSA_ALGO_MLDSA87, tile_index=3, num_tiles=4)
        self.assertEqual(t3["start_row"], 6)
        self.assertEqual(t3["num_rows"], 2)
        self.assertEqual(t3["polys_on_tile"], 14)

    def test_04_ref_partition_mlkem1024(self):
        """Validates 4-tile cluster partitioning for ML-KEM-1024."""
        t2 = ref_compute_partition_info(CNSA_ALGO_MLKEM1024, tile_index=2, num_tiles=4)
        self.assertEqual(t2["start_row"], 2)
        self.assertEqual(t2["num_rows"], 1)
        self.assertEqual(t2["polys_on_tile"], 4)
        self.assertTrue(t2["is_under_44kb_bound"])
        self.assertLessEqual(t2["total_sram_kb"], 10)

    def test_05_ref_row_accum_mldsa87(self):
        """Validates ML-DSA-87 row accumulation reference."""
        rng = np.random.default_rng(seed=0x2901)
        m = rng.integers(0, 8380417, size=(7, 256), dtype=np.uint32)
        s = rng.integers(0, 8380417, size=(7, 256), dtype=np.uint32)
        accum = ref_compute_row_accum(CNSA_ALGO_MLDSA87, m, s)
        self.assertEqual(accum.shape, (256,))
        self.assertTrue(np.all(accum < 8380417))

    def test_06_ref_row_accum_mlkem1024(self):
        """Validates ML-KEM-1024 row accumulation reference."""
        rng = np.random.default_rng(seed=0x2902)
        m = rng.integers(0, 3329, size=(4, 256), dtype=np.uint16)
        s = rng.integers(0, 3329, size=(4, 256), dtype=np.uint16)
        accum = ref_compute_row_accum(CNSA_ALGO_MLKEM1024, m, s)
        self.assertEqual(accum.shape, (256,))
        self.assertTrue(np.all(accum < 3329))


if __name__ == "__main__":
    unittest.main()
