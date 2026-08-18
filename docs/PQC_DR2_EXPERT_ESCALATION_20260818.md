# DR2 expert escalation — 2026-08-18

**Disposition:** integrated DR2 is blocked. DR2d is a physical failure, not a production candidate. The preserved research branch and expert evidence packet are authorized for publication, but they must not be merged as a production milestone, packaged as a release, or used to authorize hardware execution or production-source changes.

This handoff consolidates the recorded evidence for expert review. It makes only the claim supported by the records: an integrated ML-KEM-512 K-PKE.KeyGen candidate executed and returned parseable records whose cryptographic payloads were systematically wrong. It does not assign a root cause.

## 1. Recovered decision timeline

| Stage | Date / evidence | Supported result and boundary |
|---|---|---|
| DR0 | Merged in PR #8, commit `7b38973789fafb950a26551bc947f4fcaa91ec25`; [`PQC_DR0_SILICON_VALIDATION_20260817.md`](PQC_DR0_SILICON_VALIDATION_20260817.md) | Narrow M33 ring-product physical result: `TOTAL 24/24 PASS`. It is not complete ML-DSA residency. |
| DR1 | Merged in PR #8, commit `7b38973789fafb950a26551bc947f4fcaa91ec25`; [`PQC_DR1_SILICON_VALIDATION_PENDING.md`](PQC_DR1_SILICON_VALIDATION_PENDING.md) | Narrow ML-DSA-44 ExpandA/rejection/NTT physical result: `TOTAL 33/33 PASS`, JIT key `c1b1aaa7ab02f303edff67b3`. |
| DR2a | [`PQC_DR2A_SILICON_VALIDATION_PENDING.md`](PQC_DR2A_SILICON_VALIDATION_PENDING.md) | Narrow ML-KEM-512 SampleNTT physical result: `TOTAL 13/13 PASS`; repeated `26/26`; cache `c65a53d2c8de882f9a5dc7d9`. |
| DR2b | DR2d audit’s passed-artifact comparison | Narrow CBD3/NTT physical comparator: passed 13-vector artifact at cache `4311961d4f3a43976aa5a60d`; core `0_3` ELF SHA-256 `0f1e4f9563a6716c3076bdc8ad4c8d43dc6dfd566cf0de2fd67b14d937261125`. |
| DR2c | [`PQC_DR2C_PHYSICAL_VALIDATION_HANDOFF_20260817.md`](PQC_DR2C_PHYSICAL_VALIDATION_HANDOFF_20260817.md) | Narrow terminal ML-KEM-512 `t_hat` row: `TOTAL 11/11 PASS`, repeated `22/22`. It excludes `G(d || k)`, both-row scheduling, serialization, and lifecycle zeroization. |
| DR2d | [`PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md`](PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md) | Integrated five-worker candidate compile-only review passed, but physical backend `dr2d-mlkem512-kpke-keygen:silicon` returned `TOTAL 0/25 FAIL`, exit 1. |

The DR2a/DR2b/DR2c results are intentionally narrow. They do not offset, convert, or partially close DR2d. The roadmap consequence is explicit: **no DR3 work until integrated DR2 completion**; see [`PQC_DEVICE_RESIDENCY_ROADMAP.md`](PQC_DEVICE_RESIDENCY_ROADMAP.md).

## 2. Exact architecture boundary

The failed DR2d candidate is an integrated ML-KEM-512 K-PKE.KeyGen topology with five repaired workers:

| Core | Worker | Bounded responsibility |
|---|---|---|
| `0_2` | W0 | derives `rho`/`sigma` from `D`, expands four SHAKE256 PRFs, runs CBD3/NTT, emits the 2,096-byte secret token. |
| `0_3` | W1 | row-0 expansion, retained `rho` copy, SampleNTT A00/A01, and matrix token production. |
| `0_4` | W2 | row-0 token consumption, copies and accumulation for `t_hat[0]`. |
| `0_5` | W3 | row-1 counterpart of W1. |
| `1_2` | W4 | row-1 counterpart of W2. |

The production boundary is protected by these recorded SHA-256 identities:

| Item | SHA-256 |
|---|---|
| canonical runner `run_all_silicon_tests.py` | `742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad` |
| production DR2d ABI | `a6f44c68787905f6b4819598baacac59bf5bcc4a3125c8151b7863345e9ff4f4` |
| production DR2d graph | `e17e17b8481bc1fa8492a7e2bc9184fbae095b55c5e175b015aa19a2bc999694` |
| W0 source | `2f94e2995706ac5636f35c66167e5dd8f54ac54b618c200bf4ee45b8b754ceaf` |
| W0 internal header | `16d61e6ada4d7de384b3981cc76d3de8319ce2bec999727d4847567e7e1f3519` |
| shared Keccak header | `0470fb39277478a368004a49e551a3411d8f9185b492ac01f85d2297bcea3c1f` |
| retained W0 comparison object | `7ea27cc5f6bb905253a161acd98988c62afc54855bcfd1c4530a55c441e28b70` |
| accepted V2 W0 diagnostic graph | `6b3d29aada8cc7c4be288899d55da20b3c286e0aa415101106bba4e86295f124` |
| accepted V2 W0 diagnostic runner | `b96e1d60981121feac33644ddcda38cc490d2ee8866300509941266383575da0` |

The accepted production-repair patch hash is `ea914b69dfa76cdac20926f2000fc9a7c3ffedc9e8c469e324f3ae4e61bf3c00`; the initial condensed store-map hash is `3ab8f6584e4ccd649a5d43abee43d2af84f13860ce5d1e2ac9cd9e0ca45f0835`.

## 3. What passed before the physical failure

Compile-only inspection supports lowering/placement facts, not arithmetic equality:

- all five repaired workers have no `st.s16` at all, and reviewed Class-C coefficient/carry paths use full-word `st`, not `st.s8`/`st.s16`;
- the W0 four coefficient destinations are 48, 560, 1,072, and 1,584, with 128 full 32-bit pair writes and a proved body/tail;
- W1/W3 and W2/W4 reviewed copy, SampleNTT, and accumulation paths have recorded guard, width, count, destination, and fail-closed evidence;
- topology, FIFO placement, serialization identity, endianness, linker program/data/stack reconciliation, and absence of an unintended host/spill route were reviewed;
- W2/W4 alignment helper, W0 CBD/NTT output helper, and the Class-C write paths passed their stated compile-only sub-gates.

The production physical gate nevertheless recorded 25 plain payload `FAIL`s, zero `ERROR`s, zero `PASS`es, an anchored silicon backend, parser success, and exit 1. The log hash is `1348dfb53446c4781c14b967fc535c5694cff2d1d56af097efc67cecd902be6c`.

## 4. Failure classification

The physical result is **valid parsed `STATUS_OK` records with a systematic cryptographic payload mismatch**. It is not evidence of a transport loss, status failure, CRC failure, whole-record failure, or known partial-width high-byte store failure. Compilation and execution did occur; parsing of every terminal record did occur; the compared payload was consistently wrong.

This is why a driver update is **not evidence-supported as the diagnosis**: the observed program executed and parsed systematically, while its cryptographic payloads were systematically incorrect. A driver/toolchain/environment experiment may be worthwhile only as a separately recorded reproduction with pinned versions, hashes, cache policy, and independent comparison. It must not be represented as a remedy or root cause without such evidence.

## 5. Authorized W0 localization: one `tcId-01` call

Exactly one guarded W0 diagnostic call was authorized and completed after the 0/25 run. Its scope was one W0-only token capture, with W1–W4 and serializer explicitly excluded.

| Field | Recorded value |
|---|---|
| case | ACVP `tcId-01` |
| `D` | `47b893474672ba92e4b12ee44fb32953af8e8503b5fb471d1614fb8a021a660a` |
| request ID | `3536846849` |
| diagnostic cache | `320b9680889452b524538534` |
| retained production comparison cache | `04f147d54cb01d160974a6e6` |
| native diagnostic backend | `dr2d-mlkem512-kpke-keygen:w0-token-tap:diagnostic-only` |
| authorized calls / exit | 1 / 0 |
| raw token | 2,096 bytes; SHA-256 `b7e75f7b55f8f3d30757ca5b0c3c9d13626b40e08cb5c6972681103395c20c53` |
| protected production hashes | unchanged before/after |

The first capture record stopped after `NATIVE_CALL_BEGIN=True`; the retry record is the completed capture. The completed record reports a valid token header/status, canonical u16 coefficient ranges for all four 512-byte polynomial regions, and retains the raw binary. Those properties establish a parseable W0 diagnostic token, not correct W0 arithmetic and not a DR2d pass.

### V1 and V2 W0 token-tap boundary

The first W0 diagnostic design (V1) failed before MLIR/cache generation because postponed `from __future__ import annotations` caused the pinned IRON `CompileTime[T]` introspector to miss `d_slots`, `descriptor_slots`, `secret_token_slots`, and `element_type`; specialization then rejected `d_slots`. V2 removes postponed annotations and adds the exact compile-parameter/specialization/MLIR contract. The V2 full patch SHA-256 is `250b3beeefd2202d77cba46f32ab0742f64c33cd152850aca426df6709465f22`; its V1-to-V2 correction hash is `e38d56bc87b8faa38405cefbc5152b1f180172c58d8ec9988890ba5bce0f71d3`.

V2’s architecture is intentionally diagnostic-only: 32-byte `D` ingress, 16-byte production descriptor ingress, direct 2,096-byte W0 secret-token egress, one unchanged W0 external function, two fills, one drain, and no W1–W4, serializer, terminal ABI, host KeyGen, reference fallback, or production-file modification. See [`PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818_HANDOFF.md`](PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818_HANDOFF.md).

## 6. Eliminated or narrowed hypotheses

The following are ruled out only to the stated boundary:

1. **The original partial-store/high-byte failure shape:** Class-C repaired writes were reviewed as full-word; the retained token mismatch pattern is not a high-byte-only loss.
2. **Standalone NTT target implementation:** W0’s NTT `[0x21a0,0x2370)` is instruction-identical modulo relocation to the physically passed DR2b NTT `[0x0ab0,0x0c80)`, size `0x1d0`. The passed DR2b artifact is cache `4311961d4f3a43976aa5a60d`, ELF hash `0f1e4f9563a6716c3076bdc8ad4c8d43dc6dfd566cf0de2fd67b14d937261125`.
3. **CBD3 arithmetic/loop/tail as captured:** the W0 inlined CBD3 and passed DR2b standalone CBD3 were reviewed as the same operations under register allocation/inlining, including the final computation/store; this does not prove every surrounding W0 value is correct.
4. **Simple output permutation, pair-lane swap, common Montgomery scale, and nonce remap 0–3:** the recorded `tcId-01` comparisons do not match the observed W0 first values.
5. **Stale SampleNTT pending state as an explanation for W0 secrets:** SampleNTT state is downstream in W1/W3, whereas the captured wrong secrets are W0 outputs.
6. **A broad ordinary source-level sigma/PRF counter/domain/offset/tail mistake set tested offline:** no tested natural variant matched the retained two-coefficient observation. This is narrowing evidence, not exhaustive proof.
7. **Shared Keccak target code, to the reviewed comparison boundary:** the corrected comparison against a passed DR2b Keccak artifact was recorded as ruling out that target implementation; it does not prove the W0 invocation’s data values.

Remaining plausible surfaces include sigma bytes before PRF, SHAKE256 PRF staging, a target-specific dataflow/context issue around the inlined W0 path, or corruption before/after NTT that the reviewed store map cannot expose. Do not convert this list into a diagnosis.

## 7. Sigma/PRF diagnostic chronology

The additive sigma/PRF trace is a semantic predecessor of CBD3: 800 bytes containing sigma (32 bytes) followed by four 192-byte SHAKE256 PRFs for nonces 0–3. It intentionally has no CBD3/NTT, no W1–W4, and no serializer. For `tcId-01`, the expected sigma SHA-256 is `0ae20d0e1bfe749b3e324d91e81e140156c6bf8a34063185acae84f0c91c3248`; expected PRF SHA-256 values (nonces 0–3) are `7be3f7375be9880cd97047361def65c0154f99d05781c7fdd6dbda3079ea6db3`, `1921bf3ea11ad75a9430a85204d8fb7f185fdfc26af02953d18dbe74a6a59d34`, `966fdd0b608b6bf671a67974ab25befa727908d592a000f0f13dc5b0df175761`, and `f2f858451147d532310d7a10727164c7f0685afeae8b7fe6cfa42463e03c2d61`.

| Attempt | Result | Evidence disposition |
|---|---|---|
| retry0 / original | Failed before specialization/compile: missing required keyword-only `d_slots`. | Historical failed attempt; preserved; **must not execute**. |
| retry1 | Refused because the wrapper’s original-evidence matcher did not accept the reviewed failure form. | Historical failed attempt; preserved; **must not execute**. |
| retry2 | Structural evidence-wrapper refusal remained; it preserved retry0/retry1 and corrected only gate assumptions. | Historical failed attempt; preserved; **must not execute**. |
| retry3 | Confirmed structural host failure before native work. | Historical failed attempt; preserved; **must not execute**. |
| retry4 | Confirmed structural compile-helper failure; the one-line correction is returning `_specialized_program`, not invoking it. | Historical failed attempt; preserved; **must not execute**. |
| retry5 | Confirmed structural precompile failure. | Historical failed attempt; preserved; **must not execute**. |
| retry6 | Completed the host/MLIR/compile/artifact-audit bundle successfully: five host/no-dispatch contracts passed; compile exit 0; `NPU_DISPATCH_ATTEMPTED=False`. | The **only completed sigma/PRF bundle**. It is compile-only/no-dispatch and is not a native execution or correctness result. |

Retry6 compiled into cache `337a8cdc94914d464c109ced`; its generated MLIR SHA-256 is `6f3cc8523e83e1bf99766795ed6d9fbc98f4d6dc17c3e918a66a65893dfc7d9c`. The current diagnostic hashes recorded by retry6 are: kernel `e4bc1201e69842db5b2d33aabcde8195fced6a603a6630bdf641d3497f40a94d`, graph `f59df8bede5c924a7ae59878bf1100fffe890562a3bde9649e59369078108bf7`, and contract test `d3dac863dd9cf5b48269e12a05f1f1e95028e04db481e2c6807908300ca6c315`.

### Exact retry-chain identities

| Artifact | SHA-256 |
|---|---|
| original diagnostic patch | `bcbfec3f904fb4b64e6457320bd7750adf2be66cb760f2c8ebc2e68af85f5204` |
| retry0 script | `acbf53ae2d9b4188f55c41e02eeaefb64bc7f7b19efa1a9c2bfe2cb9cc14897a` |
| retry1 graph-fix patch | `c1e09ebfd8b5a854547bb4b1be83c75a3c6ba2e59ab1c562ab4db541f08700dd` |
| retry1 script | `c011747822cfc3d526ade11e862c0667c0f15161ef430aedc8fb07a51d1eb348` |
| retry2 script | `44dba1b1cdf2117b4fb587274b5bff307767f3131f1593eb4b64c44aa6fe10c4` |
| retry3 script | `95e6664e4b9a72d4612f0cbed7dc46f05a72bc8c84cfe074a57d1446f918d35d` |
| retry4 graph-fix patch | `3b8aa183be358080d86517007c63c659ecc5f2b9772fe4ad74beea363942d2e5` |
| retry4 script | `634a703479cd5f75aa6d1d6b76d8c5f75597c2e9f45b3d32dbf18ceef4e857f6` |
| retry5 script | `78d77de3d1dd400536706690d3d0eee7bcd85f36c860abf0cf71e569bbb5ef63` |
| retry6 script | `d3ce9d0f8ad42304518844876f82dd0394161ac0a6948d0af74e7ce94a15e055` |

## 8. Current stop state and explicit non-claims

- No further native dispatch is authorized.
- The one W0 capture does not authorize a repeat, a sigma/PRF dispatch, a full production rerun, or a driver update trial.
- Retry6 does not prove the trace’s on-device bytes; it proves a compile-only/no-dispatch artifact path.
- No captured result proves sigma, PRF, CBD3, NTT, W0, W1–W4, serializer, KeyGen, ML-KEM, or FIPS 203 correctness.
- No evidence establishes a compiler, runtime, XRT, driver, firmware, hardware, or operating-system defect.
- No production modification, production-branch merge, release package, or claim expansion is authorized. Publication of this clearly marked research/escalation branch is a documentation and evidence-preservation action only.

### Recovered source and Git lineage

The 2026-08-18 laptop forensic export removed the earlier source-recovery
limitation. The uploaded transport archive matched SHA-256
`068e94f869aa9038dfc33b324b498ca79d96feb67e2fa94a89ea8ad8253cf6ed`;
all 11 internal manifest entries verified. The all-refs bundle exposed the
complete ordered local feature lineage:

| Stage | Original local commit | Tree | Parent |
|---|---|---|---|
| DR2a | `99c80ac34e78c39f66280c64b2109db5d25c0dd9` | `fcc5b85d20ef339bc9051a67d4c32bff9de75e6f` | `7b38973789fafb950a26551bc947f4fcaa91ec25` |
| DR2b | `8b1bff209b691f013420648dff3f2a022380a918` | `131aa54d43705f1ed465d6aff8bb9156fd197dc3` | `99c80ac34e78c39f66280c64b2109db5d25c0dd9` |
| lineage record | `c0a739090ba73ec700074c8ba6876abbb14bb0a4` | `78e8fd16c3deb0dba09ee7ef3fa2c3c9d7540d39` | `8b1bff209b691f013420648dff3f2a022380a918` |
| DR2c | `74c735b089b1e66ee5ff1a49b8abf1222cce8057` | `91134a06597f8197bc0766aaa904764b0bf87f7c` | `c0a739090ba73ec700074c8ba6876abbb14bb0a4` |
| accepted roadmap | `48b5e25e42ec63d5b8b79e67791c02d3420e8353` | `cdfca290ee0490ac2c5ed129beca8590134b93c8` | `74c735b089b1e66ee5ff1a49b8abf1222cce8057` |

The export also preserved safety commits
`d033a8d5165bdea0ab3ab1cceaed99c42b856544` and
`53e7b0e5c827bd015ccf5055c69ded2dc2e6c5bc`, 159 byte-exact
DR2-named working files, the tracked worktree patch, refs, reflogs,
unreachable-object inventory, and complete `.git` capture. The source and
evidence needed for expert continuation are now present on this branch. The
complete `.git` transport was intentionally not published because it includes
unrelated repository history; its verified identity and extracted DR2
provenance are recorded in
[`PQC_DR2_LOCAL_FORENSIC_RECOVERY_20260818.md`](PQC_DR2_LOCAL_FORENSIC_RECOVERY_20260818.md).

## 9. Expert reproduction sequence (read-only first)

1. Start from the pinned repository state and verify PR #8 baseline commit `7b38973789fafb950a26551bc947f4fcaa91ec25`, the protected production hashes in section 2, and the evidence manifest in [`pqc_dr2_evidence_20260818/SHA256SUMS`](pqc_dr2_evidence_20260818/SHA256SUMS).
2. Read [`PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md`](PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md) and the raw evidence inventory; do not run any historical script.
3. Independently parse the retained 2,096-byte raw W0 token and recompute its size/hash. Confirm only the documented structural properties; do not infer correctness from canonical coefficients.
4. Independently recreate the `tcId-01` FIPS 203 reference sigma/PRF/CBD3/NTT values and compare them with the recorded fixed anchors. Keep this host-only and preserve exact code/version hashes.
5. Re-review W0 invocation dataflow between derive-G, sigma extraction, SHAKE256 PRF staging, CBD3, NTT, and the four pair-store inputs against the retained object and cache identities.
6. Reproduce only retry6’s compile-only/no-dispatch gates in a separately recorded environment if necessary. Do not treat a new cache or compiled object as equal to the recorded artifact without a fresh identity and review.
7. Propose the smallest new **read-only or compile-only** discriminator. Any native run requires a new written authorization, a single explicit case, a new output location, complete pre/post hashes, preserved logs, and an independent stop rule.

## 10. Prioritized questions for the expert

1. Can an independent reconstruction identify a dataflow or calling-convention error at the derive-G/sigma/PRF boundary while preserving the reviewed NTT, CBD3, and store facts?
2. Which one additional non-invasive observation would distinguish wrong sigma, wrong PRF, wrong CBD input, wrong NTT input, and post-NTT persistence without widening the production path?
3. Is any IRON/LLVM-AIE/AIE2 behavior relevant to this exact use of the shared Keccak routine, inlined CBD3, pointer/address-space assumptions, or asynchronous object-FIFO lifetime that survives the existing static and cache comparisons?
4. What minimal environment matrix (driver, XRT, firmware, MLIR-AIE/LLVM-AIE versions, cache cleanliness) would be scientifically useful if separately authorized—and what outcome would actually change the hypothesis ranking?
5. What evidence is required before considering one additional native call, and how can it be guaranteed not to overwrite the preserved artifact set?

## Evidence index

- Production audit: [`PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md`](PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md)
- W0 V2 diagnostic handoff: [`PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818_HANDOFF.md`](PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818_HANDOFF.md)
- Evidence guide and safety classification: [`pqc_dr2_evidence_20260818/README.md`](pqc_dr2_evidence_20260818/README.md)
- Checksum manifest: [`pqc_dr2_evidence_20260818/SHA256SUMS`](pqc_dr2_evidence_20260818/SHA256SUMS)
- Laptop source-forensic recovery: [`PQC_DR2_LOCAL_FORENSIC_RECOVERY_20260818.md`](PQC_DR2_LOCAL_FORENSIC_RECOVERY_20260818.md)
- Recovered working-file checksum manifest: [`pqc_dr2_evidence_20260818/RECOVERED_LOCAL_SOURCE_SHA256SUMS`](pqc_dr2_evidence_20260818/RECOVERED_LOCAL_SOURCE_SHA256SUMS)

## References

- NIST FIPS 202, *SHA-3 Standard*: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- NIST FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard*: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 204, *Module-Lattice-Based Digital Signature Standard*: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
- MLIR-AIE 1.4.1 documentation: https://xilinx.github.io/mlir-aie/1.4.1/
- Xilinx mlir-aie pinned commit: https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22
- LLVM-AIE: https://github.com/Xilinx/llvm-aie
- XRT: https://github.com/Xilinx/XRT
- AMD XDNA kernel documentation: https://docs.kernel.org/accel/amdxdna/amdnpu.html
