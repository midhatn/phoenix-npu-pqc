# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR24:
RFC 9370 Multi-KEM IPsec / WireGuard Inline VPN Co-Processor on AMD Phoenix AIE2.
"""

import unittest
import os
from pathlib import Path

from phoenix_sdr_dsp.pqc.dr24_ipsec_wireguard_abi import (
    MAGIC_DESC_DR24,
    MODE_RFC9370_COMBINE,
    MODE_WIREGUARD_ENCAPS,
    MODE_WIREGUARD_DECAPS,
    MODE_ASYNC_REKEY,
    pack_dr24_descriptor,
    unpack_dr24_descriptor,
)
from phoenix_sdr_dsp.pqc.dr24_ipsec_wireguard_graph import (
    get_kernel_artifact_info,
    ref_rfc9370_combine,
    ref_wireguard_encaps,
    ref_wireguard_decaps,
    ref_async_rekey,
)


class DR24IpsecWireGuardContractTests(unittest.TestCase):

    def test_01_descriptor_packing(self):
        """Validates 32-byte hardware descriptor serialization for DR24."""
        desc = pack_dr24_descriptor(
            operation_mode=MODE_WIREGUARD_ENCAPS,
            payload_len=1420,
            seq_num=0x123456789ABC,
            epoch=42,
            kem_mode=1,
        )
        self.assertEqual(len(desc), 32)
        parsed = unpack_dr24_descriptor(desc)
        self.assertEqual(parsed.magic, MAGIC_DESC_DR24)
        self.assertEqual(parsed.operation_mode, MODE_WIREGUARD_ENCAPS)
        self.assertEqual(parsed.payload_len, 1420)
        self.assertEqual(parsed.seq_num, 0x123456789ABC)
        self.assertEqual(parsed.epoch, 42)
        self.assertEqual(parsed.kem_mode, 1)

    def test_02_kernel_artifact_info(self):
        """Validates DR24 AIE2 kernel source artifact digest."""
        repo_root = Path(__file__).resolve().parents[1]
        info = get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)

    def test_03_reference_rfc9370_combiner(self):
        """Validates reference RFC 9370 Multi-KEM combiner."""
        k_classic = b"\x11" * 32
        k_pqc = b"\x22" * 32
        k_qkd = b"\x33" * 32
        ni_nr = b"\x44" * 64

        ske, ska, skd = ref_rfc9370_combine(k_classic, k_pqc, k_qkd, ni_nr)
        self.assertEqual(len(ske), 32)
        self.assertEqual(len(ska), 32)
        self.assertEqual(len(skd), 32)
        self.assertNotEqual(ske, ska)
        self.assertNotEqual(ska, skd)

    def test_04_reference_wireguard_roundtrip(self):
        """Validates reference WireGuard encapsulation and decapsulation."""
        ske = b"\x55" * 32
        ska = b"\x66" * 32
        seq_num = 101
        payload = b"RFC 9370 IPsec/WireGuard test payload"

        packet = ref_wireguard_encaps(ske, ska, seq_num, payload)
        self.assertEqual(len(packet), 24 + len(payload))

        dec_seq, dec_payload, status = ref_wireguard_decaps(ske, ska, packet)
        self.assertEqual(status, 0)
        self.assertEqual(dec_seq, seq_num)
        self.assertEqual(dec_payload, payload)

    def test_05_reference_wireguard_tampered(self):
        """Validates detection of packet tampering in reference WireGuard decaps."""
        ske = b"\x55" * 32
        ska = b"\x66" * 32
        seq_num = 102
        payload = b"Secret data"

        packet = bytearray(ref_wireguard_encaps(ske, ska, seq_num, payload))
        packet[25] ^= 0xFF  # Corrupt ciphertext byte
        _, _, status = ref_wireguard_decaps(ske, ska, bytes(packet))
        self.assertEqual(status, 2)  # Auth failure


if __name__ == "__main__":
    unittest.main()
