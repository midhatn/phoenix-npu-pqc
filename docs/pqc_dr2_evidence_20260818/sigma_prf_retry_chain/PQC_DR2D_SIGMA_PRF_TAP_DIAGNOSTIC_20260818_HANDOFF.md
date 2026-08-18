# DR2d sigma-plus-PRF tap — additive compile-only handoff

**Date:** 2026-08-18  
**Native NPU status:** **Not authorized and not executed.**  
**Production status:** Physical **FAIL / not safe to push or package** remains unchanged.

## Deliverables

| File | SHA-256 |
|---|---|
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_20260818.patch` | `bcbfec3f904fb4b64e6457320bd7750adf2be66cb760f2c8ebc2e68af85f5204` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_20260818.ps1` | `acbf53ae2d9b4188f55c41e02eeaefb64bc7f7b19efa1a9c2bfe2cb9cc14897a` |
| `PQC_DR2D_SIGMA_PRF_TAP_BUILD_VALIDATION_20260818.txt` | `396f7efab54c48b418852d51ee7c9496c47b84f8a1c3758c0bd53917dd2c8053` |

The patch adds three files only: a C++ trace kernel, a one-core graph, and host/no-dispatch contracts. It changes no production source, ABI, production graph, serializer, canonical runner, or prior V2 token-tap file.

## Trace contract

The output is exactly **800 bytes** and ends before CBD3:

| Offset | Bytes | Content |
|---:|---:|---|
| 0 | 32 | Derived sigma, bytes 32–63 of SHA3-512(`D || 0x02`) |
| 32 | 192 | Raw SHAKE256(`sigma || 0x00`) |
| 224 | 192 | Raw SHAKE256(`sigma || 0x01`) |
| 416 | 192 | Raw SHAKE256(`sigma || 0x02`) |
| 608 | 192 | Raw SHAKE256(`sigma || 0x03`) |

The additive C++ kernel uses the existing shared `phoenix_sdr_dsp::pqc::dr1::keccak_f1600` entrypoint and the evidenced byte staging: SHA3 rate 72/domain `0x06` for derive-G, and SHAKE rate 136/domain `0x1f` with the evidenced 136+56 squeeze. It has no CBD3 or NTT code and no W1–W4/serializer external function.

It is intentionally a **standalone semantic predecessor trace** rather than a change to the protected W0 three-pointer ABI. That is the only additive way to expose a pre-CBD boundary while retaining all pinned production hashes.

## Fail-closed inputs

The runner requires exact hashes for production W0 source (`2f94e2995706ac5636f35c66167e5dd8f54ac54b618c200bf4ee45b8b754ceaf`), internal header (`16d61e6ada4d7de384b3981cc76d3de8319ce2bec999727d4847567e7e1f3519`), shared Keccak header (`0470fb39277478a368004a49e551a3411d8f9185b492ac01f85d2297bcea3c1f`), production ABI (`a6f44c68787905f6b4819598baacac59bf5bcc4a3125c8151b7863345e9ff4f4`), production graph (`e17e17b8481bc1fa8492a7e2bc9184fbae095b55c5e175b015aa19a2bc999694`), canonical runner (`742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad`), and retained W0 witness object (`7ea27cc5f6bb905253a161acd98988c62afc54855bcfd1c4530a55c441e28b70`).

It also requires accepted V2 graph and runner hashes (`6b3d29aada8cc7c4be288899d55da20b3c286e0aa415101106bba4e86295f124` and `b96e1d60981121feac33644ddcda38cc490d2ee8866300509941266383575da0`) before applying the new patch.

The script refuses if either native-authorization environment variable exists, never sets one, never creates an XRT tensor, never calls a runner, and records `NPU_DISPATCH_ATTEMPTED=False`. Use a normal user account; do not grant administrator rights.

## Exact command

Copy the patch and script to the root of the existing V2 diagnostic checkout. From `C:\phoenix-sdr-dsp`, run:

```powershell
$patch = ".\PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_20260818.patch"
$script = ".\PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_20260818.ps1"

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $patch).Hash -ne
    "BCBFEC3F904FB4B64E6457320BD7750ADF2BE66CB760F2C8EBC2E68AF85F5204") { throw "sigma-plus-PRF patch hash mismatch" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script).Hash -ne
    "ACBF53AE2D9B4188F55C41E02EEAEFB64BC7F7B19EFA1A9C2BFE2CB9CC14897A") { throw "compile-only script hash mismatch" }

$exe = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
& $exe -NoProfile -ExecutionPolicy Bypass -File $script
if ($LASTEXITCODE -ne 0) { throw "sigma-plus-PRF compile-only bundle failed" }
```

The child-process execution-policy bypass is limited to this unsigned script and does not change the machine policy.

## What the command does

1. Verifies production, retained-object, and accepted V2 hashes before apply.
2. Runs `git apply --check`, applies the patch, and records the additive diff.
3. Runs Python syntax and host contracts; the IRON contract specializes and calls `as_mlir()` only.
4. Requires MLIR with one 32-byte ingress, one 800-byte egress, and only `dr2d_kpke_sigma_prf_tap` among DR2d external functions.
5. Uses `CallableDesign.specialize(...).compile()` without runtime tensor creation or callable invocation.
6. Audits generated text, object, and ELF artifacts with `llvm-readobj` and `llvm-objdump`; any W1–W4 or serializer symbol fails the run.
7. Rehashes protected files and emits `PQC_DR2D_sigma_prf_tap_apply_compile_only_evidence_20260818.txt` only on a `COMPILE_ONLY_GATE=PASS` path.

Do not set `PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION` or `PQC_DR2D_SIGMA_PRF_TAP_NATIVE_AUTHORIZATION`; do not dispatch the tap, run silicon, push, or package.

## tcId-01 host anchors

For `D=47b893474672ba92e4b12ee44fb32953af8e8503b5fb471d1614fb8a021a660a`:

- sigma: `5d3628d3edbeb81cde94bd2adc989020343cb2c5ab8f3c922e66d1cde54ef3a0`;
- sigma SHA-256: `0ae20d0e1bfe749b3e324d91e81e140156c6bf8a34063185acae84f0c91c3248`;
- PRF SHA-256 for nonces 0–3: `7be3f7375be9880cd97047361def65c0154f99d05781c7fdd6dbda3079ea6db3`, `1921bf3ea11ad75a9430a85204d8fb7f185fdfc26af02953d18dbe74a6a59d34`, `966fdd0b608b6bf671a67974ab25befa727908d592a000f0f13dc5b0df175761`, `f2f858451147d532310d7a10727164c7f0685afeae8b7fe6cfa42463e03c2d61`.
