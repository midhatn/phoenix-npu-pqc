"""Host-only contract checks for the additive DR2d W0 token-tap diagnostic."""

from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_abi as abi
from phoenix_sdr_dsp.pqc import (
    dr2d_mlkem512_kpke_keygen_w0_token_tap_graph as tap,
)


class W0TokenTapContractTests(unittest.TestCase):
    def test_pinned_production_sources_are_unchanged(self) -> None:
        observed = tap.verify_production_hashes(require_retained_object=False)
        self.assertEqual(len(observed), 5)

    def test_graph_is_one_worker_two_ingress_one_direct_egress(self) -> None:
        source = Path(tap.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from __future__ import annotations", source)
        self.assertEqual(source.count("ExternalFunction("), 1)
        self.assertEqual(source.count("d_prod.fill(d)"), 1)
        self.assertEqual(source.count("descriptor_prod.fill(descriptor)"), 1)
        self.assertEqual(source.count("secret_cons.drain(secret_token, wait=True)"), 1)
        self.assertIn("workers=[worker]", source)
        self.assertIn("stack_size=0x1000", source)
        for forbidden in (
            "row0_expand",
            "row0_accumulate",
            "row1_expand",
            "row1_accumulate",
            "kpke_keygen_serialize",
            "dr2d_reference",
        ):
            self.assertNotIn(forbidden, source)

    def test_compiletime_specialization_generates_mlir_without_dispatch(self) -> None:
        authorization_name = "PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION"
        self.assertNotIn(authorization_name, os.environ)
        try:
            design = tap._program()
        except tap.NativeBackendUnavailable:
            if os.environ.get("PQC_DR2D_REQUIRE_IRON_MLIR_CONTRACT") == "1":
                raise
            self.skipTest("IRON is unavailable for the no-dispatch MLIR contract")
        expected = {
            "d_slots",
            "descriptor_slots",
            "secret_token_slots",
            "element_type",
        }
        self.assertEqual(set(design.compilable.compile_params), expected)
        specialized = design.specialize(
            d_slots=abi.D_BYTES,
            descriptor_slots=abi.DESCRIPTOR_BYTES,
            secret_token_slots=abi.SECRET_TOKEN_BYTES,
            element_type=np.uint8,
        )
        self.assertEqual(set(specialized.compilable.compile_kwargs), expected)
        mlir = specialized.as_mlir()
        self.assertIn("dr2d_kpke_keygen_seed_noise", mlir)
        self.assertIn("dr2d_w0_tap_secret_token", mlir)
        self.assertNotIn("dr2d_kpke_keygen_row0_expand", mlir)
        self.assertNotIn("dr2d_kpke_keygen_serialize", mlir)
        self.assertNotIn(authorization_name, os.environ)

    def test_success_token_validation_is_complete_and_reference_free(self) -> None:
        request_id = 0xD2D00001
        token = bytearray(abi.SECRET_TOKEN_BYTES)
        struct.pack_into("<II", token, 0, request_id, abi.STATUS_OK)
        token[16:48] = bytes(range(32))
        self.assertEqual(tap.validate_w0_secret_token(token, request_id), bytes(token))
        hashes = tap.token_region_hashes(token)
        self.assertEqual(
            set(hashes),
            {"token", "header", "rho", "s_hat_0", "s_hat_1", "e_hat_0", "e_hat_1"},
        )

    def test_unwritten_sentinel_and_noncanonical_lane_fail_closed(self) -> None:
        request_id = 7
        with self.assertRaises(abi.Dr2dAbiError):
            tap.validate_w0_secret_token(
                bytes([0xA5]) * abi.SECRET_TOKEN_BYTES, request_id
            )
        token = bytearray(abi.SECRET_TOKEN_BYTES)
        struct.pack_into("<II", token, 0, request_id, abi.STATUS_OK)
        struct.pack_into("<H", token, 48, abi.Q)
        with self.assertRaises(abi.Dr2dAbiError):
            tap.validate_w0_secret_token(token, request_id)

    def test_error_token_requires_fixed_zero_payload(self) -> None:
        request_id = 9
        token = bytearray(abi.SECRET_TOKEN_BYTES)
        struct.pack_into("<II", token, 0, request_id, abi.STATUS_BAD_TOKEN)
        with self.assertRaises(abi.Dr2dOperationError):
            tap.validate_w0_secret_token(token, request_id)
        token[-1] = 1
        with self.assertRaises(abi.Dr2dAbiError):
            tap.validate_w0_secret_token(token, request_id)

    def test_native_entrypoint_has_an_explicit_authorization_guard(self) -> None:
        runner = (
            Path(__file__).resolve().parent
            / "diagnose_dr2d_mlkem512_kpke_w0_token_tap.py"
        ).read_text(encoding="utf-8")
        self.assertIn("PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION", runner)
        self.assertIn("AUTHORIZED_AFTER_W0_TAP_COMPILE_ONLY_REVIEW", runner)
        self.assertNotIn("dr2d_reference", runner)
        self.assertNotIn("PRE_SILICON_CORPUS", runner)


if __name__ == "__main__":
    unittest.main()
