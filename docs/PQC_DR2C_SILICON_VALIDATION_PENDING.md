# DR2c Silicon Validation Record

**Status: PHYSICAL PASS for the narrow DR2c milestone.** On 2026-08-17, the
corrected two-host-input terminal ML-KEM-512 K-PKE.KeyGen row graph compiled,
linked, placed, routed, and executed on a physical Phoenix NPU through IRON.
The native gate reported `dr2c-mlkem512-keygen-row:silicon`; all 11 named
frozen-corpus cases passed against the independent direct FIPS 203 oracle,
printing `TOTAL 11/11 PASS` and returning exit code 0.

## Validated scope

DR2c accepts exactly two host ingress buffers: packed
`rho[32] || sigma[32]` (64 bytes) and its strict 16-byte descriptor. It derives
the selected matrix row and secret/error NTT-domain polynomials within the AIE
graph, executes both `MultiplyNTTs` operations and accumulation, and exposes
only one terminal canonical 256-lane \(\widehat t[\mathrm{row}]\) result plus
status. The private 2,576-byte five-polynomial token has no shim allocation or
flow.

The physical corpus is the native gate's 11 deterministic requests: both rows
for fixed `rho=00..1f` / `sigma=20..3f`, eight varied seed pairs with
alternating rows, and one alternating-byte boundary request for row 1.

## Definitive physical evidence

| Item | Recorded value |
|---|---|
| First native backend | `dr2c-mlkem512-keygen-row:silicon` |
| First native corpus | all 11 named cases PASS; `TOTAL 11/11 PASS`; exit 0 |
| Repeated-operation result | `_run_native_gate()` invoked twice in the same Python process; two `TOTAL 11/11 PASS` results; 22/22 aggregate; exit 0 |
| JIT cache | key/path basename `8a683c16baee47604da595bf` under `$HOME/.npu/cache` |
| Packaged-artifact timestamp | 2026-08-17 21:52:40 +03 |
| XCLBIN | `final.xclbin`, 23,320 bytes |
| PDI | `main.pdi`, 16,864 bytes |
| Partition metadata | `partition_main.json`, 717 bytes; PDI UUID `1f1acd91-079d-4190-9367-6ecec2c18fe5`; pdi_id `0x01`; DPU kernel `0x901`; PRIMARY; column width 4 from column 0 |
| Memory topology | `memTopology_main.json`, 399 bytes; HOST and SRAM entries present |
| Operations-per-cycle metadata | 2048; metadata only, not a measured performance claim |
| Focused host evidence before physical execution | 14/14 PASS; Ruff PASS; `git diff --check` PASS |

The repeated native invocation reused the successful graph in one Python
process and exercised request reset over 22 sequential terminal-row requests.
Every successful request returned the terminal success ABI checked by the
native gate's independent oracle.

## Compiler-reported program size and linker memory

`llvm-size` and the generated linker artifacts reported:

| Core | Worker role | ELF path | File length | `.text` | `.data` | `.comment` | Reported total | Explicit stack |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `(0,2)` | expansion | `elfs_main_core_0_2/elfs_main_core_0_2.elf` | 12,208 B | 8,688 B | 256 B | 197 B | 9,141 B | `0x4000` (16 KiB) |
| `(0,3)` | accumulation | `elfs_main_core_0_3/elfs_main_core_0_3.elf` | 8,628 B | 5,552 B | 256 B | 197 B | 6,005 B | `0x4000` (16 KiB) |

Both linker program regions have origin 0 and length `0x0020000` (128 KiB).
Core `(0,2)` has data origin `0x7C050`, length `0x3FB0`; core `(0,3)` has data
origin `0x7C008`, length `0x3FF8`.

## ObjectFIFO allocation, placement, and DMA routes

Logical `aie.mlir` contains exactly two cores and exactly four depth-two
ObjectFIFOs:

| ObjectFIFO | Bytes | Logical direction |
|---|---:|---|
| `dr2c_descriptor` | 16 | shim → logical core |
| `dr2c_result` | 528 | logical core 0 → shim |
| `dr2c_row_token` | 2,576 | logical core → logical core 0 |
| `dr2c_seeds` | 64 | shim → logical core |

Placed buffers are:

- `dr2c_seeds` on tile `(0,2)`: address 49,152, bank 3; address 18,976,
  bank 1.
- `dr2c_row_token` on tile `(0,2)`: address 16,384, bank 1; address 32,768,
  bank 2.
- `dr2c_result` on tile `(0,3)`: address 16,384, bank 1; address 32,768,
  bank 2.
- `dr2c_descriptor` on tile `(0,2)`: address 35,360, bank 2; address 49,216,
  bank 3.

The recorded flows are exactly:

- shim `(0,0)` DMA0 → tile `(0,2)` DMA0 for `dr2c_descriptor`;
- tile `(0,3)` DMA0 → shim `(0,0)` DMA0 for `dr2c_result`; and
- shim `(0,0)` DMA1 → tile `(0,2)` DMA1 for `dr2c_seeds`.

Shim allocations are exactly descriptor MM2S0, result S2MM0, and seeds MM2S1.
There is no shim allocation or flow for `dr2c_row_token`. This is placement and
route evidence for the stated terminal-only graph boundary: the packed seeds
and descriptor enter, the completed \(\widehat t\) row exits, and the private
five-polynomial token remains inside the AIE graph.

## Reproduction boundary

The native-only command remains:

```powershell
py .\tests\pqc_device_resident\test_dr2c_mlkem512_keygen_row_silicon.py
```

A missing runtime prints the unavailable backend and exits 2; that is not a
pass. The recorded physical execution instead used the silicon backend and the
anchored 11-case total above. The focused host suite, Ruff, and whitespace
checks are host evidence; malformed descriptor/internal-token fault injection
remains compiled-harness and source-contract evidence unless separately run on
native hardware.

`run_all_silicon_tests.py` remains unchanged. Canonical-runner integration is
not established by this narrow record.

## Claim boundary

This record establishes physical exact-output execution only for **one
terminal ML-KEM-512 \(\widehat t\) row** per successful request under the
11-case corpus and the documented two-input/one-output DMA boundary. It does
not establish complete K-PKE.KeyGen or complete ML-KEM: `G(d || k)`, both-row
scheduling, public-key or secret-key serialization, and lifecycle zeroization
are not resident in DR2c.

Do not infer a performance result from operations-per-cycle metadata. Do not
claim complete FIPS 203 conformance, constant-time behavior, secure
zeroization, side-channel resistance, security hardening, CMVP validation, or
certification.
