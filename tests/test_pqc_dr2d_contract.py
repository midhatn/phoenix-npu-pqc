"""Static ABI, residency, zeroization, and native-only contracts for DR2d."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
import struct
import subprocess
import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_abi as abi
from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_graph as graph
from phoenix_sdr_dsp.pqc import (
    dr2d_mlkem512_kpke_keygen_terminal_probe_graph as terminal_probe,
)

REPO = Path(__file__).resolve().parents[1]
KERNELS = REPO / "phoenix_sdr_dsp" / "pqc" / "kernels"
DR2C_EXPAND = KERNELS / "dr2c_mlkem512_keygen_row_expand.cc"
DR2B_CBD_NTT = KERNELS / "dr2b_mlkem512_cbd_ntt.cc"
INTERNAL = KERNELS / "dr2d_mlkem512_kpke_keygen_internal.hpp"
PARTITION_SOURCES = (
    "dr2d_mlkem512_kpke_keygen_seed.cc",
    "dr2d_mlkem512_kpke_keygen_row0_expand.cc",
    "dr2d_mlkem512_kpke_keygen_row0_accumulate.cc",
    "dr2d_mlkem512_kpke_keygen_row1_expand.cc",
    "dr2d_mlkem512_kpke_keygen_row1_accumulate.cc",
    "dr2d_mlkem512_kpke_keygen_serialize.cc",
)
DESIGN = REPO / "docs" / "PQC_DR2D_DESIGN.md"
PENDING = REPO / "docs" / "PQC_DR2D_SILICON_VALIDATION_PENDING.md"
TERMINAL_PROBE = KERNELS / "dr2d_mlkem512_kpke_keygen_terminal_probe.cc"
GATE = (
    REPO / "tests" / "pqc_device_resident" / "test_dr2d_mlkem512_kpke_keygen_silicon.py"
)
VECTORS = (
    REPO
    / "tests"
    / "pqc_device_resident"
    / "data"
    / "dr2d_nist_acvp_mlkem512_kpke_keygen_25.json"
)
PROVENANCE = (
    REPO
    / "tests"
    / "pqc_device_resident"
    / "data"
    / "acvp_975de31eb83d87039ec88934fdc47d8c312b892d"
)
EXTRACTOR = REPO / "tools" / "extract_dr2d_acvp_vectors.py"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _zeta_table(source: str) -> tuple[int, ...]:
    match = re.search(r"kZetas\[128\]\s*=\s*\{(.*?)\};", source, flags=re.DOTALL)
    if match is None:
        raise AssertionError("missing kZetas[128] table")
    return tuple(int(value) for value in re.findall(r"(\d+)u", match.group(1)))


class DR2dDeviceResidencyContractTests(unittest.TestCase):
    def test_fixed_complete_keygen_abi(self) -> None:
        self.assertEqual(
            (
                abi.D_BYTES,
                abi.DESCRIPTOR_BYTES,
                abi.G_INPUT_BYTES,
                abi.G_OUTPUT_BYTES,
                abi.SECRET_TOKEN_BYTES,
                abi.ROW_MATRIX_TOKEN_BYTES,
                abi.ROW_STATE_TOKEN_BYTES,
                abi.PRIVATE_TOKEN_BYTES,
                abi.EK_PKE_BYTES,
                abi.DK_PKE_BYTES,
                abi.RESULT_HEADER_BYTES,
                abi.RESULT_BYTES,
            ),
            (32, 16, 33, 64, 2096, 3120, 2096, 2112, 800, 768, 20, 1588),
        )
        self.assertEqual(
            (
                abi.ABI_VERSION,
                abi.OPCODE_MLKEM512_KPKE_KEYGEN,
                abi.PARAMETER_MLKEM512,
                abi.K,
                abi.ETA1,
                abi.SAMPLE_NTT_BLOCK_CAP,
            ),
            (1, 0x24, 0x52, 2, 3, 5),
        )
        self.assertEqual(graph.BACKEND_LABEL, "dr2d-mlkem512-kpke-keygen:silicon")

    def test_partition_has_two_public_ingress_fifos_five_private_fifos_and_one_terminal_output(
        self,
    ) -> None:
        source = inspect.getsource(graph)
        self.assertEqual(source.count("ObjectFifo("), 8)
        self.assertEqual(source.count("Worker("), 6)
        self.assertEqual(source.count(" = external("), 6)
        for name in (
            "dr2d_d",
            "dr2d_descriptor",
            "dr2d_secret_token",
            "dr2d_row0_matrix",
            "dr2d_row_state",
            "dr2d_row1_matrix",
            "dr2d_final_token",
            "dr2d_result",
        ):
            self.assertIn(f'name="{name}"', source)
        self.assertNotIn("kpke_keygen_derive", source)
        self.assertNotIn("kpke_keygen_secret_noise", source)
        runtime_source = source.split("runtime = Runtime", 1)[1]
        for endpoint in ("of_d.prod()", "of_descriptor.prod()", "of_result.cons()"):
            self.assertIn(endpoint, runtime_source)
        for private_endpoint in (
            "of_secret.prod()",
            "of_secret.cons()",
            "of_row0_matrix.prod()",
            "of_row0_matrix.cons()",
            "of_row_state.prod()",
            "of_row_state.cons()",
            "of_row1_matrix.prod()",
            "of_row1_matrix.cons()",
            "of_final.prod()",
            "of_final.cons()",
        ):
            self.assertNotIn(private_endpoint, runtime_source)
        for filename in PARTITION_SOURCES:
            self.assertIn(filename, source)

    def test_runtime_has_exactly_two_fills_one_drain_and_one_cpu_transfer(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        sequence = _function(tree, "sequence")
        calls = [node.value for node in sequence.body if isinstance(node, ast.Expr)]
        self.assertEqual([call.func.attr for call in calls], ["fill", "fill", "drain"])
        transfers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "to"
        ]
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0].func.value.id, "result_t")
        self.assertEqual(transfers[0].args[0].value, "cpu")

    def test_validation_precedes_native_loading_and_production_has_no_reference_or_test_dependency(
        self,
    ) -> None:
        source = inspect.getsource(graph.run_mlkem512_kpke_keygen)
        self.assertLess(
            source.index("abi.validate_request"), source.index("_load_iron()")
        )
        self.assertIn("abi.result_sentinel()", source)
        self.assertIn("abi.parse_result", source)
        self.assertLess(source.index("try:"), source.index("_load_iron()"))
        self.assertIn("finally:", source)
        self.assertIn("_clear_host_staging(d_np, d_t)", source)
        self.assertIn("_clear_host_staging(descriptor_np, descriptor_t)", source)
        self.assertLess(
            source.index("abi.parse_result"),
            source.index("_clear_host_staging(result_np, result_t)"),
        )
        production = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO / "phoenix_sdr_dsp" / "pqc").rglob("*")
            if path.is_file() and path.suffix in {".py", ".cc", ".hpp"}
        )
        self.assertNotIn("tests/", production)
        self.assertNotIn("tests.", production)
        self.assertNotIn("kpke_keygen_reference", production)
        self.assertNotIn("hashlib", source)

    def test_partitioned_workers_use_fixed_tokens_frozen_zetas_and_clear_all_boundaries(
        self,
    ) -> None:
        sources = {
            name: (KERNELS / name).read_text(encoding="utf-8")
            for name in PARTITION_SOURCES
        }
        internal = INTERNAL.read_text(encoding="utf-8")
        seed = sources["dr2d_mlkem512_kpke_keygen_seed.cc"]
        dr2b = DR2B_CBD_NTT.read_text(encoding="utf-8")
        self.assertIn("constexpr uint16_t kZetas[128]", internal)
        self.assertNotIn("brv7(", internal)
        self.assertNotIn("zeta(", internal)
        self.assertNotIn("pow(", internal)
        self.assertNotIn("0x00249249u", internal)
        self.assertNotIn("cbd3_ntt_store(", internal)
        zetas = _zeta_table(internal)
        self.assertEqual(zetas, _zeta_table(DR2C_EXPAND.read_text(encoding="utf-8")))
        self.assertEqual(
            hashlib.sha256(
                b"".join(struct.pack("<H", value) for value in zetas)
            ).hexdigest(),
            "ecc64560d6b8e28e2c3954ea934dfd35ad6ca41703bf713718ce94b3b1d2381b",
        )
        for phrase in (
            "derive_g(d, rho, sigma)",
            "cbd3_ntt_store_dr2b(sigma, 0",
            "cbd3_ntt_store_dr2b(sigma, 3",
            "sample_matrix_store(matrix + kRhoOffset, 0, 0",
            "sample_matrix_store(matrix + kRhoOffset, 1, 1",
            "add_product_ntt(",
            "canonical_poly(",
            "valid_header(",
            "clear_bytes(matrix, kMatrixTokenBytes)",
            "clear_bytes(secret, kSecretTokenBytes)",
            "clear_bytes(state, kStateTokenBytes)",
            "clear_bytes(token, kTokenBytes)",
            "crc32(payload, kEkBytes + kDkBytes)",
        ):
            self.assertIn(phrase, internal + "\n".join(sources.values()))
        self.assertIn(
            "clear_bytes(d, 32)", sources["dr2d_mlkem512_kpke_keygen_seed.cc"]
        )
        self.assertIn(
            "clear_bytes(descriptor, 16)", sources["dr2d_mlkem512_kpke_keygen_seed.cc"]
        )
        for dr2b_fragment in (
            "static uint32_t bit_at(const uint8_t *prf, uint32_t bit)",
            "static void cbd3(const uint8_t prf[kPrfBytes], uint32_t out[kN])",
            "__attribute__((noinline)) static void ntt(uint32_t r[kN])",
            "const uint32_t t = mod_mul(zeta, r[j + length]);",
            "r[j + length] = r[j] >= t ? r[j] - t : r[j] + kQ - t;",
        ):
            self.assertIn(dr2b_fragment, dr2b)
            self.assertIn(dr2b_fragment, seed)
        self.assertIn("uint32_t coefficients[kN];", seed)
        self.assertIn("cbd3(prf, coefficients);", seed)
        self.assertIn("ntt(coefficients);", seed)
        self.assertIn("clear_bytes(coefficients, sizeof(coefficients));", seed)
        self.assertNotIn("cbd3_ntt_store(", seed)
        self.assertNotIn("load_le16(out + 2 * lane)", seed)
        self.assertNotIn("0x00249249u", seed)
        self.assertIn(
            "Success magic is the final device store.",
            sources["dr2d_mlkem512_kpke_keygen_serialize.cc"],
        )
        serializer = sources["dr2d_mlkem512_kpke_keygen_serialize.cc"]
        self.assertIn(
            "const uint32_t a = load_le16(source + 4 * i), b = load_le16(source + 4 * i + 2);",
            serializer,
        )
        encoder = serializer.split("static void encode_poly12", 1)[1].split(
            "static void write_error", 1
        )[0]
        self.assertIn("const uint8_t *p = source + 4 * i;", encoder)
        self.assertIn(
            "const uint32_t p0 = p[0], p1 = p[1], p2 = p[2], p3 = p[3];",
            encoder,
        )
        self.assertIn("static_cast<uint8_t>(p0)", encoder)
        self.assertIn("static_cast<uint8_t>((p1 & 0x0fu) |", encoder)
        self.assertIn("((p2 & 0x0fu) << 4))", encoder)
        self.assertIn("static_cast<uint8_t>(((p2 >> 4) & 0x0fu) |", encoder)
        self.assertIn("((p3 & 0x0fu) << 4))", encoder)
        self.assertNotIn("a >> 8", encoder)
        self.assertNotIn("load_le16(", encoder)
        self.assertNotIn("b >> 4", encoder)
        self.assertNotIn("const uint16_t a = load_le16(source + 4 * i)", serializer)
        self.assertNotIn(
            "dr2d_mlkem512_kpke_keygen_derive.cc", inspect.getsource(graph)
        )

    def test_every_repaired_production_store_is_a_guarded_full_word_store(
        self,
    ) -> None:
        """Forbid every vulnerable sub-word coefficient store shape in DR2d.

        The installed Peano (llvm-aie 21.0.0 c9c5ecb7, ancestral to upstream fix
        f1baf5a / PR #1221) drops the high half of a sub-word store scheduled
        into a zero-overhead-loop end bundle.  These are source-shape contracts
        only: they cannot replace the required Phoenix ELF inspection, but they
        make a silent regression to a 16-bit or byte coefficient store fail the
        host gate.

        Scope is destination-classified: only coefficient-bearing and
        polynomial-carry token regions must be word-stored.  Byte stores to
        local Keccak/SHAKE/PRF state, token ``rho`` regions, headers, volatile
        zeroization, and the unchanged serializer are required to remain.
        """
        internal = INTERNAL.read_text(encoding="utf-8")
        sources = {
            name: (KERNELS / name).read_text(encoding="utf-8")
            for name in PARTITION_SOURCES
        }
        repaired = {
            name: text
            for name, text in sources.items()
            if name != "dr2d_mlkem512_kpke_keygen_serialize.cc"
        }

        # 1. The shared 16-bit coefficient store helper must no longer exist.
        self.assertNotIn("store_le16", internal)
        self.assertIn("static inline uint16_t load_le16(", internal)
        for name, text in repaired.items():
            with self.subTest(source=name):
                self.assertNotIn("store_le16", text)

        # 2. The full-word primitives must be present in their exact shapes.
        self.assertIn("#include <new>", internal)
        self.assertIn(
            "static inline bool word_aligned(const void *address) {", internal
        )
        self.assertIn(
            "constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;",
            internal,
        )
        self.assertIn(
            "return (reinterpret_cast<uintptr_t>(address) & kWordAlignmentMask) == 0;",
            internal,
        )
        self.assertIn(
            "static inline void store_pair_word(uint8_t *out, uint32_t pair,", internal
        )
        self.assertIn(
            "const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);", internal
        )
        self.assertIn(
            "::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);", internal
        )
        self.assertIn("static inline bool copy_words(uint8_t *destination,", internal)
        self.assertIn(
            "if ((bytes & 3u) != 0 || !word_aligned(destination) || !word_aligned(source))",
            internal,
        )
        self.assertIn("::new (static_cast<void *>(destination + 4 * word))", internal)
        self.assertIn("uint32_t(load_le32(source + 4 * word));", internal)

        # 3. No cast-pointer or typed-array store may reappear anywhere in DR2d.
        for label, text in (("internal.hpp", internal), *repaired.items()):
            with self.subTest(no_cast_store=label):
                self.assertNotIn("reinterpret_cast<uint32_t *>", text)
                self.assertNotIn("reinterpret_cast<uint16_t *>", text)
                self.assertNotIn("words[", text)
                self.assertNotIn("memcpy", text)

        # 4. Alignment must be justified statically for every offset and span.
        for assertion in (
            "DR2d shared polynomial offsets must be 32-bit aligned",
            "DR2d secret-token polynomial offsets must be 32-bit aligned",
            "DR2d state-token polynomial offsets must be 32-bit aligned",
            "DR2d matrix-token polynomial offsets must be 32-bit aligned",
            "DR2d final-token polynomial offsets must be 32-bit aligned",
            "DR2d coefficient copy spans must be whole 32-bit words",
            "DR2d full-word coefficient stores assume a little-endian target",
        ):
            with self.subTest(static_assert=assertion):
                self.assertIn(assertion, internal)

        # 5. The three repaired helpers must be guarded, fail-closed, and pair-wise.
        sample = internal.split("static inline bool sample_matrix_store", 1)[1].split(
            "static inline bool add_product_ntt", 1
        )[0]
        self.assertIn("if (!word_aligned(out)) return false;", sample)
        self.assertIn("store_pair_word(out, accepted >> 1, pending, d1);", sample)
        self.assertIn("store_pair_word(out, accepted >> 1, pending, d2);", sample)
        self.assertNotIn("store_le16", sample)
        self.assertNotIn("out + 2 * accepted", sample)

        product = internal.split("static inline bool add_product_ntt", 1)[1]
        self.assertIn("if (!word_aligned(accumulator)) return false;", product)
        self.assertIn(
            "store_pair_word(accumulator + 2 * o, 0, reduced[0], reduced[1]);", product
        )
        self.assertIn(
            "store_pair_word(accumulator + 2 * o, 1, reduced[2], reduced[3]);", product
        )
        self.assertNotIn("store_le16", product)
        self.assertNotIn("accumulator + 2 * (o + lane), static_cast<uint16_t>", product)

        seed = sources["dr2d_mlkem512_kpke_keygen_seed.cc"]
        noise = seed.split("static bool cbd3_ntt_store_dr2b", 1)[1].split(
            "static void seed_noise", 1
        )[0]
        self.assertIn("if (!word_aligned(out)) return false;", noise)
        self.assertIn(
            "store_pair_word(out, pair, coefficients[2 * pair], coefficients[2 * pair + 1]);",
            noise,
        )
        self.assertNotIn("store_le16", noise)
        self.assertNotIn("out + 2 * i", noise)

        # 6a. No per-byte COEFFICIENT copy loop may remain in a worker.  These
        #     are the only byte-copy shapes the repair is allowed to remove.
        for name, text in repaired.items():
            with self.subTest(no_coefficient_byte_copy_loop=name):
                for forbidden in (
                    "= secret[kSecretS0Offset + i]",
                    "= state[kStateSecretOffset + i]",
                    "= matrix[kMatrixSecretOffset + i]",
                    "= matrix[kMatrixCarry0Offset + i]",
                    "= matrix[kMatrixCarry1Offset + i]",
                    "32 + 4 * kN",
                    "32 + 8 * kN",
                ):
                    self.assertNotIn(forbidden, text)

        # 6b. Every polynomial/carry region must be copied with copy_words at
        #     its exact destination offset and span.  A destination-classified
        #     map, so a future edit cannot quietly widen or narrow the repair.
        for name, expected_copies in (
            (
                "dr2d_mlkem512_kpke_keygen_row0_expand.cc",
                (
                    "copy_words(matrix + kMatrixSecretOffset, secret + kSecretS0Offset, 8 * kN)",
                ),
            ),
            (
                "dr2d_mlkem512_kpke_keygen_row1_expand.cc",
                (
                    "copy_words(matrix + kMatrixSecretOffset, state + kStateSecretOffset, 8 * kN)",
                ),
            ),
            (
                "dr2d_mlkem512_kpke_keygen_row0_accumulate.cc",
                (
                    "copy_words(state + kStateSecretOffset, matrix + kMatrixSecretOffset, 4 * kN)",
                    "copy_words(state + kStateT0Offset, matrix + kMatrixCarry0Offset, 2 * kN)",
                    "copy_words(state + kStateE1Offset, matrix + kMatrixCarry1Offset, 2 * kN)",
                ),
            ),
            (
                "dr2d_mlkem512_kpke_keygen_row1_accumulate.cc",
                (
                    "copy_words(final_token + kFinalS0Offset, matrix + kMatrixSecretOffset, 4 * kN)",
                    "copy_words(final_token + kFinalT0Offset, matrix + kMatrixCarry0Offset, 2 * kN)",
                    "copy_words(final_token + kFinalT1Offset, matrix + kMatrixCarry1Offset, 2 * kN)",
                ),
            ),
        ):
            for expected in expected_copies:
                with self.subTest(polynomial_copy=name, span=expected):
                    self.assertIn(expected, sources[name])

        # 6c. rho is NOT coefficient storage.  Its physically validated 32-byte
        #     byte-store loops must be retained, never widened to copy_words.
        #     This keeps the production repair minimal and keeps the Phoenix
        #     gate's Class R allowance truthful.
        for name, retained in (
            ("dr2d_mlkem512_kpke_keygen_seed.cc", "token[kRhoOffset + i] = rho[i];"),
            (
                "dr2d_mlkem512_kpke_keygen_row0_expand.cc",
                "matrix[kRhoOffset + i] = secret[kRhoOffset + i];",
            ),
            (
                "dr2d_mlkem512_kpke_keygen_row1_expand.cc",
                "matrix[kRhoOffset + i] = state[kRhoOffset + i];",
            ),
            (
                "dr2d_mlkem512_kpke_keygen_row0_accumulate.cc",
                "state[kRhoOffset + i] = matrix[kRhoOffset + i];",
            ),
            (
                "dr2d_mlkem512_kpke_keygen_row1_accumulate.cc",
                "final_token[kFinalRhoOffset + i] = matrix[kRhoOffset + i];",
            ),
        ):
            with self.subTest(retained_rho_byte_copy=name):
                self.assertIn(retained, sources[name])
                self.assertIn("for (uint32_t i = 0; i < 32; ++i)", sources[name])
                self.assertNotIn("copy_words(token + kRhoOffset", sources[name])
                self.assertNotIn("copy_words(matrix + kRhoOffset", sources[name])
                self.assertNotIn("copy_words(state + kRhoOffset", sources[name])
                self.assertNotIn(
                    "copy_words(final_token + kFinalRhoOffset", sources[name]
                )

        # 6d. Local byte-oriented Keccak/SHAKE/PRF state must stay byte-wise.
        #     The repair must not widen unrelated local cryptographic state.
        for fragment in (
            "for (uint32_t i = 0; i < 32; ++i) state[i] ^= d[i];",
            "for (uint32_t i = 0; i < 32; ++i) state[i] ^= rho[i];",
            "{ rho[i] = state[i]; sigma[i] = state[32 + i]; }",
        ):
            with self.subTest(retained_local_state=fragment):
                self.assertIn(fragment, internal)
        for fragment in (
            "for (uint32_t i = 0; i < 32; ++i) state[i] ^= sigma[i];",
            "for (uint32_t i = 0; i < kRate256; ++i) prf[i] = state[i];",
        ):
            with self.subTest(retained_local_state=fragment):
                self.assertIn(fragment, seed)

        # 7. Every repaired worker guards its token bases and fails closed.
        guards = {
            "dr2d_mlkem512_kpke_keygen_seed.cc": (
                "!word_aligned(token)",
                "write_header(token, kSecretTokenBytes, id, kBadToken, kSecretHeaderBytes)",
            ),
            "dr2d_mlkem512_kpke_keygen_row0_expand.cc": (
                "!word_aligned(matrix) || !word_aligned(secret)",
                "write_header(matrix, kMatrixTokenBytes, id, kBadToken, kMatrixHeaderBytes)",
            ),
            "dr2d_mlkem512_kpke_keygen_row0_accumulate.cc": (
                "!word_aligned(state) || !word_aligned(matrix)",
                "write_header(state, kStateTokenBytes, id, kBadToken, kStateHeaderBytes)",
            ),
            "dr2d_mlkem512_kpke_keygen_row1_expand.cc": (
                "!word_aligned(matrix) || !word_aligned(state)",
                "write_header(matrix, kMatrixTokenBytes, id, kBadToken, kMatrixHeaderBytes)",
            ),
            "dr2d_mlkem512_kpke_keygen_row1_accumulate.cc": (
                "!word_aligned(final_token) || !word_aligned(matrix)",
                "write_header(final_token, kFinalTokenBytes, id, kBadToken, kFinalHeaderBytes)",
            ),
        }
        for name, (guard, fail_closed) in guards.items():
            with self.subTest(worker=name):
                self.assertIn(guard, sources[name])
                self.assertIn(fail_closed, sources[name])

        # 8. Every repaired store result must actually be consumed, not dropped.
        self.assertIn("const bool stored =", seed)
        for name in (
            "dr2d_mlkem512_kpke_keygen_row0_expand.cc",
            "dr2d_mlkem512_kpke_keygen_row1_expand.cc",
        ):
            with self.subTest(worker=name):
                self.assertIn("const bool complete = copy_words(", sources[name])
                self.assertIn("if (!complete) write_header(", sources[name])
        for name in (
            "dr2d_mlkem512_kpke_keygen_row0_accumulate.cc",
            "dr2d_mlkem512_kpke_keygen_row1_accumulate.cc",
        ):
            with self.subTest(worker=name):
                self.assertIn("const bool stored =", sources[name])
                self.assertIn("if (!stored) write_header(", sources[name])
                self.assertIn("add_product_ntt(", sources[name])

        # 9. The physically validated serializer translation unit is untouched by
        #    the repair: it neither includes the internal header nor gains a
        #    full-word helper, so its validated lowering cannot shift.
        serializer = sources["dr2d_mlkem512_kpke_keygen_serialize.cc"]
        self.assertNotIn("dr2d_mlkem512_kpke_keygen_internal.hpp", serializer)
        for forbidden in ("word_aligned", "store_pair_word", "copy_words", "::new "):
            with self.subTest(serializer_unchanged=forbidden):
                self.assertNotIn(forbidden, serializer)
        self.assertIn("static void store_le16(uint8_t *out, uint16_t x) {", serializer)

        # 10. DR2b and DR2c must be byte-identical to the validation baseline.
        for relative in (
            "phoenix_sdr_dsp/pqc/kernels/dr2b_mlkem512_cbd_ntt.cc",
            "phoenix_sdr_dsp/pqc/kernels/dr2b_mlkem512_shake256_prf_service.cc",
            "phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_expand.cc",
            "phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_accumulate.cc",
        ):
            with self.subTest(unchanged=relative):
                self.assertEqual(
                    (REPO / relative).read_text(encoding="utf-8"),
                    subprocess.run(
                        ["git", "show", f"HEAD:{relative}"],
                        cwd=REPO,
                        check=True,
                        capture_output=True,
                        encoding="utf-8",
                    ).stdout,
                )

        # 11. The physical diagnostic result and the residual gate are documented.
        pending = PENDING.read_text(encoding="utf-8")
        design = DESIGN.read_text(encoding="utf-8")
        self.assertIn("Status: PENDING PHYSICAL VALIDATION", pending)
        self.assertIn("physically PASSED on Phoenix", pending)
        self.assertIn(
            "309c9dd65e843edb15bc67766aff8f37b302ef815a435813881d6908d567adb4",
            pending,
        )
        self.assertIn(
            "Required Phoenix ELF inspection before production execution", pending
        )
        self.assertIn("st.s8", pending)
        self.assertIn("st.s16", pending)
        self.assertIn("f1baf5a", pending)
        self.assertIn("Residual gate", pending)
        self.assertIn("Full-word coefficient stores", design)
        self.assertIn("store_pair_word", design)
        self.assertIn("placement new", design)

        # 12. The documented Phoenix gate must be destination- and
        #     loop-classified.  A global byte-store allowlist is impossible for
        #     these workers (they legitimately keep Keccak/SHAKE/PRF, rho,
        #     header, clear, and serializer byte stores), so the gate must
        #     forbid sub-word stores only for coefficient/carry destinations and
        #     must explicitly say a global grep is invalid.
        self.assertIn(
            "destination- and loop-classified, never a global byte-store grep",
            pending,
        )
        for required in (
            'A global "no `st.s8`/`st.s16`" check is **wrong and must not be used**',
            "Class C - coefficient/carry FIFO destination",
            "Any `st.s8`/`st.s16` in Class C is a hard failure",
            "Class L - local byte-oriented cryptographic state",
            "Class R - token `rho` region",
            "Class H - token/result header fields",
            "Class Z - volatile zeroization",
            "Class S - serializer output packing",
            "Byte stores deliberately retained (not defects, not in scope)",
            "Do not use a global",
            "An unclassifiable store",
        ):
            with self.subTest(destination_aware_gate=required):
                self.assertIn(required, pending)
        # The retained-byte-store table must name every allowed class by source.
        for retained in ("Keccak", "SHAKE256", "PRF", "clear_bytes", "ByteEncode12"):
            with self.subTest(retained_class=retained):
                self.assertIn(retained, pending)
        # No text may claim the only surviving byte stores are the old triple.
        for forbidden in (
            "the only surviving byte stores",
            "the four surviving intentional byte-store sites",
            "absence of `st.s8` and",
        ):
            with self.subTest(no_global_allowlist=forbidden):
                self.assertNotIn(forbidden, pending)
                self.assertNotIn(forbidden, design)
        self.assertIn(
            "reject sub-word stores only for coefficient/carry destinations", design
        )
        self.assertIn("deliberately retained", design)

    def test_official_25_case_acvp_corpus_and_pending_gate_record_are_anchored(
        self,
    ) -> None:
        vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        self.assertEqual(vectors["parameterSet"], "ML-KEM-512")
        self.assertEqual(
            vectors["sourceCommit"], "975de31eb83d87039ec88934fdc47d8c312b892d"
        )
        self.assertEqual(
            vectors["source"],
            "https://github.com/usnistgov/ACVP-Server/tree/"
            "975de31eb83d87039ec88934fdc47d8c312b892d/"
            "gen-val/json-files/ML-KEM-keyGen-FIPS203",
        )
        self.assertEqual(
            vectors["sourceFiles"], ["prompt.json", "expectedResults.json"]
        )
        self.assertEqual(
            vectors["sourceSha256"]["prompt.json"],
            "3f9ce34f6c836c77958bad2729e837c3b213f44ac36c3065976e7acca6389523",
        )
        self.assertEqual(
            vectors["sourceSha256"]["expectedResults.json"],
            "a253d0ad91c95ebea5b409673defef0aa49d65d4ed72286399e2e798ddf073a4",
        )
        self.assertEqual(
            hashlib.sha256((PROVENANCE / "prompt.json").read_bytes()).hexdigest(),
            vectors["sourceSha256"]["prompt.json"],
        )
        self.assertEqual(
            hashlib.sha256(
                (PROVENANCE / "expectedResults.json").read_bytes()
            ).hexdigest(),
            vectors["sourceSha256"]["expectedResults.json"],
        )
        self.assertEqual(len(vectors["tests"]), 25)
        self.assertEqual(
            [case["tcId"] for case in vectors["tests"]], list(range(1, 26))
        )
        self.assertTrue(
            all(len(bytes.fromhex(case["d"])) == 32 for case in vectors["tests"])
        )
        self.assertTrue(
            all(len(bytes.fromhex(case["ekPKE"])) == 800 for case in vectors["tests"])
        )
        self.assertTrue(
            all(len(bytes.fromhex(case["dkPKE"])) == 768 for case in vectors["tests"])
        )
        self.assertIn(
            "Status: PENDING PHYSICAL VALIDATION", PENDING.read_text(encoding="utf-8")
        )
        self.assertIn("two host fills", DESIGN.read_text(encoding="utf-8"))
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_TOTAL = 25", gate)
        self.assertIn('print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")', gate)
        self.assertIn("return 2", gate)
        subprocess.run(
            [
                "python",
                str(EXTRACTOR),
                "--prompt",
                str(PROVENANCE / "prompt.json"),
                "--expected-results",
                str(PROVENANCE / "expectedResults.json"),
                "--compact",
                str(VECTORS),
            ],
            cwd=REPO,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(
            (REPO / "run_all_silicon_tests.py").read_text(encoding="utf-8"),
            subprocess.run(
                ["git", "show", "HEAD:run_all_silicon_tests.py"],
                cwd=REPO,
                check=True,
                capture_output=True,
                encoding="utf-8",
            ).stdout,
        )

    def test_terminal_probe_is_diagnostic_only_and_preserves_terminal_residency(
        self,
    ) -> None:
        source = inspect.getsource(terminal_probe)
        kernel = TERMINAL_PROBE.read_text(encoding="utf-8")
        production = inspect.getsource(graph)
        self.assertEqual(
            terminal_probe.BACKEND_LABEL,
            "dr2d-mlkem512-kpke-keygen:terminal-probe:diagnostic-only",
        )
        self.assertEqual(
            terminal_probe.DIAGNOSTIC_CASE1_REQUEST_ID,
            0xD2D00001,
        )
        self.assertEqual(source.count("ObjectFifo("), 4)
        self.assertEqual(source.count("Worker("), 2)
        self.assertEqual(source.count(" = ExternalFunction("), 2)
        for name in (
            "dr2d_probe_d",
            "dr2d_probe_descriptor",
            "dr2d_probe_final_token",
            "dr2d_probe_result",
        ):
            self.assertIn(f'name="{name}"', source)
        runtime_source = source.split("runtime = Runtime", 1)[1]
        self.assertIn("of_d.prod()", runtime_source)
        self.assertIn("of_descriptor.prod()", runtime_source)
        self.assertIn("of_result.cons()", runtime_source)
        self.assertNotIn("of_final.prod()", runtime_source)
        self.assertNotIn("of_final.cons()", runtime_source)
        tree = ast.parse(source)
        sequence = _function(tree, "sequence")
        calls = [node.value for node in sequence.body if isinstance(node, ast.Expr)]
        self.assertEqual([call.func.attr for call in calls], ["fill", "fill", "drain"])
        transfers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "to"
        ]
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0].func.value.id, "result_t")
        self.assertIn("dr2d_kpke_keygen_serialize", source)
        self.assertIn("dr2d_kpke_keygen_terminal_probe", source)
        self.assertIn("run_case1_terminal_probe_record", source)
        self.assertIn("kProbeRequestId = 0xD2D00001u", kernel)
        self.assertIn("store_probe_poly_pairs(final_token + kFinalT0Offset", kernel)
        self.assertIn("store_probe_poly_pairs(final_token + kFinalS1Offset", kernel)
        self.assertIn(
            "constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;",
            kernel,
        )
        self.assertIn(
            "if ((reinterpret_cast<uintptr_t>(out) & kWordAlignmentMask) != 0) return false;",
            kernel,
        )
        pair_store = kernel.split("static bool store_probe_poly_pairs", 1)[1].split(
            "static void produce", 1
        )[0]
        self.assertIn(
            "const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);", pair_store
        )
        self.assertIn("#include <new>", kernel)
        self.assertIn(
            "::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);",
            pair_store,
        )
        self.assertNotIn("store_le16(", pair_store)
        self.assertNotIn("reinterpret_cast<uint32_t *>", pair_store)
        self.assertNotIn("words[pair] = word;", pair_store)
        self.assertNotIn("stored_t1", kernel)
        self.assertNotIn("derive_g(", kernel)
        self.assertNotIn("sample_matrix_store(", kernel)
        self.assertNotIn("add_product_ntt(", kernel)
        self.assertNotIn("terminal_probe", production)
        serializer = (KERNELS / "dr2d_mlkem512_kpke_keygen_serialize.cc").read_text(
            encoding="utf-8"
        )
        commit_success = serializer.split("static void commit_success", 1)[1].split(
            "static void serialize", 1
        )[0]
        self.assertLess(
            commit_success.index("store_le32(result + 16"),
            commit_success.index("store_le32(result, kResultMagic)"),
        )
        self.assertIn("Success magic is the final device store.", commit_success)


if __name__ == "__main__":
    unittest.main()
