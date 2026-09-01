# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR25:
Higher-Order Masking & On-Chip Local PRNG Entropy Expansion on AMD Phoenix AIE2.
"""

import unittest
from pathlib import Path
import numpy as np

from phoenix_sdr_dsp.pqc.dr25_masking_prng_abi import (
    MAGIC_DESC_DR25,
    MODE_PRNG_EXPAND,
    MODE_MASK_1ST_ORDER,
    MODE_MASK_2ND_ORDER,
    MODE_UNMASK_1ST_ORDER,
    MODE_UNMASK_2ND_ORDER,
    MODE_SNI_REFRESH_1ST,
    MODE_SNI_REFRESH_2ND,
    MODULUS_MLKEM,
    pack_dr25_descriptor,
    unpack_dr25_descriptor,
)
from phoenix_sdr_dsp.pqc.dr25_masking_prng_graph import (
    get_kernel_artifact_info,
    ref_prng_expand_mask,
    ref_mask_1st_order,
    ref_mask_2nd_order,
    ref_unmask_1st_order,
    ref_unmask_2nd_order,
    ref_masked_add_1st,
    ref_sni_refresh_1st,
    ref_sni_refresh_2nd,
)


class DR25MaskingPrngContractTests(unittest.TestCase):

    def test_01_descriptor_packing(self):
        """Validates 32-byte hardware descriptor serialization for DR25."""
        desc = pack_dr25_descriptor(
            operation_mode=MODE_MASK_2ND_ORDER,
            modulus=MODULUS_MLKEM,
            num_coeffs=256,
            epoch=77,
        )
        self.assertEqual(len(desc), 32)
        parsed = unpack_dr25_descriptor(desc)
        self.assertEqual(parsed.magic, MAGIC_DESC_DR25)
        self.assertEqual(parsed.operation_mode, MODE_MASK_2ND_ORDER)
        self.assertEqual(parsed.modulus, MODULUS_MLKEM)
        self.assertEqual(parsed.num_coeffs, 256)
        self.assertEqual(parsed.epoch, 77)

    def test_02_kernel_artifact_info(self):
        """Validates DR25 AIE2 kernel source artifact digest."""
        repo_root = Path(__file__).resolve().parents[1]
        info = get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_ref_prng_expand_mask(self):
        """Validates reference PRNG mask expansion."""
        seed = b"\x12" * 32
        mask = ref_prng_expand_mask(seed, domain_sep=1, modulus=MODULUS_MLKEM, num_coeffs=256)
        self.assertEqual(len(mask), 256)
        self.assertTrue(np.all(mask >= 0))
        self.assertTrue(np.all(mask < MODULUS_MLKEM))

    def test_04_ref_mask_unmask_1st_order(self):
        """Validates 1st-order polynomial blinding and unmasking exact recovery."""
        s = np.arange(256, dtype=np.uint16) % MODULUS_MLKEM
        mask = (np.arange(256, dtype=np.uint16) * 17) % MODULUS_MLKEM
        s0, s1 = ref_mask_1st_order(s, mask, MODULUS_MLKEM)
        rec_s = ref_unmask_1st_order(s0, s1, MODULUS_MLKEM)
        np.testing.assert_array_equal(rec_s, s)

    def test_05_ref_mask_unmask_2nd_order(self):
        """Validates 2nd-order polynomial blinding and unmasking exact recovery."""
        s = np.arange(256, dtype=np.uint16) % MODULUS_MLKEM
        mask1 = (np.arange(256, dtype=np.uint16) * 17) % MODULUS_MLKEM
        mask2 = (np.arange(256, dtype=np.uint16) * 31) % MODULUS_MLKEM
        s0, s1, s2 = ref_mask_2nd_order(s, mask1, mask2, MODULUS_MLKEM)
        rec_s = ref_unmask_2nd_order(s0, s1, s2, MODULUS_MLKEM)
        np.testing.assert_array_equal(rec_s, s)

    def test_06_ref_sni_refresh(self):
        """Validates that SNI share refresh preserves underlying secret."""
        s = np.arange(256, dtype=np.uint16) % MODULUS_MLKEM
        mask = (np.arange(256, dtype=np.uint16) * 17) % MODULUS_MLKEM
        s0, s1 = ref_mask_1st_order(s, mask, MODULUS_MLKEM)

        r = (np.arange(256, dtype=np.uint16) * 43) % MODULUS_MLKEM
        out_s0, out_s1 = ref_sni_refresh_1st(s0, s1, r, MODULUS_MLKEM)
        rec_s = ref_unmask_1st_order(out_s0, out_s1, MODULUS_MLKEM)
        np.testing.assert_array_equal(rec_s, s)


if __name__ == "__main__":
    unittest.main()
