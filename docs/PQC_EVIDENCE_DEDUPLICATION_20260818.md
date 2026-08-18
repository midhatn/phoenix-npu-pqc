# DR2 evidence deduplication record — 2026-08-18

## Decision and invariant

This record removes only root-level copies whose bytes exactly matched an entry
already covered by `docs/pqc_dr2_evidence_20260818/SHA256SUMS`. The protected
copy remains the sole canonical artifact. Neither the protected directory nor
its manifest was modified.

No unique evidence, historical log, or non-manifested artifact was deleted.
In particular, PII-bearing unique evidence remains retained because it is
historical material; its machine paths/user identifiers are an access and
publication risk, not a reason to rewrite evidence in place. See
[`SECURITY.md`](../SECURITY.md) and
[`PQC_AUDIT_REMEDIATION_20260818.md`](PQC_AUDIT_REMEDIATION_20260818.md).

## Deleted duplicate paths and canonical replacements

| Deleted root path | Canonical protected path | SHA-256 |
| --- | --- | --- |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_20260818.ps1` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_20260818.ps1` | `acbf53ae2d9b4188f55c41e02eeaefb64bc7f7b19efa1a9c2bfe2cb9cc14897a` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY1_20260818.ps1` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY1_20260818.ps1` | `c011747822cfc3d526ade11e862c0667c0f15161ef430aedc8fb07a51d1eb348` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY2_20260818.ps1` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY2_20260818.ps1` | `44dba1b1cdf2117b4fb587274b5bff307767f3131f1593eb4b64c44aa6fe10c4` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY3_20260818.ps1` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY3_20260818.ps1` | `95e6664e4b9a72d4612f0cbed7dc46f05a72bc8c84cfe074a57d1446f918d35d` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY4_20260818.ps1` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY4_20260818.ps1` | `634a703479cd5f75aa6d1d6b76d8c5f75597c2e9f45b3d32dbf18ceef4e857f6` |
| `PQC_DR2D_SIGMA_PRF_TAP_COMPILE_ONLY_RETRY5_20260818.ps1` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_COMPILE_ONLY_RETRY5_20260818.ps1` | `78d77de3d1dd400536706690d3d0eee7bcd85f36c860abf0cf71e569bbb5ef63` |
| `PQC_DR2D_SIGMA_PRF_TAP_COMPILE_ONLY_RETRY6_20260818.ps1` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_COMPILE_ONLY_RETRY6_20260818.ps1` | `d3ce9d0f8ad42304518844876f82dd0394161ac0a6948d0af74e7ce94a15e055` |
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_20260818.patch` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_20260818.patch` | `bcbfec3f904fb4b64e6457320bd7750adf2be66cb760f2c8ebc2e68af85f5204` |
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch` | `c1e09ebfd8b5a854547bb4b1be83c75a3c6ba2e59ab1c562ab4db541f08700dd` |
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY4_FIX_20260818.patch` | `sigma_prf_retry_chain/PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY4_FIX_20260818.patch` | `3b8aa183be358080d86517007c63c659ecc5f2b9772fe4ad74beea363942d2e5` |
| `PQC_DR2D_W0_compile_invocation_and_intermediates_20260818.txt` | `PQC_DR2D_W0_compile_invocation_and_intermediates_20260818.txt` | `c1db7524232eb8b8765221be62fde8da946c24a2aca33a803eba533036a2c967` |
| `PQC_DR2D_W0_complete_IR_metadata_objects_20260818.txt` | `PQC_DR2D_W0_complete_IR_metadata_objects_20260818.txt` | `30f1f61edad508ded2e39360e468dd91012113709eabf5ab06f13c8b66aedb06` |
| `PQC_DR2D_W0_pair_pack_vs_passed_terminal_probe_20260818.txt` | `PQC_DR2D_W0_pair_pack_vs_passed_terminal_probe_20260818.txt` | `ca0097bbd8a6cbe2e98842b7df79c8361c8f3e4f870d88dfbe8b5bce92729ca0` |
| `PQC_DR2D_W0_relocations_and_final_link_20260818.txt` | `PQC_DR2D_W0_relocations_and_final_link_20260818.txt` | `f56521866e96afc77bcc4fbfa2853f5adb0d60ed192facb5dd8c20afd278c706` |
| `PQC_DR2D_W0_token_tap_compile_only_evidence_20260818.txt` | `PQC_DR2D_W0_token_tap_compile_only_evidence_20260818.txt` | `69bba9a440a99b95acee99d3d4885e83f63ae5734752d57bd52454feff11f6df` |
| `PQC_DR2D_W0_token_tap_tcId01_native_evidence_20260818.txt` | `PQC_DR2D_W0_token_tap_tcId01_native_evidence_20260818.txt` | `4f40e3f235906752e37da3608ae2187c75e7ee47a186ef96196bc4b4cd19262b` |
| `PQC_DR2D_W0_token_tap_tcId01_native_evidence_retry1_20260818.txt` | `PQC_DR2D_W0_token_tap_tcId01_native_evidence_retry1_20260818.txt` | `9a9f976862e18c3b491431d85633a5d2e0740da6d7501bcf95001f45c711f83d` |
| `PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin` | `PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin` | `b7e75f7b55f8f3d30757ca5b0c3c9d13626b40e08cb5c6972681103395c20c53` |
| `PQC_DR2D_derive_sigma_and_copy_words_20260818.txt` | `PQC_DR2D_derive_sigma_and_copy_words_20260818.txt` | `7ce15c4d207aa09762c6f5aaa44ceb7b5b8fda76b28b9bf505e1a0377b9de05b` |
| `PQC_DR2D_sigma_prf_tap_apply_compile_only_retry6_evidence_20260818.txt` | `PQC_DR2D_sigma_prf_tap_apply_compile_only_retry6_evidence_20260818.txt` | `565ae3e37a0b687ec057d6a8069ab9a5a03d37608018469294c0618375f8f77b` |

The `scripts/` retry6 copy was retained because its checkout EOL conversion
means it is not byte-identical in the working tree, even though its Git blob
shares source content with the protected record.
