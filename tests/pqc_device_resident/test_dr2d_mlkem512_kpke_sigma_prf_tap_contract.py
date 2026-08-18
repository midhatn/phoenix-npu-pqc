"""Host-only and no-dispatch contracts for the additive sigma-plus-PRF tap."""

import hashlib
import os
import unittest
from pathlib import Path

D_HEX = "47b893474672ba92e4b12ee44fb32953af8e8503b5fb471d1614fb8a021a660a"
EXPECTED_SIGMA = "5d3628d3edbeb81cde94bd2adc989020343cb2c5ab8f3c922e66d1cde54ef3a0"
EXPECTED_PRF_SHA256 = (
    "7be3f7375be9880cd97047361def65c0154f99d05781c7fdd6dbda3079ea6db3",
    "1921bf3ea11ad75a9430a85204d8fb7f185fdfc26af02953d18dbe74a6a59d34",
    "966fdd0b608b6bf671a67974ab25befa727908d592a000f0f13dc5b0df175761",
    "f2f858451147d532310d7a10727164c7f0685afeae8b7fe6cfa42463e03c2d61",
)
ROOT = Path(__file__).resolve().parents[2]
KERNEL = (
    ROOT
    / "phoenix_sdr_dsp"
    / "pqc"
    / "kernels"
    / ("dr2d_mlkem512_kpke_sigma_prf_tap.cc")
)
GRAPH = ROOT / "phoenix_sdr_dsp" / "pqc" / "dr2d_mlkem512_kpke_sigma_prf_tap_graph.py"


def expected_trace(d: bytes) -> bytes:
    digest = hashlib.sha3_512(d + b"\x02").digest()
    sigma = digest[32:64]
    streams = b"".join(
        hashlib.shake_256(sigma + bytes((nonce,))).digest(192) for nonce in range(4)
    )
    return sigma + streams


class SigmaPrfTapContracts(unittest.TestCase):
    def test_known_tc_id_01_reference_trace(self) -> None:
        trace = expected_trace(bytes.fromhex(D_HEX))
        self.assertEqual(len(trace), 800)
        self.assertEqual(trace[:32].hex(), EXPECTED_SIGMA)
        for nonce, expected_digest in enumerate(EXPECTED_PRF_SHA256):
            start = 32 + nonce * 192
            self.assertEqual(
                hashlib.sha256(trace[start : start + 192]).hexdigest(), expected_digest
            )

    def test_kernel_has_exact_evidenced_staging_and_pre_cbd_layout(self) -> None:
        source = KERNEL.read_text(encoding="utf-8")
        for required in (
            "dr2d_kpke_sigma_prf_tap",
            "state[32] ^= 2u;",
            "state[33] ^= 0x06u;",
            "state[kRateG - 1u] ^= 0x80u;",
            "state[32] ^= nonce;",
            "state[33] ^= 0x1fu;",
            "state[kRateShake256 - 1u] ^= 0x80u;",
            "output[index] = state[index];",
            "output[kRateShake256 + index] = state[index];",
            "kTraceBytes = kSigmaBytes + kPrfCount * kPrfBytes",
        ):
            self.assertIn(required, source)
        self.assertNotIn("cbd3", source.lower())
        self.assertNotIn("ntt", source.lower())

    def test_graph_is_one_worker_one_input_one_direct_trace_egress(self) -> None:
        source = GRAPH.read_text(encoding="utf-8")
        topology_source = source.replace("dr2d_kpke_keygen_seed_noise.o", "")
        self.assertIn('name="dr2d_sigma_prf_tap_d"', source)
        self.assertIn('name="dr2d_sigma_prf_tap_trace"', source)
        self.assertIn('"dr2d_kpke_sigma_prf_tap"', source)
        self.assertEqual(source.count("ObjectFifo("), 2)
        self.assertEqual(source.count("Worker("), 1)
        for forbidden in (
            "dr2d_kpke_keygen_seed_noise",
            "dr2d_kpke_keygen_row0_expand",
            "dr2d_kpke_keygen_row0_accumulate",
            "dr2d_kpke_keygen_row1_expand",
            "dr2d_kpke_keygen_row1_accumulate",
            "dr2d_kpke_keygen_serialize",
        ):
            self.assertNotIn(forbidden, topology_source)

    def test_graph_protects_pinned_production_inputs(self) -> None:
        source = GRAPH.read_text(encoding="utf-8")
        for digest in (
            "742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad",
            "a6f44c68787905f6b4819598baacac59bf5bcc4a3125c8151b7863345e9ff4f4",
            "e17e17b8481bc1fa8492a7e2bc9184fbae095b55c5e175b015aa19a2bc999694",
            "16d61e6ada4d7de384b3981cc76d3de8319ce2bec999727d4847567e7e1f3519",
            "0470fb39277478a368004a49e551a3411d8f9185b492ac01f85d2297bcea3c1f",
            "2f94e2995706ac5636f35c66167e5dd8f54ac54b618c200bf4ee45b8b754ceaf",
            "7ea27cc5f6bb905253a161acd98988c62afc54855bcfd1c4530a55c441e28b70",
        ):
            self.assertIn(digest, source)

    @unittest.skipUnless(
        os.environ.get("PQC_DR2D_REQUIRE_IRON_MLIR_CONTRACT") == "1",
        "requires the checkout-local Windows IRON environment",
    )
    def test_specialization_generates_mlir_without_compile_or_dispatch(self) -> None:
        import numpy as np

        from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_sigma_prf_tap_graph as tap

        design = tap._program()
        self.assertEqual(
            set(design.compilable.compile_params),
            {"d_slots", "trace_slots", "element_type"},
        )
        specialized = design.specialize(
            d_slots=32,
            trace_slots=800,
            element_type=np.uint8,
        )
        self.assertEqual(
            set(specialized.compilable.compile_kwargs),
            {"d_slots", "trace_slots", "element_type"},
        )
        mlir_text = specialized.as_mlir()
        self.assertIn("dr2d_kpke_sigma_prf_tap", mlir_text)
        self.assertIn("dr2d_sigma_prf_tap_trace", mlir_text)
        for forbidden in (
            "dr2d_kpke_keygen_seed_noise",
            "dr2d_kpke_keygen_row0_expand",
            "dr2d_kpke_keygen_row0_accumulate",
            "dr2d_kpke_keygen_row1_expand",
            "dr2d_kpke_keygen_row1_accumulate",
            "dr2d_kpke_keygen_serialize",
        ):
            self.assertNotIn(forbidden, mlir_text)


if __name__ == "__main__":
    unittest.main()
