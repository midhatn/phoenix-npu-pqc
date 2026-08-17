# M33 ML-DSA silicon-path provenance and attribution

**Scope.** This inventory records external resources and in-repository patterns
consulted for the native M33a/M33b runner integration. It distinguishes
algorithm sources from host-runtime API patterns: the new Python runners do
not copy cryptographic arithmetic from a third party; they dispatch the
repository's existing AIE2 C++ kernels. Versions and licenses are marked
**unknown / not independently verified** when this work did not inspect the
upstream release metadata or LICENSE file. Do not infer a stronger claim from
an entry marked that way.

## Cryptographic standards and vectors

| Source | Exact URL; version / revision | Relevant section or local path | License / status | Use and relationship |
|:--|:--|:--|:--|:--|
| NIST, *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions* (FIPS 202) | <https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf>; Aug. 2015 edition, no commit | SHAKE functions referenced by M33 design; M33 reuses the M32c hashing layer conceptually but does not add a SHAKE runner | U.S. Government publication; no software license asserted here | **Consulted only.** Documents the SHAKE primitive relied on by the existing composer/reference implementation. |
| NIST, *Module-Lattice-Based Key-Encapsulation Mechanism Standard* (FIPS 203) | <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf>; Aug. 2024, no commit | MLIR-AIE host dispatch pattern was adapted from this repository's M32 ML-KEM tests | U.S. Government publication; no software license asserted here | **Consulted only.** It is not an ML-DSA algorithm source; it contextualizes the existing M32 control-buffer runner pattern. |
| NIST, *Module-Lattice-Based Digital Signature Standard* (FIPS 204) | <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>; Aug. 2024, no commit | Algorithms 29–34 (rounding/hints), NTT-related ML-DSA operations, Algorithms 6–8 (composer contracts) | U.S. Government publication; no software license asserted here | **Consulted.** Constants, mode semantics, and tests in existing M33 files are based on it. New runners merely transmit the existing kernel inputs/outputs. |
| NIST ACVP-Server, ML-DSA FIPS 204 JSON vectors | <https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files>; exact commit **not recorded / unknown** | `tests/m33_mldsa/vectors/ML-DSA-{keyGen,sigGen,sigVer}-FIPS204_{prompt,expectedResults}.json` | Upstream license **not independently verified**; inspect ACVP-Server repository before redistribution | **Previously vendored data; consulted and executed by the existing gates.** No vector content was modified or newly copied by this integration. |

## Algorithm and reference-implementation sources

| Source | Exact URL; version / revision | Relevant section or local path | License / status | Use and relationship |
|:--|:--|:--|:--|:--|
| pq-crystals, Dilithium reference implementation | <https://github.com/pq-crystals/dilithium>; existing M33 docs cite `ref/ntt.c` and `ref/rounding.c`; exact commit **not recorded / unknown** | `tests/m33_mldsa/dilithium_ntt_kernel.cc`; `tests/m33_mldsa/dilithium_sampler_kernel.cc` | Upstream license **not independently verified in this integration**; consult its `LICENSE` | **Existing kernels are documented as transliterations/adaptations.** The runner code does not copy its arithmetic; it invokes those existing local kernels. |
| Giacomo Pope, `dilithium-py` | <https://github.com/GiacomoPope/dilithium-py>; existing M33 files name v1.4.0; exact commit **not recorded / unknown** | `tests/m33_mldsa/mldsa_composer.py`; M33 primitive test oracle calls | Upstream license **not independently verified in this integration**; consult upstream metadata / `LICENSE` | **Consulted through the existing dependency.** It remains a KAT/reference oracle; it is not used as a hardware fallback in M33 silicon gates after this change. |

## MLIR-AIE, compiler, and runtime sources

| Source | Exact URL; version / revision | Relevant section or local path | License / status | Use and relationship |
|:--|:--|:--|:--|:--|
| AMD/Xilinx MLIR-AIE documentation, IRON API | <https://xilinx.github.io/mlir-aie/1.4.1/>; v1.4.1 | `ObjectFifo`, `Worker`, `Runtime`, `Program`, `ExternalFunction`, `XRTTensor` usage in the new runners | Upstream license **not independently verified in this integration**; consult the MLIR-AIE repository `LICENSE` | **API pattern consulted and adapted.** The runners implement the same one-token ObjectFifo graph used by local M32 tests. |
| AMD/Xilinx MLIR-AIE source tree | <https://github.com/Xilinx/mlir-aie>; local integration has `third_party/mlir-aie`; an existing local note references commit `3ca0193` for a runtime API link, but that commit was **not independently revalidated** here | `run_all_silicon_tests.py` `ironenv` bootstrap paths | Upstream license **not independently verified in this integration** | **Consulted only** for project/runtime provenance; no source code copied. |
| LLVM-AIE / Peano toolchain | <https://github.com/Xilinx/llvm-aie>; version / commit **unknown** | `third_party/mlir-aie/ironenv/Lib/site-packages/llvm-aie`, selected by `PEANO_INSTALL_DIR` in `run_all_silicon_tests.py` | Upstream license **not independently verified in this integration** | **Toolchain dependency only.** It compiles the AIE2 C++ kernels invoked by IRON. No code copied. |
| Xilinx Runtime (XRT) | <https://github.com/Xilinx/XRT>; version / commit **unknown** | `aie.utils.hostruntime.xrtruntime.tensor.XRTTensor` in the new runners | Upstream license **not independently verified in this integration** | **API/runtime dependency only.** `XRTTensor` is used to place buffers on device and retrieve results. No code copied. |

## In-repository patterns and artifacts

| Local source | Relevant files / identifiers | License / status | Use and relationship |
|:--|:--|:--|:--|
| Existing M32b native NTT pattern | `tests/m32_mlkem/test_ntt_m32b.py`: `ntt_program`, `_pack_ctrl`, `_dispatch`; `tests/m32_mlkem/ntt_kernel.cc` control-array ABI | Repository-local; consult repository licensing policy (no assertion made here) | **Adapted structurally.** M33a uses two input ObjectFifos and one output; mode and the second polynomial share a packed input token to fit the Phoenix XDNA1 two-input-DMA limit. |
| Existing M32d multi-buffer pattern | `tests/m32_mlkem/test_kpke_m32d.py`: `kpke_program`, `_dispatch`; `tests/m32_mlkem/kpke_kernel.cc` | Repository-local; consult repository licensing policy (no assertion made here) | **Adapted structurally.** M33b uses two input ObjectFifos and two outputs; mode, param, and the second polynomial share one packed input token. |
| Existing regression policy | `run_all_silicon_tests.py`: `validate_test_output`, policies `m33_primitive_silicon` and `m33_composer_silicon` | Repository-local | **Consulted and made stricter in practice.** New M33 test output uses exactly `Backend: m33a:silicon` or `Backend: m33a:silicon, m33b:silicon`; unavailable native dependencies cause exit 2 rather than a reference pass. |
| Existing M33 C++ kernels | `tests/m33_mldsa/dilithium_ntt_kernel.cc`; `tests/m33_mldsa/dilithium_sampler_kernel.cc` | SPDX header in both files: Apache-2.0 | **Reused with one defined-arithmetic correction.** The NTT Montgomery reducer now computes the low 32 bits of the `QINV` product and explicitly sign-extends that word before the final multiply by `q`, preserving pq-crystals semantics without signed `int64_t` overflow. The integration also adds `*_controlled` ABI shims and two-input-DMA `*_packed` shims that unpack control fields and the second polynomial before forwarding to the pre-existing kernel entry points. |
| M33a defined-arithmetic regression | `tools/m33a_montgomery_defined_check.cpp` | SPDX Apache-2.0; new repository-local test | **New test.** Includes the actual M33a kernel, exercises maximal and deterministic BASEMUL inputs under UBSan, and compares all 256 lanes against independent modular `a*b*R^-1 mod q` arithmetic. |
| New native integration | `phoenix_sdr_dsp/silicon/m33a_runner.py`; `phoenix_sdr_dsp/silicon/m33b_runner.py` | Repository-local; consult repository licensing policy | **New code.** Implements only input validation, XRT tensor setup, MLIR-AIE graph construction, native dispatch, and explicit error handling. It contains no CPU mathematical fallback. |

## Reproduction boundary

The native claim is established only when a Windows Phoenix/XDNA1 laptop with
the checkout-local `ironenv`, LLVM-AIE/Peano, and XRT can compile and execute
the runners, and the tests return zero after their KAT comparisons. A local
static check, a dependency-import check, a Python transliteration, or an ACVP
comparison without successful native dispatch is **not** evidence of silicon
execution.
