# M33 native silicon-path handoff — 2026-08-17

## Scope completed

This change turns the M33 primitive and composer gates into **native-only**
hardware gates. A missing MLIR-AIE/IRON/XRT stack now produces an unavailable
diagnostic and a nonzero exit; it cannot silently pass through the prior Python
transliteration/reference backend.

No commit, push, remote operation, or modification of unrelated uncommitted
documentation was performed.

## Changed files

### New native runner package

- `phoenix_sdr_dsp/__init__.py`
- `phoenix_sdr_dsp/silicon/__init__.py`
- `phoenix_sdr_dsp/silicon/m33a_runner.py`
  - Exposes both `run_m33a(mode, in_a, in_b=None)` and the composer-compatible
    alias `run`.
  - Builds a one-tile MLIR-AIE/IRON graph with two input ObjectFifos:
    `in_a[256]` and packed `[mode, in_b[0], ..., in_b[255]]`, plus
    `out_c[256]`, all `int32`.
  - Uses XRT tensors and the existing C++ NTT kernel. It contains no host
    arithmetic fallback.
- `phoenix_sdr_dsp/silicon/m33b_runner.py`
  - Exposes both `run_m33b(mode, param, in_a, in_b=None)` and `run`.
  - Builds a one-tile graph with two input ObjectFifos: `in_a[256]` and
    packed `[mode, param, in_b[0], ..., in_b[255]]`, plus two outputs.
  - Uses XRT and contains no host arithmetic fallback.

### Existing kernel adapters

- `tests/m33_mldsa/dilithium_ntt_kernel.cc`
  - Adds `dilithium_ntt_controlled(int32_t ctrl[1], ...)`, forwarding
    `ctrl[0]` to the existing `uint8_t mode` entry point.
  - Adds `dilithium_ntt_packed(...)`, which fits the physical two-input-DMA
    limit by unpacking `mode` and `in_b` before calling the same entry point.
- `tests/m33_mldsa/dilithium_sampler_kernel.cc`
  - Adds `dilithium_sampler_controlled(int32_t ctrl[2], ...)`, forwarding
    `ctrl[0]` and `ctrl[1]` to the existing mode/param entry point.
  - Adds `dilithium_sampler_packed(...)`, which unpacks `mode`, `param`, and
    `in_b` from the second input DMA token.

The adapters add no arithmetic; their purpose is to marshal scalar fields
through the fixed-shape array ABI used by MLIR-AIE ObjectFifos.

The packed adapters were added after the first Phoenix compile reached the
placer and reported that a core tile provides two input DMA channels, while
the original control-plus-two-polynomial graph required three. No kernel
arithmetic changed in this topology correction.

An independent source audit then found that the original Montgomery reducer
multiplied a legal `int64` operand by `QINV` before narrowing, which can
overflow signed `int64`. The corrected implementation explicitly computes the
low 32 bits of that product, sign-extends the word, and only then performs the
bounded multiply by `q`. This preserves the pq-crystals reduction semantics.
The corrected M33a silicon path subsequently passed its complete 420/420
laptop gate.

### M33 gates and composer

- `tests/m33_mldsa/test_dilithium_ntt_m33a.py`
- `tests/m33_mldsa/test_dilithium_sampler_m33b.py`
  - Default path now requires the native runner.
  - Output is explicit and strict-runner compatible:
    `Backend: m33a:silicon` or `Backend: m33b:silicon`.
- `tests/m33_mldsa/test_mldsa_keygen_m33d.py`
- `tests/m33_mldsa/test_mldsa_sign_m33e.py`
- `tests/m33_mldsa/test_mldsa_verify_m33e.py`
  - Require both runners together; partial/reference composition is rejected.
  - Output is:
    `Backend: m33a:silicon, m33b:silicon`.
- `tests/m33_mldsa/mldsa_composer.py`
  - `SiliconBackend()` now defaults to the new native M33 runners.
  - Supplying only one dispatcher raises `ValueError`.
  - `reference_for_unit_tests()` is explicitly named for isolated host tests;
    it is not used by hardware gates.

### Tests and documentation

- `tests/test_m33_native_runner_contract.py`
  - Host-only checks for aliases, input validation, ABI adapters, strict labels,
    and absence of active primitive reference-fallback wiring.
- `docs/M33_SILICON_PROVENANCE.md`
  - Dedicated source, version/revision, license-status, usage, and
    copied/adapted-vs-consulted inventory.
- `docs/M33a_DESIGN.md`, `docs/M33b_DESIGN.md`, `docs/M33d_DESIGN.md`,
  `docs/M33e_DESIGN.md`
  - Corrected to describe native-only gates and avoid presenting sandbox
    reference results as hardware validation.

## Checks completed on the development host

The host has no `aie` module, no attached NPU, and no `dilithium_py` package.
Accordingly, no hardware claim was made and no ML-DSA KAT was executed here.

Passed:

```text
python -m unittest tests.test_m33_native_runner_contract tests.test_regression_validation -v
Ran 18 tests ... OK

python tools/m33a_kernel_transliteration_check.py
RESULT: PASS
python tools/m33b_kernel_transliteration_check.py
RESULT: PASS
python tools/m33d_kernel_transliteration_check.py
M33d composer transliteration check: PASS
python tools/m33e_kernel_transliteration_check.py
M33e Sign/Verify composer transliteration check: PASS

c++ -std=c++17 -fsyntax-only tests/m33_mldsa/dilithium_ntt_kernel.cc
c++ -std=c++17 -fsyntax-only tests/m33_mldsa/dilithium_sampler_kernel.cc
C++ syntax checks passed
```

Also passed:

```text
python -m py_compile phoenix_sdr_dsp/silicon/m33a_runner.py \
  phoenix_sdr_dsp/silicon/m33b_runner.py \
  tests/m33_mldsa/mldsa_composer.py \
  tests/test_m33_native_runner_contract.py
```

`git diff --check` reports pre-existing trailing whitespace in
`docs/PQC_COMPLETE_V1.md`, an unrelated uncommitted file; the M33-specific
diff passes its own `git diff --check -- <M33 paths>` check.

The attempted primitive command deliberately exited 2 rather than claiming
silicon because `dilithium-py` is absent:

```text
ERROR: dilithium-py is required (pip install dilithium-py).
exit=2
```

## Exact Windows Phoenix laptop commands

Run from the repository root in PowerShell. The first command assumes the
checkout has already been prepared with `python install.py`.

```powershell
$py = .\third_party\mlir-aie\ironenv\Scripts\python.exe
$env:PEANO_INSTALL_DIR = (Resolve-Path .\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie)

# Only if dilithium-py is not already installed in ironenv:
& $py -m pip install "dilithium-py==1.4.0"

# Fast host/static preflight:
& $py -m unittest tests.test_m33_native_runner_contract tests.test_regression_validation -v
& $py tools\m33a_kernel_transliteration_check.py
& $py tools\m33b_kernel_transliteration_check.py
& $py tools\m33d_kernel_transliteration_check.py
& $py tools\m33e_kernel_transliteration_check.py

# Native primitive gates:
& $py tests\m33_mldsa\test_dilithium_ntt_m33a.py
& $py tests\m33_mldsa\test_dilithium_sampler_m33b.py

# Native composed KAT gates:
& $py tests\m33_mldsa\test_mldsa_keygen_m33d.py
& $py tests\m33_mldsa\test_mldsa_sign_m33e.py
& $py tests\m33_mldsa\test_mldsa_verify_m33e.py

# Entire strict silicon matrix (optional; runs all non-M33 milestones too):
py run_all_silicon_tests.py
```

## Recorded Phoenix laptop results

The following native headers and totals were recorded on 2026-08-17:

```text
Backend: m33a:silicon
TOTAL 420/420 PASS

Backend: m33b:silicon
TOTAL 700/700 PASS

Backend: m33a:silicon, m33b:silicon
TOTAL 75/75 PASS       # M33d KeyGen

Backend: m33a:silicon, m33b:silicon
TOTAL 90/90 PASS       # M33e Sign_internal

Backend: m33a:silicon, m33b:silicon
TOTAL 90/90 PASS       # M33e Verify_internal
```

The strict policies in `run_all_silicon_tests.py` accept these backend strings
case-insensitively. Any `unavailable`, reference, fallback, or host backend
causes the process and strict matrix entry to fail.

## Hardware-only uncertainties and honest boundary

1. **The complete 34-invocation master suite is not yet recorded after these
   changes.** The five M33 invocations passed individually, but the strict
   aggregate runner remains the release-level regression gate.
2. **M33d/M33e are hybrid compositions by design.** NTT/INTT/basemul and
   rounding/hint/norm primitives now dispatch through M33a/M33b hardware.
   SHAKE calls, rejection sampling, `SampleInBall`, matrix/vector host
   accumulation, and packing remain host-side as already documented. The
   current composer does not route SHAKE through an M32c runner, so do not
   describe the full algorithm as entirely on-tile.
4. **Runtime may be long.** The composer intentionally performs many
   host-to-NPU round trips, one per polynomial primitive. Reuse of the cached
   `@iron.jit` program should avoid rebuilding the Python graph each call, but
   compile-cache behavior and total wall time are hardware-only measurements.
5. **If a native gate fails**, preserve the printed backend line and the first
   exception/Peano/XRT diagnostic. Do not enable `reference_for_unit_tests()`
   or reintroduce a fallback to convert the result into a hardware pass.

## Provenance

See `docs/M33_SILICON_PROVENANCE.md` for all consulted standards, vectors,
projects, runtime/toolchain components, exact URLs, known version status,
license status, local patterns, and copied/adapted/consulted classification.
