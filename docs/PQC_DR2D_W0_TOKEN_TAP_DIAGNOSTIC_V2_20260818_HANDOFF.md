# DR2d W0 token tap V2 — diagnostic-only handoff

**Date:** 2026-08-18  
**State:** V2 replacement prepared for independent review and compile-only inspection.  
**Native status:** **NOT AUTHORIZED.** No silicon command was run or authorized.  
**Production status:** Still **FAIL / NOT SAFE to push or package**.

## 1. Purpose

The production physical run returned valid, canonical, CRC-checked records but
failed all 25 ACVP payload comparisons. Static review exhausted the production
source, object, wrapper, FIFO, memory, relocation, and final-ELF surfaces without
finding a defect.

This additive artifact exposes the earliest complete semantic boundary: the raw
2,096-byte W0 secret token before W1-W4 and before the serializer.

It is a discriminator only. It is not a production fix, fallback, validation
pass, or canonical-runner entry.

## 2. Artifact

Unified patch:

`PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818.patch`

SHA-256:

`250b3beeefd2202d77cba46f32ab0742f64c33cd152850aca426df6709465f22`

Scope: exactly three new files, 599 insertions, zero modifications or deletions.

| New diagnostic-only file | Role |
|---|---|
| `phoenix_sdr_dsp/pqc/dr2d_mlkem512_kpke_keygen_w0_token_tap_graph.py` | One-worker graph, direct W0 token egress, token validation, production/object hash guards |
| `tests/pqc_device_resident/diagnose_dr2d_mlkem512_kpke_w0_token_tap.py` | Explicitly authorization-gated future one-call entrypoint; raw output and region hashes |
| `tests/pqc_device_resident/test_dr2d_mlkem512_kpke_w0_token_tap_contract.py` | Host-only topology, integrity, token, and refusal contracts |

No production file is in the patch.

For a tree where V1 is already applied, use only:

`PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V1_TO_V2_20260818.patch`

SHA-256:

`e38d56bc87b8faa38405cefbc5152b1f180172c58d8ec9988890ba5bce0f71d3`

The corrective patch changes only the two diagnostic files affected by V2:
34 insertions and 2 deletions. Do not apply the full V2 patch on top of V1.

## 2a. V1 defect and V2 correction

V1 placed `from __future__ import annotations` in the graph module. The pinned
IRON `CompileTime[T]` introspector received postponed string annotations rather
than the marker objects used by the production graph. Consequently
`design.compilable.compile_params` did not contain `d_slots`,
`descriptor_slots`, `secret_token_slots`, and `element_type`, and
`specialized.compile()` failed before MLIR/cache generation with unexpected
keyword `d_slots`.

V2 removes postponed annotations from the graph. It also adds a host contract
that:

1. constructs the `CallableDesign`;
2. requires the exact four compile-parameter names;
3. specializes with those exact names;
4. requires the specialized `compile_kwargs` names to match;
5. calls `specialized.as_mlir()` only;
6. checks the W0 symbol and direct secret-token FIFO are present and all
   downstream/serializer symbols are absent.

No tensor, `NPUKernel`, compile, cache, or dispatch is created by this contract.

## 3. Exact diagnostic topology

- Host ingress 0: D, exactly 32 bytes.
- Host ingress 1: production descriptor, exactly 16 bytes.
- Direct host egress: W0 secret token, exactly 2,096 bytes.
- One `ExternalFunction`: unchanged `dr2d_kpke_keygen_seed_noise`.
- One worker with the production W0 stack reservation `0x1000`.
- Two fills and one blocking drain.
- No W1, W2, W3, W4, serializer, terminal-result ABI, crypto reference,
  host KeyGen, or fallback.
- The output buffer starts as `0xA5` bytes so an unwritten result cannot parse
  as a valid token.

The successful token layout validated by the host is:

| Region | Offset | Bytes |
|---|---:|---:|
| ID/status/reserved header | 0 | 16 |
| rho | 16 | 32 |
| s_hat[0] | 48 | 512 |
| s_hat[1] | 560 | 512 |
| e_hat[0] | 1072 | 512 |
| e_hat[1] | 1584 | 512 |

Every polynomial coefficient is checked as little-endian uint16 and must be
less than q=3329. Error status records must have fixed-zero reserved bytes and
payload and raise rather than return data.

## 4. Fail-closed integrity guard

Before IRON/XRT loading, and again after any future dispatch, the graph requires
these exact hashes:

| Pinned production input | SHA-256 |
|---|---|
| W0 source | `2f94e2995706ac5636f35c66167e5dd8f54ac54b618c200bf4ee45b8b754ceaf` |
| Internal header | `16d61e6ada4d7de384b3981cc76d3de8319ce2bec999727d4847567e7e1f3519` |
| Production graph | `e17e17b8481bc1fa8492a7e2bc9184fbae095b55c5e175b015aa19a2bc999694` |
| Production ABI | `a6f44c68787905f6b4819598baacac59bf5bcc4a3125c8151b7863345e9ff4f4` |
| Canonical runner | `742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad` |
| Retained W0 comparison object | `7ea27cc5f6bb905253a161acd98988c62afc54855bcfd1c4530a55c441e28b70` |

The retained-object path defaults to:

`$HOME\.npu\cache\04f147d54cb01d160974a6e6\dr2d_kpke_keygen_seed_noise.o`

It can be overridden only with `PQC_DR2D_W0_RETAINED_OBJECT`; the replacement
must still have the exact pinned hash.

The pinned IRON `ExternalFunction` API used in this repository exposes
`source_file`, not a reviewed direct-object parameter. Therefore this patch
does not claim to link the retained object directly. It hash-gates that object
as the comparison witness and requires the newly compiled diagnostic W0
implementation sections to match it instruction-for-instruction modulo declared
relocations before any native authorization.

## 5. Host-only evidence already run

An isolated copy of the accepted tree plus the full V2 patch passed:

- `git apply --check`: PASS.
- `py_compile`: PASS.
- `ruff check`: PASS.
- `ruff format --check`: PASS.
- six environment-independent host contracts: PASS;
- the seventh no-dispatch IRON MLIR-generation contract is present and is
  mandatory in the pinned Windows IRON environment; it was skipped only in the
  Linux review sandbox where `aie` is unavailable.
- native entrypoint without authorization: refused with exit code 3.
- no output file was created by the refused invocation.

No IRON dispatch or silicon command was run.

## 6. Review/apply and host-only commands

Run from the repository root with the checkout-local IRON Python selected:

If V1 is already applied:

```powershell
$fix = ".\PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V1_TO_V2_20260818.patch"
if ((Get-FileHash -Algorithm SHA256 $fix).Hash -ne
    "E38D56BC87B8FAA38405CEFBC5152B1F180172C58D8EC9988890BA5BCE0F71D3") {
  throw "V1-to-V2 corrective patch hash mismatch"
}
git apply --check $fix
git apply $fix
```

For a baseline without V1, use the full V2 patch:

```powershell
$patch = ".\PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818.patch"
`$py` = ".\third_party\mlir-aie\ironenv\Scripts\python.exe"

git apply --check $patch
git apply --stat $patch

& `$py` -m py_compile `
  .\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_w0_token_tap_graph.py `
  .\tests\pqc_device_resident\diagnose_dr2d_mlkem512_kpke_w0_token_tap.py `
  .\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_w0_token_tap_contract.py

& `$py` -m ruff check `
  .\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_w0_token_tap_graph.py `
  .\tests\pqc_device_resident\diagnose_dr2d_mlkem512_kpke_w0_token_tap.py `
  .\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_w0_token_tap_contract.py

& `$py` -m ruff format --check `
  .\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_w0_token_tap_graph.py `
  .\tests\pqc_device_resident\diagnose_dr2d_mlkem512_kpke_w0_token_tap.py `
  .\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_w0_token_tap_contract.py

$env:PQC_DR2D_REQUIRE_IRON_MLIR_CONTRACT = "1"
try {
  & `$py` -m unittest `
    tests.pqc_device_resident.test_dr2d_mlkem512_kpke_w0_token_tap_contract -v
  if ($LASTEXITCODE -ne 0) { throw "V2 host/MLIR contracts failed" }
} finally {
  Remove-Item Env:PQC_DR2D_REQUIRE_IRON_MLIR_CONTRACT -ErrorAction SilentlyContinue
}
```

The revised non-executing compile-only script is:

`PQC_DR2D_W0_TOKEN_TAP_COMPILE_ONLY_V2_20260818.ps1`

SHA-256:

`7e47ccf9bc5f82c4d323c426efd9b72e3a2425ce69b70002b6c88f723668d71f`

It checks the exact compile-parameter names, exact specialization keys, and
`specialized.as_mlir()` topology before calling `specialized.compile()`.

Integrity preflight, still without compilation or execution:

```powershell
$env:PQC_DR2D_W0_RETAINED_OBJECT = `
  "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6\dr2d_kpke_keygen_seed_noise.o"

& `$py` -c @'
from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_w0_token_tap_graph as tap
for name, digest in tap.verify_production_hashes().items():
    print(f"{name}={digest}")
'@
```

Authorization refusal gate:

```powershell
Remove-Item Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION -ErrorAction SilentlyContinue
$refusalOutput = ".\UNAUTHORIZED_W0_TOKEN_SHOULD_NOT_EXIST.bin"
Remove-Item $refusalOutput -ErrorAction SilentlyContinue

& `$py` .\tests\pqc_device_resident\diagnose_dr2d_mlkem512_kpke_w0_token_tap.py `
  --d-hex ("00" * 32) --request-id 1 --output $refusalOutput

if ($LASTEXITCODE -ne 3) { throw "authorization guard did not return exit 3" }
if (Test-Path $refusalOutput) { throw "unauthorized diagnostic created output" }
```

## 7. Compile-only build rule

Do **not** use the diagnostic entrypoint as a way to populate the JIT cache:
calling the decorated function may dispatch after compilation.

Run only the signed V2 compile-only script. It uses the public
`CallableDesign.specialize(...).compile()` path, generates MLIR first, and never
invokes `CallableDesign.__call__` or constructs a tensor:

```powershell
& {
  $ErrorActionPreference = "Stop"
  $script = ".\PQC_DR2D_W0_TOKEN_TAP_COMPILE_ONLY_V2_20260818.ps1"
  $expected = "7E47CCF9BC5F82C4D323C426EFD9B72E3A2425CE69B70002B6C88F723668D71F"
  $evidence = ".\PQC_DR2D_W0_token_tap_compile_only_evidence_20260818.txt"
  if ((Get-FileHash -Algorithm SHA256 $script).Hash -ne $expected) {
    throw "V2 compile-only script hash mismatch"
  }
  if (Test-Path $evidence) {
    $raw = Get-Content $evidence -Raw
    if ($raw -notmatch "unexpected keyword argument 'd_slots'" -or
        $raw -notmatch "COMPILE_EXIT=1") {
      throw "Existing evidence is not the reviewed V1 pre-cache failure"
    }
    Remove-Item $evidence
  }
  Remove-Item Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION -ErrorAction SilentlyContinue
  $old = $env:PYTHONPATH
  $had = Test-Path Env:PYTHONPATH
  $root = (Resolve-Path ".").Path
  $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($old)) {
    $root
  } else {
    "$root$([IO.Path]::PathSeparator)$old"
  }
  try {
    $exe = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    & $exe -NoProfile -ExecutionPolicy Bypass -File $script
    if ($LASTEXITCODE -ne 0) { throw "V2 compile-only gate failed" }
  } finally {
    Remove-Item Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION -ErrorAction SilentlyContinue
    if ($had) { $env:PYTHONPATH = $old }
    else { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
  }
}
```

## 8. Mandatory compile-only evidence checklist

Stop on any missing or ambiguous item.

### Provenance and immutability

- Patch adds exactly the three listed files.
- All six pinned hashes pass before build and after evidence collection.
- Cache key/path, toolchain versions, commands, timestamps, and hashes recorded.
- Production graph, ABI, serializer, canonical runner, W0 source, and existing
  production cache remain byte-identical.

### Topology and ABI

- Exactly one logical worker/core.
- Exactly three object FIFOs: D 32, descriptor 16, secret token 2,096.
- Exactly two host fills and one blocking direct drain.
- Kernel call pointer order is D, descriptor, secret output.
- One `dr2d_kpke_keygen_seed_noise` call.
- No compiled source, symbol, or call for W1-W4, serializer, terminal probe, or
  host crypto/reference.
- No private intermediate FIFO and no second output.

### W0 object/ELF identity

- Diagnostic W0 stack reservation is `0x1000`.
- Retained object hash is exact.
- Newly compiled main/helper/Keccak/NTT/zeta section sizes match the retained
  object (`0xf30`, `0x870`, `0x7f0`, `0x1d0`, `0x100`).
- Every implementation instruction is byte-identical to the retained object or
  differs only at a declared relocation site.
- Relocations resolve only to expected local labels, helper, Keccak, NTT, zeta,
  `__umodsi3`, and the three diagnostic FIFO globals.
- No unresolved relocation, substituted function, linker relaxation, orphan
  allocation, or unexplained instruction difference.

### Stores, memory, and fail-closed behavior

- W0 alignment guard dominates all four coefficient commit loops.
- Each output region has 128 full-word commits and no Class C subword store.
- rho remains the retained 32-byte Class R byte copy.
- Program/data/stack fit with no overlap or spill route.
- Output sentinel, request ID/status/reserved validation, canonical checks,
  fixed-zero error-token rule, pre/post hash guard, and host zeroization remain.
- Unauthorized entrypoint still exits 3 and creates no file.

## 9. Native prohibition and later decision

Do not set:

`PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION=AUTHORIZED_AFTER_W0_TAP_COMPILE_ONLY_REVIEW`

No native call is authorized by this handoff. Return the compile-only evidence
for independent review. Only a separate explicit authorization may permit one
tcId-01 call. A future authorized call must retain the raw 2,096-byte token,
hash the complete record and all six semantic regions, and must not run a
25-case corpus.
