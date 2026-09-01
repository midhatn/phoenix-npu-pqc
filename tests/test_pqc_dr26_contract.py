# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR26:
AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling on AMD Phoenix AIE2.
"""

import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc.dr26_multi_arch_abi import (
    MAGIC_DESC_DR26,
    ARCH_PHOENIX_XDNA1,
    ARCH_STRIX_XDNA2,
    ARCH_ALVEO_V70,
    MODE_QUERY_ARCH_TOPOLOGY,
    MODE_VALIDATE_GRID_FIT,
    MODE_PARTITION_COLUMNS,
    MODE_EMIT_MLIR_TOPOLOGY,
    pack_dr26_descriptor,
    unpack_dr26_descriptor,
)
from phoenix_sdr_dsp.pqc.dr26_multi_arch_graph import (
    get_kernel_artifact_info,
    ref_query_arch_topology,
    ref_validate_grid_fit,
    ref_partition_columns,
    ref_emit_mlir_topology,
)


class DR26MultiArchContractTests(unittest.TestCase):

    def test_01_descriptor_packing(self):
        """Validates 32-byte hardware descriptor serialization for DR26."""
        desc = pack_dr26_descriptor(
            operation_mode=MODE_PARTITION_COLUMNS,
            target_arch=ARCH_STRIX_XDNA2,
            requested_tiles=4,
            epoch=88,
        )
        self.assertEqual(len(desc), 32)
        parsed = unpack_dr26_descriptor(desc)
        self.assertEqual(parsed.magic, MAGIC_DESC_DR26)
        self.assertEqual(parsed.operation_mode, MODE_PARTITION_COLUMNS)
        self.assertEqual(parsed.target_arch, ARCH_STRIX_XDNA2)
        self.assertEqual(parsed.requested_tiles, 4)
        self.assertEqual(parsed.epoch, 88)

    def test_02_kernel_artifact_info(self):
        """Validates DR26 AIE2 kernel source artifact digest."""
        repo_root = Path(__file__).resolve().parents[1]
        info = get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_ref_query_arch_topology(self):
        """Validates reference query for Phoenix, Strix Point, and Alveo V70."""
        p_geom = ref_query_arch_topology(ARCH_PHOENIX_XDNA1)
        self.assertEqual(p_geom["rows"], 4)
        self.assertEqual(p_geom["cols"], 5)
        self.assertEqual(p_geom["total_tiles"], 20)

        s_geom = ref_query_arch_topology(ARCH_STRIX_XDNA2)
        self.assertEqual(s_geom["rows"], 4)
        self.assertEqual(s_geom["cols"], 8)
        self.assertEqual(s_geom["total_tiles"], 32)
        self.assertEqual(s_geom["peak_tops"], 50)

        a_geom = ref_query_arch_topology(ARCH_ALVEO_V70)
        self.assertEqual(a_geom["rows"], 8)
        self.assertEqual(a_geom["cols"], 38)
        self.assertEqual(a_geom["total_tiles"], 304)

    def test_04_ref_validate_grid_fit(self):
        """Validates spatial bounds checks."""
        # 4 tiles fit on Phoenix (total 20 tiles) -> 5 concurrent pipelines
        ok, max_c = ref_validate_grid_fit(ARCH_PHOENIX_XDNA1, 4)
        self.assertTrue(ok)
        self.assertEqual(max_c, 5)

        # 30 tiles exceed Phoenix (20 tiles)
        ok, _ = ref_validate_grid_fit(ARCH_PHOENIX_XDNA1, 30)
        self.assertFalse(ok)

        # 30 tiles fit on Strix Point (32 tiles)
        ok, max_c = ref_validate_grid_fit(ARCH_STRIX_XDNA2, 30)
        self.assertTrue(ok)
        self.assertEqual(max_c, 1)

    def test_05_ref_partition_columns(self):
        """Validates spatial column partitioning."""
        # Partition Strix Point (8 columns) across 4 pipelines -> 2 columns each
        parts = ref_partition_columns(ARCH_STRIX_XDNA2, 4)
        self.assertEqual(len(parts), 4)
        total_cols = sum(num for _, num in parts)
        self.assertEqual(total_cols, 8)

    def test_06_ref_emit_mlir_topology(self):
        """Validates multi-target MLIR device topology vector."""
        topo = ref_emit_mlir_topology(ARCH_ALVEO_V70)
        self.assertEqual(topo["magic"], 0x4D4C4952)
        self.assertEqual(topo["total_tiles"], 304)
        self.assertEqual(topo["shim_rows"], 2)


if __name__ == "__main__":
    unittest.main()
