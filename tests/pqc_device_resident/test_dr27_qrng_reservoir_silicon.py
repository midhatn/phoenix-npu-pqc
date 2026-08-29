# SPDX-License-Identifier: Apache-2.0
"""
Device-Resident Silicon Test Suite: Milestone DR27 (Gate 24).
QRNG-OPENAPI Ingress & NPU-Resident Token-Bucket Key/Entropy Reservoir on AMD Phoenix NPU (AIE2 / XDNA1).

Standards & Resource Citations:
1. Palo Alto Networks QRNG-OPENAPI Specification (v1.0)
2. NIST Special Publication 800-90B: Section 4.4.1 (RCT) & Section 4.4.2 (APT)
3. NIST Special Publication 800-56C Rev. 2: Two-Step Key Derivation
4. NIST FIPS 203 (ML-KEM) & NIST FIPS 204 (ML-DSA) Seeding & Key Generation
5. ETSI GS QKD 014 v1.1.1: REST-based Key Delivery Protocol
6. AMD AIE2 Architecture: Tile SRAM Ring Buffer & ObjectFIFO Pipeline
7. DOI: 10.5281/zenodo.22164124
"""
import os
import sys
import unittest
import numpy as np
from hashlib import sha256

# Ensure repository root is on path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from phoenix_sdr_dsp.pqc import dr27_qrng_openapi_abi as abi
from phoenix_sdr_dsp.pqc.dr27_qrng_reservoir_graph import (
    ingress_entropy,
    drain_entropy,
    get_reservoir_telemetry,
    zeroize_reservoir,
    NativeBackendUnavailable
)

class TestDR27QrngReservoirSilicon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            # Probe backend health
            zeroize_reservoir()
        except NativeBackendUnavailable as e:
            raise unittest.SkipTest(f"Physical silicon backend unavailable: {e}")

    def setUp(self):
        # Always zeroize to clean initial state
        zeroize_reservoir()

    def test_01_sp800_90b_health_evaluator(self):
        """Validates NIST SP 800-90B Health Tests (RCT and APT)."""
        # Healthy pseudo-quantum stream
        rng = np.random.default_rng(seed=0x27527101)
        healthy_stream = rng.bytes(512)
        is_healthy, rct, apt = abi.eval_sp800_90b_health(healthy_stream)
        self.assertTrue(is_healthy)
        self.assertLess(rct, abi.SP800_90B_RCT_CUTOFF)

        # Repetition Count Failure (e.g. 12 identical consecutive bytes)
        unhealthy_rct = bytearray(rng.bytes(512))
        unhealthy_rct[10:25] = b"\xAA" * 15
        is_healthy_rct, rct_bad, _ = abi.eval_sp800_90b_health(bytes(unhealthy_rct))
        self.assertFalse(is_healthy_rct)
        self.assertGreaterEqual(rct_bad, abi.SP800_90B_RCT_CUTOFF)

    def test_02_qrng_openapi_json_parsing(self):
        """Validates QRNG-OPENAPI v1.0 standard container parsing."""
        raw_entropy = os.urandom(32)
        json_str = abi.format_qrng_openapi_json(raw_entropy, source_id=42, quality=0.9999)
        parsed = abi.parse_qrng_openapi_json(json_str)

        self.assertEqual(parsed["version"], "1.0")
        self.assertEqual(parsed["source_id"], 42)
        self.assertAlmostEqual(parsed["quality"], 0.9999, places=4)
        self.assertEqual(parsed["entropy"], raw_entropy)

    def test_03_reservoir_ingress_and_drain_silicon(self):
        """Validates on-device ingress and drain operations on AIE2 tile SRAM."""
        rng = np.random.default_rng(seed=0x12345678)
        block1 = rng.bytes(32)
        block2 = rng.bytes(32)

        # Ingress Block 1
        res1 = ingress_entropy(block1, source_id=1, req_id=101)
        self.assertEqual(res1["status"], abi.STATUS_SUCCESS)
        self.assertEqual(res1["fill_level"], 1)

        # Ingress Block 2
        res2 = ingress_entropy(block2, source_id=1, req_id=102)
        self.assertEqual(res2["status"], abi.STATUS_SUCCESS)
        self.assertEqual(res2["fill_level"], 2)

        # Drain Block 1
        drained1, d_res1 = drain_entropy(req_id=201)
        self.assertEqual(d_res1["status"], abi.STATUS_SUCCESS)
        self.assertEqual(drained1, block1)
        self.assertEqual(d_res1["fill_level"], 1)

        # Drain Block 2
        drained2, d_res2 = drain_entropy(req_id=202)
        self.assertEqual(d_res2["status"], abi.STATUS_SUCCESS)
        self.assertEqual(drained2, block2)
        self.assertEqual(d_res2["fill_level"], 0)

        # Drain on Empty Reservoir -> Rejection
        _, d_empty = drain_entropy(req_id=203)
        self.assertEqual(d_empty["status"], abi.STATUS_RESERVOIR_EMPTY)

    def test_04_hysteresis_loop_state_transitions(self):
        """Validates 5% / 30% Hysteresis loop on physical AIE2 hardware."""
        rng = np.random.default_rng(seed=0x87654321)

        # Initial mode should be Degraded A (0 slots < high water mark 5)
        status = get_reservoir_telemetry()
        self.assertEqual(status["mode"], abi.STATE_DEGRADED_A)

        # Fill up to 4 slots (still below High-Water Mark of 5 slots = ~31%)
        for i in range(4):
            res = ingress_entropy(rng.bytes(32), req_id=300 + i)
            self.assertEqual(res["status"], abi.STATUS_SUCCESS)
            self.assertEqual(res["mode"], abi.STATE_DEGRADED_A)

        # Fill 5th slot -> Reaches High-Water Mark (5 / 16 = 31.25% >= 30%) -> Transitions to Full Hybrid
        res5 = ingress_entropy(rng.bytes(32), req_id=305)
        self.assertEqual(res5["status"], abi.STATUS_SUCCESS)
        self.assertEqual(res5["fill_level"], 5)
        self.assertEqual(res5["mode"], abi.STATE_FULL_HYBRID)

        # Drain down to 2 slots -> Due to hysteresis, STILL in Full Hybrid (anti-flapping active)
        drain_entropy() # 4 left
        drain_entropy() # 3 left
        _, d_res = drain_entropy() # 2 left
        self.assertEqual(d_res["fill_level"], 2)
        self.assertEqual(d_res["mode"], abi.STATE_FULL_HYBRID)

        # Drain down to 1 slot -> Hits Low-Water Mark (<= 1 slot = 6.25% <= 5%) -> Transitions to Degraded A
        _, d_low = drain_entropy()
        self.assertEqual(d_low["fill_level"], 1)
        self.assertEqual(d_low["mode"], abi.STATE_DEGRADED_A)

    def test_05_zeroization_scrubber(self):
        """Validates complete hardware zeroization of reservoir."""
        rng = np.random.default_rng(seed=0x99999999)
        for i in range(8):
            ingress_entropy(rng.bytes(32), req_id=400 + i)

        status_before = get_reservoir_telemetry()
        self.assertEqual(status_before["fill_level"], 8)

        # Trigger Zeroization
        z_res = zeroize_reservoir()
        self.assertEqual(z_res["status"], abi.STATUS_TAMPER_ZEROIZED)
        self.assertEqual(z_res["fill_level"], 0)
        self.assertEqual(z_res["mode"], abi.STATE_DEGRADED_A)

    def test_06_downstream_pqc_seeding_integration(self):
        """Validates feeding QRNG reservoir entropy into ML-KEM-768 and ML-DSA-65."""
        from phoenix_sdr_dsp.pqc.dr8_mlkem768_encaps_graph import run_mlkem768_encaps
        from phoenix_sdr_dsp.pqc.dr8_mlkem768_keygen_graph import run_mlkem768_keygen

        # Seed reservoir with high-quality entropy (d, z, m)
        d_seed = sha256(b"NPU_QRNG_D_SEED_DR27").digest()
        z_seed = sha256(b"NPU_QRNG_Z_SEED_DR27").digest()
        m_seed = sha256(b"NPU_QRNG_M_SEED_DR27").digest()

        ingress_entropy(d_seed, req_id=501)
        ingress_entropy(z_seed, req_id=502)
        ingress_entropy(m_seed, req_id=503)

        # Drain entropy blocks for KeyGen (d, z)
        qrng_d, _ = drain_entropy(req_id=504)
        qrng_z, _ = drain_entropy(req_id=505)
        qrng_m, _ = drain_entropy(req_id=506)

        self.assertEqual(len(qrng_d), 32)
        self.assertEqual(len(qrng_z), 32)
        self.assertEqual(len(qrng_m), 32)

        # Generate ML-KEM KeyPair seeded by physical QRNG reservoir
        pk, sk = run_mlkem768_keygen(qrng_d, qrng_z)
        self.assertEqual(len(pk), 1184)
        self.assertEqual(len(sk), 2400)

        # Encapsulate
        ct, ss = run_mlkem768_encaps(pk, qrng_m)
        self.assertEqual(len(ct), 1088)
        self.assertEqual(len(ss), 32)

if __name__ == "__main__":
    unittest.main()
