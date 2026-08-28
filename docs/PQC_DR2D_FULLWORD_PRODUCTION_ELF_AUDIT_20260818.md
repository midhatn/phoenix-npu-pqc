# DR2d V2 Phoenix production ELF store audit

**Date:** 2026-08-18  
**Audited evidence set:** condensed and unfiltered six-core disassembly, provenance/endianness manifests, placed MLIR memory/topology inventory, six linker scripts, and six ELF section/program-header reports  
**Initial condensed store-map SHA-256:** `3ab8f6584e4ccd649a5d43abee43d2af84f13860ce5d1e2ac9cd9e0ca45f0835`  
**Source baseline:** accepted V2 production repair, patch SHA-256 `ea914b69dfa76cdac20926f2000fc9a7c3ffedc9e8c469e324f3ae4e61bf3c00`  
**Core map:** `0_2=W0`, `0_3=W1`, `0_4=W2`, `0_5=W3`, `1_2=W4`  
**Store-map result:** **PASS — all five repaired workers**  
**Overall compile-only result:** **PASS**  
**Production physical result:** **FAIL — anchored silicon backend, `TOTAL 0/25 FAIL`, exit 1**

## 1. Executive conclusion

The complete accumulated Phoenix evidence proves that the workaround lowered as intended:

- no `st.s16` appears anywhere in any of the five repaired cores;
- every visible store at a candidate Class C coefficient/carry output site is unsuffixed `st` (the AIE scalar full-word form), not `st.s8` or `st.s16`;
- no `st.s8` appears in the visible W0 coefficient pair-write ZOL body or its pipelined epilogue/delay slots;
- no `st.s8` appears at the visible W1/W3 SampleNTT pair-commit sites;
- no `st.s8` appears in the visible W1/W3 polynomial-copy loop, W2/W4 polynomial/carry-copy loop, or W2/W4 accumulation-write window.

Subsequent unfiltered disassembly closed every destination, call-span, loop/tail, alignment, and remaining-byte-store classification left open by the initial condensed map. Fresh provenance, serializer identity, endianness, generated topology/residency, FIFO placement, and linker-level program/data/stack reconciliation also pass. There is no Class C `st.s8`/`st.s16`, unclassifiable store, overflow, overlap, orphan load segment, or unintended host/spill route.

**Disposition:** **PHYSICAL FAIL — DO NOT RUN HARDWARE AGAIN, PUSH, OR PACKAGE.** Compile-only inspection passed, but the first authorized production run failed all 25 ACVP cases. The single guarded tcId-01 localization call has now completed; no further hardware action is authorized.

### 2026-08-18 guard-evidence update

Unfiltered disassembly for both `core_0_4` and `core_1_2` shows the identical `add_product_ntt` entry sequence:

- `0xf94`: `mova r0, #0x3`;
- `0xf9a`: `and r0, r1, r0`;
- `0xfa2`: `jnz r0, #0x13e0`.

This computes `pointer & 3` for the pointer represented by `r1` and branches to the failure/return block iff any low alignment bit is set. The aligned fall-through enters the repaired add-product body. With a single function entry and no alternate entry into the body, this guard dominates the W2/W4 add-product Class C write path. The W2/W4 **add-product helper guard sub-gate is PASS**. This evidence does not by itself identify the final pair-store addresses, prove 64-group/tail coverage, prove the two call destinations, or close worker-level and `copy_words` guard dominance.

Additional unfiltered W0 evidence closes the `cbd3_ntt_store_dr2b` output guard:

- `0x116c`: `mova r0, #0x3`;
- `0x1172`: `and r16, r2, r0`;
- `0x1178`: `jnz r16, #0x1970`.

This computes `r2 & 3`, rejects a non-4-byte-aligned output pointer by branching to `0x1970`, and lets only an aligned pointer fall through toward the repaired coefficient writeout. The W0 **CBD/NTT coefficient-output helper guard sub-gate is PASS**. The four caller destination offsets remain a separate open proof; exact 128-word pipeline coverage is closed below.

## 2. Instruction-width inventory

| Core | Role | Visible `st.s8` | Visible `st.s16` | Generic/full `st` | Width conclusion |
| --- | --- | ---: | ---: | ---: | --- |
| 0_2 | W0 seed/noise | 65 | 0 | 183 | No halfword store; candidate coefficient writeout is full-word |
| 0_3 | W1 row0_expand | 54 | 0 | 157 | Candidate copy/SampleNTT outputs are full-word |
| 0_4 | W2 row0_accumulate | 47 | 0 | 73 | Candidate copy/accumulation outputs are full-word |
| 0_5 | W3 row1_expand | 55 | 0 | 157 | Candidate copy/SampleNTT outputs are full-word |
| 1_2 | W4 row1_accumulate | 48 | 0 | 73 | Candidate copy/accumulation outputs are full-word |

Counts include stack spills, local cryptographic state, headers, rho, clears, and library code; they are not Class C counts.

## 3. W0 / core 0_2 — seed, CBD3, NTT, four coefficient outputs

### Candidate Class C pair writeout

The strongest evidence in the map is the W0 pipelined pair-output loop:

- setup at `0x16f0` loads `0x80` (128) and sets loop end `0x1790`;
- steady-state body at `0x1764` contains `st r3, [p1, dj0]`;
- the `.L_LEnd18` region at `0x1790` is followed by pipelined completion stores at `0x17b2` (`st r3, [p1, dj0]`) and `0x17b8` (`st r0, [p1, dj1]`).

Every one of these stores is full-word `st`. There is no `st.s8` or `st.s16` from the loop entry at `0x1750` through the body, `.L_LEnd18`, and visible epilogue at `0x17b8`. This directly addresses the old vulnerable high-half loss shape: the W0 terminal pair writeout did not lower into separate high-byte stores.

The new unfiltered window closes the exact pipeline count and tail proof:

- `0x16e0` sets `ls=0x1750`;
- `0x16f0` places old `r0=0x80` (128) while setting `le=0x1790`;
- in the VLIW bundle at `0x16fc`, `mova r0,#0x2` and `add.nc lc,r0,#-0x2` execute with AIE2 old-value semantics, so the LC calculation consumes the old `r0=128` and programs `lc=126`;
- AIE2 ZOL trip-count semantics execute 126 steady-state loop commits at the full-word `st@0x1764`;
- the two valid software-pipeline results drained after `.L_LEnd18` commit with full-word `st@0x17b2` and `st@0x17b8`;
- the preloads/modifier rotation at `0x1702-0x1748`, the body modifier/increment, and the two distinct epilogue modifiers continue the output sequence rather than resetting it.

Thus the schedule commits `126 + 2 = 128` consecutive 32-bit pair words. There is no duplicate, gap, scalar remainder, or sub-word tail. No `st.s8`/`st.s16` occurs in the body or epilogue. The **W0 coefficient writeout width/count/tail sub-gate is PASS**.

The unfiltered call-site window closes all four W0 destinations and ordered short-circuit flow:

- calls to the single helper entry `0x1140` occur at `0xcaa`, `0xcdc`, `0xd1c`, and `0xd5c`;
- helper entry `0x1140` executes `mov r2,p1`, so the adjusted `p1` is exactly the guarded output pointer;
- AIE2 call-delay semantics execute the listed pointer-adjust instructions before control arrives at `0x1140`;
- first call: `0xcb6 mova m0,#0x29`, `0xcba paddb [p1],m0`. Here `0x29` is decimal +41; the live header cursor is already token-base+7 after seven post-increments and the non-incrementing eighth-byte store, so the delay slot produces token+7+41 = token+48;
- second call: baseline `p1` reload at `0xcd4`, then delay-slot `paddb [p1],#560` at `0xcea`;
- third call: baseline reload at `0xd14`, then `padda [p1],#1072` at `0xd2a`;
- fourth call: baseline reload at `0xd54`, then `padda [p1],#1584` at `0xd6a`.

The argument flow therefore invokes the proved aligned 128-word helper exactly on secret `s0/s1/e0/e1` at 48/560/1072/1584.

Short-circuit behavior is also preserved:

- first false result branches at `0xcc0 jz r0,#0xec0` before call two;
- second result is normalized against true at `0xcf0-0xd00`, with mismatch branching at `0xd04` before call three;
- third is normalized similarly at `0xd30-0xd40`, with mismatch branching at `0xd44` before call four;
- fourth result remains live while the local rho/sigma clear loops run; `0xea0 jnz r0,#0x1120` takes the true/success path to common ingress cleanup, while false falls through `0xeb0 j #0xff0` to the complete `BAD_TOKEN` rewrite before common cleanup.

Thus W0 has exactly four ordered coefficient writes, all four required destinations, correct fail-closed short circuit, helper alignment dominance, and exact 128-word full-width body/tail coverage. The **entire W0 Class C compile-only store sub-gate is PASS**.

### Visible alignment evidence

Unfiltered evidence conclusively identifies the helper guard: `0x116c mova r0,#3`, `0x1172 and r16,r2,r0`, `0x1178 jnz r16,#0x1970`. It rejects `r2 & 3 != 0`; aligned fall-through reaches the repaired coefficient path. The helper guard dominates W0's Class C pair-write body and is PASS.

The outer W0 token-base guard, four short-circuit call destinations, and exact pipelined word count are not reconstructable from the filtered map.

### Non-Class-C stores

The many W0 `st.s8` loops before/around the helper are consistent with the V2 allowed source set:

- L: local Keccak/SHAKE absorption/padding, `rho`/`sigma` extraction, and `prf[192]` fills;
- R: the retained 32-byte token `rho` copy;
- H: output header ID/status bytes;
- Z: local/input/token clear loops.

Likely examples include local-state/clear loops around `0x810-0x10a0`, PRF/local loops around `0x11e0-0x14d0`, and clear loops around `0x17e0-0x1960`. The condensed map does not preserve sufficient p-register destination provenance to assign every one conclusively. They remain unclassified pending the requested windows.

**W0 status:** **PASS** for Class C helper guard, four destination offsets, 128-word width/count/tail, and ordered fail-closed call flow. Remaining W0 L/R/H/Z classification/provenance items are tracked separately from the Class C store sub-gate.

## 4. W1 / core 0_3 — row0 expand

### Candidate Class C polynomial/carry copy

The unfiltered W1 window closes destination alignment, helper guards, and exact full-word count/tail:

- call `0xa80 -> 0xc70` executes AIE2 delay slots before helper entry;
- delay-slot `m0=#0x29` plus `paddb [p3],m0` applies +41 to the saved matrix header cursor at matrix+7, producing matrix+48; `p0=p3` passes matrix+48 as helper destination;
- `p1=p2` passes the current source pointer (its secret+48 provenance is the one remaining open item);
- destination guard: `0xc70 mova r0,#3`, `0xc70/0xc7a` mask `p0 & 3`, and the nonzero path returns false at `0xc90`;
- source guard: `0xca0-0xcac` masks `p1 & 3`, with nonzero returning false at `0xcc0`;
- aligned fall-through reaches `0xcd0` and the copy loop;
- old `r5=0x200` (512) at `0xcf8`, with AIE2 old-value bundle semantics at `0xcfe`, programs `lc=511`;
- preload/packing creates the first word before loop entry; the body performs 511 monotonic +4 full-word commits at `0xd38`;
- `.L_LEnd7@0xd70` completes the last pack, and return-delay epilogue `0xd8a` performs the 512th full-word commit;
- success sets `r0=1`; no `st.s8`/`st.s16` exists in the Class C body, ZOL end, or epilogue.

Therefore the helper performs exactly `511 + 1 = 512` consecutive 32-bit commits (2,048 bytes), with no gap, duplicate, or partial tail, to destination matrix+48. The **W1 copy destination/guard/width/count/tail sub-gate is PASS**. The source is passed as `p1=p2`, but neither supplied W1 window defines `p2`; secret+48 is not yet independently proved.

The added `0x0800-0x0a80` window clarifies control-flow classes:

- `0x800-0x880` is the common consumed-input byte-zeroization loop, followed by register restore and return at `0x8c0`; it is Class Z, not itself the matrix `BAD_TOKEN`/`LIMIT_EXCEEDED` rewrite;
- `0x8d0-0x950` is an output clear/setup loop and `0x960-0x9e2` writes header bytes (Class Z/H by shape); exact output-base/status register provenance still comes from the missing entry setup;
- `0xa10-0xa70` is the retained 32-byte rho byte-copy ZOL (Class R by source/shape), with byte load `[p0,dj0]` and byte store `[p1,dj0]`;
- copy false at `0xaa0` branches to `0xb40`; the already supplied next portion shows `0xb40-0xc64` clearing/writing a matrix error record and then jumping to `0x800` for common input zeroization/return. Structurally this is fail closed and prevents both SampleNTT calls. The exact matrix base, request ID, and error-status register values still require the entry/prologue provenance window.

The entry and mid windows together close W1 copy-source provenance and worker alignment:

- function entry is `dr2d_kpke_keygen_row0_expand@0x1a0` with secret input in `p0`;
- `0x1c8` copies the secret base to `p2`;
- three post-increment header loads at `0x1d6/0x1de/0x1e8`, followed by a non-incrementing fourth load at `0x1f4`, leave `p2=secret+3`;
- `0x3c0 mova m0,#0x2d` and `0x3ca paddb [p2],m0`: AIE2 B-address modifier encoding `0x2d` is a linear `+45` byte update, so p2 becomes `secret+3+45 = secret+48`;
- the subsequent canonical checks use aliases/copies and do not modify p2; therefore later `0xa96 p1=p2` passes exactly secret+48 to `copy_words`;
- worker output alignment: `0x59e r3=3, r4=p1`, `0x5a4 r4 &= 3`, with nonzero branching at `0x5a8` to `0x5d0`;
- worker input alignment: `0x5b8 r4=p0`, `0x5bc r3=r4&3`, with zero branching at `0x5c0` to aligned normal path `0x8d0`; nonzero falls through to `0x5d0`.

Thus both token bases must be 4-byte aligned before normal output setup, rho copy, Class C copy, or SampleNTT. The worker guard dominates every W1 Class C path. Combined with the already-proved helper guards and destination+48, the W1 bulk copy now has complete source secret+48 and destination matrix+48 provenance. The **W1 bulk-copy source/destination/alignment/width/count/tail sub-gate is PASS**.

The earlier failed `-S` attempt remains no evidence. The raw `0x5d0-0x6f0` window closes the guard's fail-closed target:

- entry provenance set `r22=0xc30` and `r16=0`; `0xc30` is exactly 3,120, the complete matrix-token size;
- `0x5d0` programs the zeroization ZOL from `ls=0x5f0` through `le=0x650` with LC derived from `r22`; the body writes zero with `st.s8 r16,[p1,dj0]` across the complete output record;
- after the full clear, bytes 0..3 are written sequentially from `r21,r20,r19,r18`, the original request-ID bytes loaded from the input header;
- byte 4 is `r1=3`, the little-endian low byte of `BAD_TOKEN`; bytes 5..7 are `r16=0`, including the last header byte in the jump delay slot;
- every reserved and payload byte remains zero from the preceding complete clear;
- control jumps to `0x800`, the already-proved common consumed-input Class Z clear/return, without reaching rho, copy_words, or SampleNTT.

This exactly implements `write_header(matrix,3120,id,BAD_TOKEN,16)`. The **W1 worker-alignment fail-closed sub-gate is PASS**. Together with source/destination provenance and helper mechanics, W1's bulk-copy path is fully closed.

### Candidate Class C SampleNTT commits

The full helper and earlier caller window close both SampleNTT destinations and all commit/tail semantics.

Caller arguments execute in AIE2 call delay slots before helper entry:

- first call `0xabe -> 0xd90`: reload matrix base into p1; `p6=p1`, then `p6+=16` supplies rho at matrix+16; encoded modifier `m0=0x830` advances output p1 by 2096, so helper output is matrix A00; p0=p6 supplies the same rho;
- second call `0xb08 -> 0xd90`: matrix base is reloaded, p0 reuses p6=matrix+16, and encoded `m0=0xa30` advances output p1 by 2608, so helper output is matrix A01.

Helper proof:

- entry copies output p1 to the guarded pointer; `0xdb0-0xdbc` masks low two bits and misaligned output exits at `0x1270`; aligned fall-through sets p7=p1 before any commit;
- r16 is accepted count 0, r19 parity mask 1, r21 pending, r22=q=3329, r18=256, and r8=0x1fc;
- both candidate paths reject candidates >=q and enforce accepted<256;
- accepted even index (`r16&1==0`) only saves candidate in r21;
- accepted odd index packs `pending | candidate<<16` and performs one full-word store: `st@0x10cc` for one candidate path or `st@0x115c` for the other;
- store offset `(r16<<1)&0x1fc` maps odd accepted counts 1..255 to word byte offsets 0..508; r16 increments only after acceptance;
- completion requires r16==256, hence exactly 128 complete pair commits. There is no odd pending success state, scalar remainder, or partial-width tail;
- no `st.s8`/`st.s16` exists on either Class C commit path;
- `0x11f0-0x1250` clears the complete 200-byte local state buffer (Class Z/L cleanup) after pending is discarded;
- first false return branches to `0xb40` LIMIT_EXCEEDED rewrite and skips call two; after call two, true branches at `0xb20` to common cleanup `0x800`, while false falls through to `0xb40`.

The **W1 SampleNTT A00/A01 destination/guard/width/count/tail/cleanup/failure sub-gate is PASS**.

### Guard evidence

The copy and worker guards were proved earlier. The SampleNTT output guard at `0xdb0-0xdbc` is now proved to dominate both full-word commit sites for both A00/A01 calls; misalignment exits at `0x1270` without a Class C write.
### Likely allowed byte-store classes

- H/Z: early clear/header paths and epilogues (`0x2d0-0x3b4`, `0x600-0x7f4`, `0x900-0x9e2`, `0xb90-0xc64`);
- R: the retained rho-copy loop is strongly consistent with `0xa30-.L_LEnd2@0xa70`;
- L/Z inside SampleNTT: `0xe30-0xf96` and local clear at `0x1200-.L_LEnd8@0x1250`.

These classifications are plausible from source order and loop shape but not proved by destination addresses in the condensed map.

**W1 status:** **PASS for the complete Class C compile-only store path**: bulk copy secret+48 to matrix+48, worker/helper guards, exact 512-word copy, A00/A01 offsets 2096/2608, 128 pair commits each, no partial tails, local cleanup, BAD_TOKEN misalignment rewrite, and LIMIT_EXCEEDED SampleNTT failure routing.

## 5. W2 / core 0_4 — row0 accumulate

### Candidate Class C copy loop

The generic copy helper ends at `.L_LEnd7` `0xf40`, whose bundle contains `st r4, [p0, dj0]`. It is full-word and contains no sub-word store. V2 requires three invocations/spans (256 words at state 48, 128 at 1072, 128 at 1584). The map gives one shared/inlined loop body but omits the three call setups, destination bases, and trip counts, so all three required regions cannot be independently checked.

### Class C accumulation output — helper body PASS

The unfiltered helper resolves every previously ambiguous store and pointer role:

- incoming a pointer p0 is saved at stack -68; b pointer p1 at -64; incoming accumulator p2 is copied to p6 at `0xfc4` and remains the Class C base;
- p1 is repurposed to a local stack region at stack-128, and p7 to a separate local stack region at stack-160;
- stores `0x129a`, `0x12a0`, `0x12a6`, and `0x12aa` use p0 after `0x1288 p0=p1`, so they are local four-lane reduction/staging stores, not FIFO Class C writes;
- `0x1340 st r3,[p7,dj0]` and pipelined completion `0x138a st r0,[p7,dj0]` also target the p7 local reduction array, not the accumulator;
- after all four reduced lanes are available, `0x1382 p0=p7` reads the local lanes at `0x1390-0x13a8` and packs two pair words;
- `0x13b2 p0=p6` restores the accumulator output; `paddb [p0],m0` selects the current 8-byte group;
- the only final Class C stores are `0x13ba st r0,[p0,#0]` and `0x13da st r1,[p0,#4]`. Both are full 32-bit stores. At `0x13ba`, AIE2 VLIW old-value semantics make the store consume the already packed old r0 while the parallel `mova r0,#0x200` prepares the later loop-bound comparison; the data store is not the constant 0x200. The second store is in the loop branch/delay schedule and executes for every group, including the final group.

Count and sequence proof:

- r9 starts at 0 and is the accumulator byte-group offset;
- each iteration writes exactly offsets r9+0 and r9+4, then `0x13ba` advances r9 by 8;
- `0x13c4` compares the updated r9 to 0x200 (512) and `0x13c8` loops while unequal;
- therefore group bases are 0,8,...,504: exactly 64 consecutive groups, two words each, covering all 512 accumulator bytes once with no duplicate, gap, or partial tail;
- all old accumulator inputs and all four reduced lane results are loaded/computed and staged before `0x13b2-0x13da` performs either final output store;
- no `st.s8`/`st.s16` occurs anywhere in the final Class C body, loop branch, delay slot, or tail.

The previously proved `0xf94/0xf9a/0xfa2` alignment guard dominates this helper body. The **W2 add_product_ntt helper guard/store-classification/64-group width-count-tail sub-gate is PASS**.

The W2 main/caller window closes relative argument setup and ordered routing:

### Retained rho

`0xb60-0xbc0` is a byte load `[p0,dj0]` plus byte store `[p1,dj0]` ZOL with no coefficient write. Its source shape is the retained rho Class R copy. The window begins after r0/r2 and p0/p1 were initialized, so exact offsets 16..47 and 32-byte count still require prior normal-path setup.

### Three copy_words calls

- `0xbd0 -> 0xe40`: delay slots pass p1=p7 as source, advance live destination p2 by `m0=0x29` (+41 from its header cursor), and pass p0=p2. This is structurally the state secret/s1 copy; absolute matrix/state bases and live first length are not defined in this window.
- `0xc1a -> 0xe40`: destination base is reloaded then advanced by 1072 at `0xc24`; source comes from stack -84; delay `r1=0x200` gives exactly 512 bytes = 128 words. This is the t0 seed copy.
- `0xc5c -> 0xe40`: destination base is reloaded then advanced by 1584 at `0xc6a`; source comes from stack -80; delay `r1=0x200` gives 512 bytes = 128 words. This is the e1 carry copy.

The helper at `0xe40-0xf5c` masks both destination and source low bits before its only store loop. Its Class C store is full `st@0xf40`; there is no `st.s8`/`st.s16` body or tail. Length r1 is transformed into an exact word loop. Calls two and three therefore have proved 128-word full-width counts. The first call's expected r1=0x400 (1,024 bytes/256 words) remains live-in and must be proved by the preceding setup.

### Two add_product_ntt calls

- `0xc9e -> 0xf60`: p0 from stack -76, p1=p7 in the delay slot, p2 from stack -72;
- `0xcde -> 0xf60`: p0 from stack -96, p1=p6 in the delay slot, p2 again stack -72.

This proves both calls share one accumulator alias and use distinct A/input aliases. Against V2 source order these are A00·secret and A01·s1. Absolute identities (A00=matrix+2096, A01=matrix+2608, p7=matrix+48, p6=matrix+560, accumulator=state+1072) require the stack/register definitions from the preceding normal-path setup.

### Ordered short-circuit and failure structure

- copy one false: `0xbf0 jz r0,#0xd10`;
- copy two/three and add one false are normalized against true and branch at `0xc42/0xc84/0xcc4` to `0xd10`;
- add two true branches at `0xd00` to success/common cleanup `0x950`; false falls through `0xd10`;
- `0xd10-0xda0` clears an output record and `0xdc0-0xe34` writes ID/status/header bytes before jumping to `0x950`, structurally the complete BAD_TOKEN rewrite. Exact token size/status register provenance is prior to this window.

Thus call order and prevention of later calls on failure PASS structurally. The normal-output window closes additional relative provenance:

### Success/common cleanup at 0x950

`0x950-0x9d0` is a volatile byte-clear loop over p0, followed by register restore and return at `0xa10`. This is the common consumed-matrix Class Z cleanup/return reached after successful add two (`0xd00 -> 0x950`) and after error-record completion. The exact input matrix base and 3,120-byte count r17 are set earlier.

### Normal state output and header cursor

- normal path `0xa20-0xaa0` clears the full output through p1 using loop count r23; absolute state base and 2,096-byte r23 value are earlier;
- `0xab0 p2=p1` snapshots the state output base for header emission;
- before the header stores, p5/p4/p3 are saved at stack -76/-80/-84. These are exactly the aliases later used by add/copy calls, but their absolute matrix offsets were established earlier;
- header writes at `0xac2/0xad2/0xae2/0xaf2/0xb02/0xb12/0xb22` post-increment seven times; `0xb32` writes the eighth byte without increment. They preserve ID in r21-r18 and write zero OK status/reserved bytes, leaving p2 exactly state+7;
- first-copy delay `m0=0x29` (+41) later advances this live p2 cursor to state+48 exactly.

This proves the first copy's **relative destination** state+48 and confirms successful completion returns through input cleanup, but not yet the absolute p1 state base.

### Retransferred entry/mid evidence — all remaining W2 provenance closed

The readable 534-line entry/mid window establishes every outstanding value:

**Function bases, IDs, sizes, and constants**

- `dr2d_kpke_keygen_row0_accumulate@0x1a0` receives matrix input in p0 and state output in p1;
- `0x1e6 p6=p0`; header ID bytes are loaded through p6 into r21/r20/r19/r18;
- r23=0x830 at `0x22c` = 2,096-byte state token; r17=0xc30 at `0x240` = 3,120-byte matrix token;
- r22=3 at `0x236` is BAD_TOKEN; r16=0; r1=0x400 at `0x256` is the first copy's 1,024-byte length; r2=0x20 is rho count 32.

**Absolute matrix aliases**

Header post-increments leave p6=matrix+3. Then:

- `0x3d0-0x3da`: p7=p6 plus `0x2d` (+45) -> matrix+48;
- `0x456-0x45a`: p6 plus `0x22d` (+557) -> matrix+560;
- `0x4d6-0x4da`: p3=p0+1072 -> stack -84 later;
- `0x556-0x55a`: p4=p0+1584 -> stack -80 later;
- `0x5d0-0x5da`: p5=p0+2096 -> stack -76 later;
- `0x65c-0x66a`: p2=p0+2608 -> stack -96.

The caller window saves/reloads these exact aliases. For copy two, p0=state base then +1072 and is saved at stack -72, proving the shared accumulator state+1072. Thus:

- copy one: state+48 <- matrix+48, r1=0x400 = 256 words;
- copy two: state+1072 <- matrix+1072, r1=0x200 = 128 words;
- copy three: state+1584 <- matrix+1584, r1=0x200 = 128 words;
- add one: matrix+2096 (A00), matrix+48 (secret), state+1072;
- add two: matrix+2608 (A01), matrix+560 (s1), state+1072.

Combined with the copy/add helper audits, every W2 Class C destination, span, full-word count, and arithmetic output is exact.

**Rho Class R**

p0/p1 remain matrix/state bases on the normal path. r0 remains 0x10 from entry and r2=0x20. At `0xb60`, AIE2 old-value semantics make dj0 consume old r0 before increment, producing offsets 16 through 47 for exactly 32 LC iterations. `0xb70` byte-loads matrix and `0xb80` byte-stores state. This is exactly matrix rho -> state rho and is Class R.

**Worker guard and BAD_TOKEN**

- output guard `0x6ee-0x6f8`: state p1&3, nonzero -> `0x720`;
- input guard `0x708-0x710`: matrix p0&3, zero -> normal `0xa20`, nonzero falls to `0x720`;
- both dominate all rho/copy/add work;
- `0x720-0x7a0` clears exactly r23=0x830 state bytes;
- `0x7c0-0x834` writes original ID r21..r18, status r22=3, and three zero bytes, last in the jump delay slot; payload/reserved remain zero;
- jump reaches `0x950`, where r17=0xc30 clears the complete consumed matrix and returns.

This exactly proves the worker misalignment BAD_TOKEN path. Invalid-header/canonical paths at `0x840` use the same 2,096-byte clear/header structure and cannot enter normal work.

The previously missing attachment was correctly treated as no evidence; this retransferred file supersedes that availability gap.

### Guard evidence

The add-product helper guard at `0xf94/0xf9a/0xfa2` is proved and dominates the now-identified final Class C stores at `0x13ba/0x13da`. The worker-level guard, all three copy call setups, two add-product caller argument sets, and main failure routing remain unresolved.
### Likely allowed byte-store classes

- H/Z: early fail/status output paths and final input clear;
- R: the 32-byte rho copy is strongly consistent with the `0xb80-.L_LEnd2@0xbc0` byte loop;
- Z: `0xd60-.L_LEnd1@0xda0` is consistent with a full-token clear.

All visible byte stores before the full-word helpers are compatible with H/R/Z source loops, but destination proof is absent.

**W2 status:** **PASS for the complete Class C compile-only path and associated R/H/Z routing**: exact 256/128/128-word copies, A00/A01 product calls into state+1072, 64×2 full-word groups per product, worker/helper guards, rho Class R offsets 16..47, complete BAD_TOKEN record, canonical failure routing, and full matrix cleanup.

## 6. W3 / core 0_5 — row1 expand

The unfiltered W3 SampleNTT helper closes its internal producer semantics:

- output p1 is masked with 3 at `0xdb0-0xdbc`; misalignment exits at `0x1290`, and aligned fall-through establishes p7 as the only Class C output pointer;
- r16=0 accepted count, r18=256 limit, r19=1 parity, r21 pending, r22=3329, r7=16 shift, and r8=0x1fc offset mask exactly mirror W1;
- candidate paths reject >=q and prevent acceptance beyond 256;
- even accepted indices save pending only; odd accepted indices pack pending low plus candidate<<16 and perform one full-word commit;
- the only Class C commit sites are full `st@0x10ec` and `st@0x117c`;
- completion r16==256 proves exactly 128 pair words, with no odd pending success, scalar remainder, or sub-word tail;
- local 200-byte state clear runs at `0x1210-0x1270` and is Class Z/L cleanup;
- the additional byte update at `0xf82`, offset `0x21`, targets local SHAKE/domain state, not p7 output, and is Class L rather than Class C.

The **W3 SampleNTT helper guard/width/count/tail/local-classification sub-gate is PASS**. The caller/copy window closes the remaining caller and helper mechanics:

### A10/A11 callers and ordered failure routing

- first SampleNTT call is `0xabe -> 0xd90`; delay slots preserve matrix base in p6, advance p6 by 16 for rho, apply encoded output modifier `0x830` (=2096) to p1, and pass p0=p6. Combined with the proved helper, this targets matrix A10 and uses matrix rho;
- first return is normalized against true at `0xae0-0xaec`; mismatch branches at `0xaf0` to `0xb40`, skipping call two;
- second call is `0xb08 -> 0xd90`; delay slot applies `0xa30` (=2608) to the reloaded matrix base and reuses p0=p6=matrix+16, targeting A11;
- second true return branches at `0xb20` to common cleanup `0x800`; false falls through to `0xb40` LIMIT_EXCEEDED rewrite.

Thus A10/A11 destination offsets and ordered failure flow PASS, subject only to proving the live matrix-base alias from the earlier worker entry.

### W3 copy helper mechanics

- copy call `0xa80 -> 0xc70` applies `m0=0x29` (+41) to the live p3 header cursor; if p3 is matrix+7 as in W1, the endpoint is matrix+48. It passes p0=p3 as destination and p1=p2 as carried-state source; the current window itself does not define that p3 cursor;
- destination and source low-bit guards at `0xc70-0xcc0` return false before any store on misalignment;
- aligned setup loads old r5=0x200 and programs lc=511;
- 511 monotonic +4 full-word body commits occur at `0xd38`, followed by the 512th full-word pipeline completion at `0xd8a` after `.L_LEnd7@0xd70`;
- no `st.s8`/`st.s16` occurs in the Class C copy body/end/epilogue.

The copy guard/width/count/tail and encoded destination +48 mechanics PASS. This window begins after p2 and p3 were defined, so it does **not** prove p2=state+48 or p3=matrix base. It also does not show the worker-level input/output alignment guard or exact BAD_TOKEN branch target values.

The W3 entry/mid window now closes carried-state source provenance and worker guard dominance:

- function entry `dr2d_kpke_keygen_row1_expand@0x1a0` receives carried state in p0 and matrix output in p1;
- `0x1c8` copies state base to p2; three post-increment header loads at `0x1d6/0x1de/0x1e8` and a non-incrementing fourth at `0x1f4` leave p2=state+3;
- `0x3c0 m0=0x2d` and `0x3ca paddb [p2],m0` apply +45, yielding p2=state+48; subsequent canonical checks use p2 read-only or use temporary p3 aliases and do not change p2;
- therefore `0xa96 p1=p2` passes exactly state+48 to copy_words;
- output guard at `0x59e-0x5a8` computes matrix p1&3 and branches nonzero to `0x5d0`;
- input guard at `0x5b8-0x5c0` computes state p0&3; zero branches to aligned normal path `0x8d0`, while nonzero falls through to `0x5d0`;
- these worker checks dominate rho, copy, and both SampleNTT calls.

The **W3 carried-state+48 source and worker-alignment dominance sub-gate is PASS**. The final W3 path window closes every remaining edge:

### Misalignment BAD_TOKEN and common cleanup

- entry provenance has r22=0xc30 (3,120) and r16=0; `0x5d0-0x650` clears exactly the complete matrix token through `st.s8 r16,[p1,dj0]`;
- header bytes at `0x670-0x6e4` write original request ID from r21/r20/r19/r18, status low byte r1=3, then three zero bytes, with the last zero in the jump delay slot;
- all reserved/payload bytes remain zero from the full clear;
- `0x6de` jumps to `0x800`; `0x800-0x880` clears the complete consumed 2,096-byte state input (r17=0x830) and returns. No Class C work is reached.

Thus `0x5d0` exactly implements the matrix BAD_TOKEN record and the worker misalignment fail-closed path.

### Aligned output initialization, header cursor, and rho

- aligned path `0x8d0-0x950` clears the complete 3,120-byte matrix output;
- `0x960` sets p3=p1 at matrix base; header stores at `0x970/0x982/0x992/0x9a2/0x9b2/0x9c2/0x9d2` post-increment seven times, while `0x9e2` writes the eighth byte without increment. The ID is preserved and status/reserved bytes are zero, leaving p3 exactly matrix+7;
- p3 is unchanged through the rho ZOL;
- the retained rho loop `0xa10-0xa70` performs byte load from carried state and byte store to matrix with the shared offset sequence covering token offsets 16..47 for exactly 32 bytes. It is Class R, not Class C;
- later call delay `m0=0x29` is decimal +41, so p3 matrix+7 becomes matrix+48 exactly before copy_words.

Combined with state+48 source, helper guards, and 512-word mechanics, the W3 bulk copy is exactly state+48 -> matrix+48. A10/A11, SampleNTT, failure routing, local cleanup, and all relevant byte-store classes were already proved.

**W3 status:** **PASS for the complete Class C compile-only store path** and associated R/H/Z routing: state+48 to matrix+48 exact 512-word copy, A10/A11 at 2096/2608 with 128 full-word commits each, worker/helper guards, no sub-word tails, complete BAD_TOKEN and LIMIT_EXCEEDED paths, retained rho Class R, and input/local Class Z cleanup.

## 7. W4 / core 1_2 — row1 accumulate

The complete unfiltered W4 function independently proves the row-1 accumulator; no conclusion below relies only on W2 symmetry.

### Bases, sizes, aliases, and guards

- function entry receives matrix input p0 and final output p1;
- ID bytes load into r21/r20/r19/r18;
- r23=0x840 at `0x22c` = 2,112-byte final token; r17=0xc30 at `0x240` = 3,120-byte matrix token; r22=3 is BAD_TOKEN; r16=0; r1=0x400 first-copy length;
- header cursor p6 begins matrix+3; p7=p6+45 = matrix+48; p6+=557 = matrix+560;
- p3=matrix+1072, p4=matrix+1584, p5=matrix+2096, stack -96=matrix+2608;
- output guard `0x6ee-0x6f8` checks final p1&3; input guard `0x708-0x710` checks matrix p0&3. Either misalignment reaches `0x720`; aligned input reaches normal `0xa20`. Guards dominate all W4 Class C writes.

### Complete BAD_TOKEN and cleanup

`0x720-0x7a0` clears exactly r23=0x840 final bytes. Header stores `0x7c0-0x834` write original ID, r22=3 status, and zero reserved bytes; payload stays zero. The path jumps to `0x950`, where r17=0xc30 clears the complete consumed matrix and returns. Invalid/canonical failures at `0x840` use the same full final-record clear/header structure. This is complete fail-closed H/Z behavior.

### Normal final output, rho, and the `0xbe2` specialization

- `0xa20-0xaa0` clears all 2,112 final bytes; `0xab0` snapshots final base in p2 and writes ID plus zero OK status/reserved bytes through `0xb24`;
- rho setup uses source matrix offset 16 and destination final offset 32. The software-pipelined loop produces 31 body writes at `0xb60` plus the final byte-store epilogue at `0xbe2`, for exactly 32 bytes: matrix 16..47 -> final 32..63;
- `st.s8@0xbe2` is therefore the final Class R rho epilogue store, not a coefficient/carry write and not a defect;
- before copy one, p2 is the final header cursor at final+7; modifier `0x39` is +57, producing final+64 exactly.

### Exact copies and caller aliases

The guarded full-word helper at `0xe40-0xf5c` is directly present in W4 and has no Class C sub-word body/tail.

- copy one `0xbe8`: final+64 <- matrix+48, r1=0x400 = 1,024 bytes = 256 words;
- copy two `0xc1c`: final+1088 <- matrix+1072, r1=0x200 = 512 bytes = 128 words;
- copy three `0xc5a`: final+1600 <- matrix+1584, r1=0x200 = 128 words; resulting final+1600 is saved as shared accumulator.

All three calls short-circuit false to `0xd10`, which clears/writes a complete final BAD_TOKEN record before matrix cleanup.

### Two row-1 products and final accumulator

- add one `0xc9e`: matrix A10 at +2096, secret at +48, accumulator final+1600;
- add two `0xcde`: matrix A11 at +2608, s1 at +560, same final+1600 accumulator;
- failures short-circuit to `0xd10`; final success branches at `0xd00` to matrix cleanup.

The W4 add helper independently contains the same directly observed structure:

- output guard `0xf94/0xf9a/0xfa2` dominates the body;
- stores `0x129a/0x12a0/0x12a6/0x12aa` use local p1 stack storage;
- stores `0x1340/0x138a` use local p7 reduction storage;
- only final Class C stores are full-word `st@0x13ba` and `st@0x13da` after p0=p6 accumulator;
- r9 advances 8 and compares to 0x200, yielding group bases 0..504: exactly 64 groups × two words = all 512 final-t1 bytes, no duplicate/gap/partial tail;
- at `0x13ba`, old-value semantics store the packed old r0 while parallel `mova r0,#0x200` prepares the bound comparison; `0x13da` is the second full-word delay-slot store for every group;
- no `st.s8`/`st.s16` occurs in a Class C body, ZOL end, epilogue, or tail.

**W4 status:** **PASS for the complete Class C compile-only path and associated R/H/Z routing.** Final s0/s1/t0/t1 copies, A10/A11 products, final+1600 accumulation, guards, exact tails, rho specialization including `0xbe2`, BAD_TOKEN, and matrix cleanup are all proved.

### All-five repaired-worker store verdict

| Core | Worker | Store-map result |
| --- | --- | --- |
| 0_2 | W0 seed/noise | PASS |
| 0_3 | W1 row0_expand | PASS |
| 0_4 | W2 row0_accumulate | PASS |
| 0_5 | W3 row1_expand | PASS |
| 1_2 | W4 row1_accumulate | PASS |

Across all five: every Class C write is full-word `st`; every required span/tail is complete; no Class C `st.s8`/`st.s16` exists; all visible sub-word stores relevant to repaired paths are classified L/R/H/Z. The **destination-aware Phoenix store gate is PASS**.

## 8. Provenance/freshness audit and single next command

### Accepted V2 source identity — PASS

The manifest hashes match the exact V2 apply-check/working-tree identities independently recorded earlier:

| Source | Accepted/manifest SHA-256 |
| --- | --- |
| `internal.hpp` | `16d61e6ada4d7de384b3981cc76d3de8319ce2bec999727d4847567e7e1f3519` |
| W0 seed | `2f94e2995706ac5636f35c66167e5dd8f54ac54b618c200bf4ee45b8b754ceaf` |
| W1 row0_expand | `d95106c0f01a1a99aee21cef3fab704b1e57bd6d1d4e066f7e421f0dd0b53986` |
| W2 row0_accumulate | `a577360c6e24296576daedfdc537d04765aaebfdc74eeadd34358437986e0622` |
| W3 row1_expand | `c893d0158f85a00c6dfd6a7f20c6aa2c5259d397ac64c32d4c3f9e8cb82c13c8` |
| W4 row1_accumulate | `235c69d008e7db656c26053a404980b7de139156c8c4671ac94a04c7fb1c9806` |
| serializer | `23f691bc40410f7bdf9573a14bc01c590a3e9d2a36b07e807e415b033d49780c` |
| production graph | `e17e17b8481bc1fa8492a7e2bc9184fbae095b55c5e175b015aa19a2bc999694` |
| ABI | `a6f44c68787905f6b4819598baacac59bf5bcc4a3125c8151b7863345e9ff4f4` |
| canonical runner | `742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad` |

No rejected-V1 or unrelated source identity is present.

### Freshness/no-stale-object chain — PASS

- cache key/path: `04f147d54cb01d160974a6e6`;
- accepted repaired sources: approximately `00:35:43Z`;
- worker objects: `00:36:47Z` through `00:36:54Z`, all later than the sources;
- all six core ELFs: `00:36:55.410Z`, later than every worker object;
- final.xclbin: `00:36:55.504Z`, later than all six ELFs.

This is a strictly monotonic source -> object -> six-ELF -> xclbin chain in one cache key. Combined with exact accepted source hashes and distinct recorded object/ELF/xclbin hashes, there is no stale-object indication. The artifact freshness/no-stale gate is PASS.

Artifact identities are pinned by the manifest:

- core 0_2 W0 ELF: `042D0CAD...`;
- core 0_3 W1 ELF: `212944A6...`;
- core 0_4 W2 ELF: `DA1A7BAC...`;
- core 0_5 W3 ELF: `E1B4DC3A...`;
- core 1_2 W4 ELF: `F9FC6A57...`;
- core 1_3 serializer ELF: `FECC3F0A...`;
- final.xclbin: `99F74EA2...`.

The five repaired mappings are independently corroborated by the audited function symbols/store maps. Core 1_3 is the remaining sixth worker in the unchanged six-worker graph and is mapped to the serializer; its source hash is exactly the physically validated unchanged serializer hash. The serializer source/core provenance gate is PASS.

### Toolchain identity — PASS for pinned workaround context

The manifest records LLVM/llvm-objdump 21.0.0 with assertions, matching the pinned vulnerable AIE2 toolchain family for which the source workaround and destination-aware ELF gate were required. The exact store audit above is therefore tied to the intended compiler context and cache artifact.

### Endianness gate — PASS

The endianness manifest reads the same six exact core ELFs from the pinned cache. Every header reports:

- `Format: elf32-aie`;
- `Arch: aie2`;
- `AddressSize: 32bit`;
- `Ident.DataEncoding: LittleEndian (0x1)`;
- `Machine: EM_AIE`.

All production pair-word layouts therefore use the required little-endian byte order. The separate endianness-proof alternative in the physical gate is satisfied for all six cores.

### Generated topology/residency gate — PASS

The generated logical and placed MLIR close this gate:

- exactly six worker cores are present and placed at 0_2, 0_3, 0_4, 0_5, 1_2, and 1_3, with the expected worker object linked to each;
- exactly eight object FIFOs exist: two ingress (`dr2d_d`, 32 bytes; `dr2d_descriptor`, 16 bytes), five private (`secret_token`, 2096; `row0_matrix`, 3120; `row_state`, 2096; `row1_matrix`, 3120; `final_token`, 2112), and one terminal result FIFO (1588);
- all FIFOs are depth two and the placed MLIR contains both physical buffers;
- the only shim data flows are D and descriptor into tile 0_2 and result out of tile 1_3; the fourth explicit flow is the private row1-matrix tile-to-tile route from 0_5 to 1_2, not a shim/host route;
- runtime data movement is exactly two MM2S inputs of 32 and 16 bytes and one token-issuing S2MM result of 1588 bytes, followed by `dma_await_task` on the result;
- no private FIFO has a shim allocation or runtime DMA task.

The `memory-connection: HOST` entries in `kernels_main.json` and the generic HOST DRAM entry in `memTopology_main.json` describe command BO connectivity. They do not add data movement and cannot override the concrete three-task runtime sequence and three shim allocations. They are therefore not evidence of private-token host transfers.

The placed double buffers are within their declared 16-KiB banks and do not overlap one another. The closest same-bank boundaries remain disjoint:

- tile 0_2 bank 0: secret `[0x1000,0x1830)`, descriptor `[0x1840,0x1850)`; bank 1 repeats at `[0x4000,0x4830)` and `[0x4840,0x4850)`; bank 2 D `[0x8000,0x8020)` is immediately followed by the 12-byte core bookkeeping buffer `[0x8020,0x802c)`;
- tile 0_3: row0 matrix `[0x0800,0x1430)` / `[0x4000,0x4c30)`, with bookkeeping at `[0x8000,0x8008)`;
- tile 0_4: row state `[0x0800,0x1030)` / `[0x4000,0x4830)`, with bookkeeping at `[0x8000,0x8008)`;
- tile 0_5: row1 producer matrix `[0x0800,0x1430)` / `[0x4000,0x4c30)`, with bookkeeping at `[0x8000,0x8008)`;
- tile 1_2 bank 0: row1 consumer matrix `[0x0800,0x1430)`, bookkeeping `[0x1440,0x1448)`; bank 1 matrix `[0x4000,0x4c30)`; final-token buffers `[0x8000,0x8840)` and `[0xc000,0xc840)`;
- tile 1_3: result `[0x0800,0x0e34)` / `[0x4000,0x4634)`, with bookkeeping at `[0x8000,0x8008)`.

Thus generated graph topology, private residency, FIFO lengths/depths, buffer placement, cross-column routing, and host transfer cardinality all PASS.

### Program/data/stack memory gate — PASS

Every linker script declares program memory `[0x00000,0x20000)`. Each ELF has exactly one RX `PT_LOAD` at address zero whose file size and memory size equal `.text`. All six fit with large margin:

| Core | Worker | RX `.text` / `PT_LOAD` | Program end | Margin to `0x20000` |
|---|---|---:|---:|---:|
| 0_2 | W0 seed/noise | `0x2450` | `0x2450` | `0x1dbb0` |
| 0_3 | W1 row0 expand | `0x1b80` | `0x1b80` | `0x1e480` |
| 0_4 | W2 row0 accumulate | `0x1510` | `0x1510` | `0x1eaf0` |
| 0_5 | W3 row1 expand | `0x1ba0` | `0x1ba0` | `0x1e460` |
| 1_2 | W4 row1 accumulate | `0x1510` | `0x1510` | `0x1eaf0` |
| 1_3 | serializer | `0x1370` | `0x1370` | `0x1ec90` |

The linker scripts, placed MLIR, ELF sections, and load segments reconcile per core as follows:

- **0_2 / W0:** stack is actually reserved as `[0x70000,0x71000)`, exactly `0x1000`; the first local secret buffer begins at the exact non-overlapping boundary `0x71000`. Local D buffer 1 ends at `0x7c020`. The linker data region is `[0x7c020,0x80000)`, and the sole RO data load is exactly `.data = [0x7c020,0x7c120)`, wholly inside that region and immediately after, not over, D. RX and RO `PT_LOAD` entries exactly match `.text` and `.data`.
- **0_3 / W1:** stack is `[0x70000,0x70800)`, exactly `0x0800`; local row0-matrix buffer 0 begins at `0x70800`. Bookkeeping ends at `0x78008`, which is the exact start of data region `[0x78008,0x80000)`. The ELF contains no allocatable `.data` and no data `PT_LOAD`; only the bounded RX load exists.
- **0_4 / W2:** stack is `[0x70000,0x70800)`, exactly `0x0800`; local row-state buffer 0 begins at `0x70800`. Bookkeeping is `[0x78000,0x78008)`. The RO `.data` load is `[0x78008,0x78108)`, exactly at the start of data region `[0x78008,0x80000)`. RX and RO loads exactly match their sections.
- **0_5 / W3:** stack is `[0x70000,0x70800)`, exactly `0x0800`; local row1-matrix buffer 0 begins at `0x70800`. Bookkeeping ends at the exact data-region start `0x78008`; there is no allocatable `.data` and no data `PT_LOAD`.
- **1_2 / W4:** stack is `[0x70000,0x70800)`, exactly `0x0800`; local row1-consumer matrix begins at `0x70800`, and bookkeeping `[0x71440,0x71448)` follows the matrix end `0x71430` with a 16-byte gap. Final-token buffer 0 is `[0x78000,0x78840)`. Data region begins at that exact end and is `[0x78840,0x7c000)`; RO `.data` is `[0x78840,0x78940)`, wholly inside. Final-token buffer 1 starts at the exact region end `0x7c000` in the adjacent addressed bank, so it does not overlap `.data`. RX and RO loads match their sections.
- **1_3 / serializer:** stack is `[0x70000,0x70800)`, exactly `0x0800`; local result buffer 0 begins at `0x70800`. Bookkeeping ends at data-region start `0x78008`; there is no allocatable `.data` and no data `PT_LOAD`.

The zero-size RW `PT_GNU_STACK` entry is metadata, not the AIE local-stack allocation. The actual reservations are the explicit linker location-counter ranges above, and their boundaries agree with the placed buffers and MLIR `stack_size` declarations.

There are no additional allocatable sections or load segments. `.comment`, `.symtab`, `.shstrtab`, and `.strtab` are non-allocatable file metadata; `.bss` and `.stack_sizes` are empty. No segment exceeds its MEMORY region, no two load segments overlap, no stack/FIFO/data range overlaps, and no suspicious orphan or spill allocation is present. The program/data/stack memory gate is PASS.

### First native production result — FAIL

The guarded first production run recorded:

- canonical runner SHA-256 `742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad`;
- anchored backend `dr2d-mlkem512-kpke-keygen:silicon`;
- every ACVP tcId 01–25 failed;
- `TOTAL 0/25 FAIL`;
- exit code 1;
- the guard threw as designed.

This is a decisive production physical FAIL, not an unavailable runtime and not an incomplete gate. No repeat production/25-case execution, push, or package is authorized.

The distinction between case-level `FAIL` and `ERROR` is material. The silicon test prints `ERROR` when `run_mlkem512_kpke_keygen` raises. The graph returns only after `abi.parse_result` accepts the terminal record. That parser rejects, by exception, wrong magic, wrong request ID, unknown or nonzero error status, wrong key lengths, CRC mismatch, all-zero payload, non-canonical polynomial lanes, and malformed length. A plain case-level `FAIL` therefore means a syntactically and cryptographically framed `STATUS_OK` record was transported and parsed, but its `(ekPKE, dkPKE)` bytes differed from the ACVP expected tuple.

The retained-log classifier is now confirmed:

- log SHA-256 `1348dfb53446c4781c14b967fc535c5694cff2d1d56af097efc67cecd902be6c`;
- silicon backend true;
- 25 plain `FAIL`, zero `ERROR`, zero `PASS`;
- anchored `TOTAL 0/25 FAIL`;
- exact gate and parser lines confirm that only tuple mismatch can produce plain `FAIL`.

The physical classification is therefore conclusively **valid parsed STATUS_OK records with systematic cryptographic payload mismatch**, not transport/status/whole-record failure. Uniform 0/25 points to a deterministic semantic error common to every case—such as coefficient contents, transform/sampling/arithmetic semantics, or persistence between repaired stages—not an intermittent FIFO/serializer/CRC route failure. Compile-only full-width-store, memory, and topology proofs establish shape and placement; they do not establish arithmetic equality.

The completed 25-case process did not retain raw terminal bytes: the graph parsed the 1,588-byte record into `(ekPKE, dkPKE)`, then zeroized/discarded the backing result tensor, and the silicon gate discarded `actual` after printing FAIL. Those bytes cannot be recovered post-process.

One—and only one—additional native invocation is narrowly authorized because it is the minimum way to recover an actual payload for localization. It is limited to ACVP tcId 01, uses an additive temporary script outside the repository, calls the production graph exactly once, leaves production sources and the canonical runner unchanged, hashes all protected inputs before and after, hashes the diagnostic script and output, and reports:

- first mismatching region and byte;
- per-region actual/expected SHA-256 and byte mismatch count;
- `rho` equality and first rho mismatch;
- per-polynomial first differing coefficient and coefficient mismatch count;
- count of coefficient mismatches where low 8 bits agree and only bits 8–11 differ.

No 25-case repeat, second diagnostic case, push, or package is authorized. Run exactly this one command:

```powershell
& {
  $python = ".\third_party\mlir-aie\ironenv\Scripts\python.exe"
  $script = Join-Path $env:TEMP "pqc_dr2d_one_case_payload_localizer_20260818.py"
  $log = ".\PQC_DR2D_one_case_payload_localizer_20260818.log"
  $hashRecord = ".\PQC_DR2D_one_case_payload_localizer_20260818.sha256"
  $protected = @(
    ".\run_all_silicon_tests.py",
    ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_abi.py",
    ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_graph.py",
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_internal.hpp",
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc",
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row0_expand.cc",
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row0_accumulate.cc",
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row1_expand.cc",
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row1_accumulate.cc",
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_serialize.cc",
    ".\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_keygen.py",
    ".\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_keygen_silicon.py"
  )
  $expected = @{
    ".\run_all_silicon_tests.py" = "742591321AC5DC3069A51DED4E198905367F8DC6261DF8C3EBAE20B5E333FBAD"
    ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_abi.py" = "A6F44C68787905F6B4819598BAACAC59BF5BCC4A3125C8151B7863345E9FF4F4"
    ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_graph.py" = "E17E17B8481BC1FA8492A7E2BC9184FBAE095B55C5E175B015AA19A2BC999694"
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_internal.hpp" = "16D61E6ADA4D7DE384B3981CC76D3DE8319CE2BEC999727D4847567E7E1F3519"
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc" = "2F94E2995706AC5636F35C66167E5DD8F54AC54B618C200BF4EE45B8B754CEAF"
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row0_expand.cc" = "D95106C0F01A1A99AEE21CEF3FAB704B1E57BD6D1D4E066F7E421F0DD0B53986"
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row0_accumulate.cc" = "A577360C6E24296576DAEDFDC537D04765AAEBFDC74EEADD34358437986E0622"
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row1_expand.cc" = "C893D0158F85A00C6DFD6A7F20C6AA2C5259D397AC64C32D4C3F9E8CB82C13C8"
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row1_accumulate.cc" = "235C69D008E7DB656C26053A404980B7DE139156C8C4671AC94A04C7FB1C9806"
    ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_serialize.cc" = "23F691BC40410F7BDF9573A14BC01C590A3E9D2A36B07E807E415B033D49780C"
  }

  $pre = @{}
  foreach ($path in $protected) {
    $pre[$path] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
  }
  foreach ($path in $expected.Keys) {
    if ($pre[$path] -ne $expected[$path]) {
      throw "Pinned source identity mismatch before diagnostic: $path"
    }
  }

  @'
import hashlib
import json
import sys
from pathlib import Path

repo = Path.cwd()
sys.path.insert(0, str(repo))

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_graph as graph
from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_keygen import (
    ACVP_EXPECTED,
    PRE_SILICON_CORPUS,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def poly12(data):
    out = []
    for i in range(128):
        j = 3 * i
        out.append(data[j] | ((data[j + 1] & 0x0F) << 8))
        out.append((data[j + 1] >> 4) | (data[j + 2] << 4))
    return out


case = PRE_SILICON_CORPUS[0]
tc_id = int(case.label[-2:])
expected_ek, expected_dk = ACVP_EXPECTED[tc_id]

# Exactly one native production-graph invocation.
actual_ek, actual_dk = graph.run_mlkem512_kpke_keygen(case.d, case.request_id)

actual = actual_ek + actual_dk
expected = expected_ek + expected_dk
regions = [
    ("t_hat[0]", 0, actual_ek[0:384], expected_ek[0:384], True),
    ("t_hat[1]", 384, actual_ek[384:768], expected_ek[384:768], True),
    ("ek_rho", 768, actual_ek[768:800], expected_ek[768:800], False),
    ("s_hat[0]", 800, actual_dk[0:384], expected_dk[0:384], True),
    ("s_hat[1]", 1184, actual_dk[384:768], expected_dk[384:768], True),
]

report = {
    "backend": graph.BACKEND_LABEL,
    "case": case.label,
    "request_id": case.request_id,
    "native_calls": 1,
    "actual_full_sha256": sha(actual),
    "expected_full_sha256": sha(expected),
    "full_byte_mismatches": sum(a != e for a, e in zip(actual, expected)),
    "first_mismatch_region": None,
    "regions": [],
}

for name, base, a, e, is_poly in regions:
    differing = [i for i, (x, y) in enumerate(zip(a, e)) if x != y]
    item = {
        "name": name,
        "base_offset": base,
        "actual_sha256": sha(a),
        "expected_sha256": sha(e),
        "byte_mismatches": len(differing),
        "first_byte_mismatch": None if not differing else {
            "region_offset": differing[0],
            "record_payload_offset": base + differing[0],
            "terminal_record_offset": 20 + base + differing[0],
            "actual": a[differing[0]],
            "expected": e[differing[0]],
        },
    }
    if differing and report["first_mismatch_region"] is None:
        report["first_mismatch_region"] = name
    if is_poly:
        ac = poly12(a)
        ec = poly12(e)
        cdiff = [i for i, (x, y) in enumerate(zip(ac, ec)) if x != y]
        high_only = [i for i in cdiff if (ac[i] & 0xFF) == (ec[i] & 0xFF)]
        item.update({
            "coefficient_mismatches": len(cdiff),
            "low8_equal_high4_different_count": len(high_only),
            "all_coefficient_mismatches_high_part_only": bool(cdiff)
            and len(high_only) == len(cdiff),
            "first_coefficient_mismatch": None if not cdiff else {
                "index": cdiff[0],
                "actual": ac[cdiff[0]],
                "expected": ec[cdiff[0]],
                "low8_equal": (ac[cdiff[0]] & 0xFF) == (ec[cdiff[0]] & 0xFF),
                "high4_different": (ac[cdiff[0]] >> 8) != (ec[cdiff[0]] >> 8),
            },
        })
    else:
        item["rho_equal"] = a == e
    report["regions"].append(item)

print(json.dumps(report, indent=2, sort_keys=True))
'@ | Set-Content -LiteralPath $script -Encoding UTF8

  $scriptHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $script).Hash
  $env:PYTHONDONTWRITEBYTECODE = "1"
  & {
    "UTC=$([DateTime]::UtcNow.ToString('o'))"
    "DIAGNOSTIC_SCRIPT=$script"
    "DIAGNOSTIC_SCRIPT_SHA256=$scriptHash"
    "PROTECTED_PRE_HASHES"
    foreach ($path in $protected) { "$($pre[$path])  $path" }
  } | Tee-Object -FilePath $log

  & $python $script 2>&1 | Tee-Object -FilePath $log -Append
  $rc = $LASTEXITCODE
  "ONE_CASE_DIAGNOSTIC_EXIT_CODE=$rc" | Tee-Object -FilePath $log -Append

  $changed = @()
  "PROTECTED_POST_HASHES" | Tee-Object -FilePath $log -Append
  foreach ($path in $protected) {
    $post = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
    "$post  $path" | Tee-Object -FilePath $log -Append
    if ($post -ne $pre[$path]) { $changed += $path }
  }

  $logHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $log).Hash
  @(
    "DIAGNOSTIC_SCRIPT_SHA256=$scriptHash",
    "DIAGNOSTIC_OUTPUT_SHA256=$logHash"
  ) | Set-Content -LiteralPath $hashRecord -Encoding ASCII

  if ($changed.Count -ne 0) {
    throw "Protected source changed during diagnostic: $($changed -join ', ')"
  }
  if ($rc -ne 0) {
    throw "The single authorized tcId-01 diagnostic failed; no further native run is authorized."
  }
}
```

### One-case localization result — completed safely, no further native run

The single authorized call completed with backend `dr2d-mlkem512-kpke-keygen:silicon`, tcId 01, `native_calls = 1`, exit code 0, and identical protected pre/post hashes. Its payload evidence is:

- actual full SHA-256 `e3af666e595033e4010115462744fc49763eb1d96754fcfa2d5c703b0405e755`;
- expected full SHA-256 `82f988d32466c997c766fd95d6441844d00f0fc251a4c13538ad93f16a28d39c`;
- 1,532 differing payload bytes;
- `rho` exact: zero mismatches and identical SHA-256 `b6db3d7f30de11fc03d997d25208abd3d622d644c08fec75c40cf742a076a361`;
- all four polynomials differ in all 256 coefficients:
  - `t_hat[0]`: 381 byte mismatches; coefficient 0 actual 3208, expected 1576;
  - `t_hat[1]`: 384 byte mismatches; coefficient 0 actual 287, expected 1385;
  - `s_hat[0]`: 384 byte mismatches; coefficient 0 actual 2281, expected 905;
  - `s_hat[1]`: 383 byte mismatches; coefficient 0 actual 1067, expected 2192;
- only 0–2 coefficient mismatches per polynomial preserve the low 8 bits, conclusively rejecting a high-byte-only failure.

The earliest output with a direct producer is W0's `s_hat[0]/s_hat[1]`; both `t_hat` rows are downstream of W0 secrets and errors. Exact `rho` shows that G's first 32 output bytes and the rho route are correct, but it does **not** independently prove G's second 32 bytes (`sigma`), so sigma extraction remains part of the W0 suspect surface.

Offline tcId-01 hypothesis testing against the independent DR2b reference gives canonical first coefficients `[905, 2192, 199, 667]` for counters 0–3. Against actual W0-observable first values `(2281, 1067)`:

- s0 actual 2281 occurs nowhere in the canonical counter-0 NTT vector, ruling out any pure output permutation or pair-lane swap as the sole cause;
- pair swap predicts `(476, 887)`, not actual;
- the modular scale ratios are 2857 and 2681, ruling out one common Montgomery/scaling factor;
- no counter remap among 0–3 matches both values;
- no tested combination of canonical/include-k0/negated/inverse/reversed/natural-order zetas with canonical/negated/pair-swapped/reversed/bit-reversed-index CBD vectors matches both actual first values.

Stale SampleNTT `pending` state cannot explain wrong `s_hat`, because that state exists in W1/W3 matrix expansion, downstream from W0. The existing host harness proves the current W0 source formulation matches the independent reference, and the source intentionally duplicates the physically validated DR2b CBD3/NTT formulation. Therefore the leading hypothesis is **integrated W0 AIE2 target-code dataflow/arithmetic mis-lowering between sigma extraction, CBD3, NTT, and the value operands feeding the full-word pair stores**, rather than wrong source zetas, a global Montgomery factor, pair-lane order, or the original partial-store/high-byte defect.

No raw actual vector beyond the reported summaries was retained, and no further native call is authorized. The next step is read-only extraction of the complete pinned W0 worker/helper arithmetic, symbol table, and zeta-bearing data section:

```powershell
& {
  $cache = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6"
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $elf = "$cache\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $seed = ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc"
  $internal = ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_internal.hpp"
  $out = ".\PQC_DR2D_W0_full_arithmetic_disassembly_20260818.txt"

  & {
    "ELF_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash)"
    "SEED_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $seed).Hash)"
    "INTERNAL_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $internal).Hash)"
    "===== W0 SYMBOL TABLE ====="
    & $objdump -t $elf
    "===== W0 .data / FROZEN ZETA BYTES ====="
    & $objdump -s -j .data $elf
    "===== W0 UNFILTERED WORKER + derive_g + CBD3 + NTT + PAIR-STORE INPUTS ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x01a0 --stop-address=0x17c0 $elf
  } | Tee-Object -FilePath $out
}
```

### Partial W0 target capture — no decisive mis-lowering yet

The capture matches the pinned identities and establishes:

- `cbd3_ntt_store_dr2b` at `0x1140`, size `0x870`, hence exact extent `[0x1140,0x19b0)`;
- `keccak_f1600` at `0x19b0`, size `0x7f0`, extent `[0x19b0,0x21a0)`;
- `ntt` at `0x21a0`, size `0x1d0`, extent `[0x21a0,0x2370)`;
- `kZetas` at `.data 0x7c020`, size `0x100`; the captured little-endian bytes decode to the pinned 128-entry table.

The worker portion visibly:

- calls the shared `keccak_f1600`;
- copies state byte `i` to rho and state byte `32+i` to sigma in the same 32-iteration path;
- passes counters 0, 1, 2, and 3 to four ordered helper calls;
- preserves the already-proved output offsets and short-circuit routing.

The helper portion visibly:

- clears its 200-byte state;
- absorbs 32 sigma bytes and the counter;
- applies SHAKE256 domain/final bits at state offsets 33 and 135;
- calls `keccak_f1600` twice;
- stages the first 136 and remaining 56 PRF bytes;
- executes a 256-coefficient CBD loop with 32-bit local coefficient stores;
- calls the separate `ntt` at `0x16d0`;
- feeds the transformed local array into the already-proved full-word pair-store pipeline.

Nothing in the captured range is yet a conclusive arithmetic defect. In particular, the `0x1444 movxm r2,#0x100000` / modifier sequence cannot be classified as an invalid offset without the omitted continuation and authoritative AIE2 modifier/20-bit semantics; it is not treated as a blocker by appearance. The current capture stops before:

1. helper cleanup/return `[0x17c0,0x19b0)`;
2. the full shared Keccak body `[0x19b0,0x21a0)`;
3. the entire noinline NTT `[0x21a0,0x2370)`.

The first continuation attempt preserved valid pinned hashes and source excerpts, but its single disassembly request started at `0x17c0`, which is inside the bundle beginning at `0x17be`. LLVM-AIE's disassembler asserted, emitted unknown bytes, and produced no usable helper-tail, Keccak, or NTT instructions. That binary output is **no evidence** and supports no inference. The source excerpts remain valid source evidence.

The NTT is still the highest-priority omission because source-level zeta/order hypotheses were rejected, yet no target instruction currently proves the seven-stage butterfly, zeta loads, `__umodsi3` calls, or final local-array contents. Run exactly this corrected read-only command. It uses three separate invocations, starts at the known helper bundle and exact Keccak/NTT symbols, and deliberately omits `-S`:

```powershell
& {
  $cache = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6"
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $elf = "$cache\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $out = ".\PQC_DR2D_W0_CBD_tail_Keccak_NTT_aligned_20260818.txt"

  & {
    "ELF_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash)"

    "===== HELPER TAIL: bundle 0x17be through symbol end 0x19b0 ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x17be --stop-address=0x19b0 $elf
    if ($LASTEXITCODE -ne 0) { throw "Helper-tail disassembly failed." }

    "===== KECCAK: exact symbol 0x19b0 through 0x21a0 ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x19b0 --stop-address=0x21a0 $elf
    if ($LASTEXITCODE -ne 0) { throw "Keccak disassembly failed." }

    "===== NTT: exact symbol 0x21a0 through 0x2370 ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x21a0 --stop-address=0x2370 $elf
    if ($LASTEXITCODE -ne 0) { throw "NTT disassembly failed." }
  } | Tee-Object -FilePath $out
}
```

### Complete aligned W0 capture — no instruction-level defect proved

The corrected capture is valid and complete for the requested ranges.

**Helper tail.** The three visible zeroization loops clear exactly the local coefficient array (`0x400` bytes), PRF (`0xc0` bytes), and state (`0xc8` bytes), then restore the frame and return the helper's success predicate. No omitted coefficient write or alternate arithmetic path appears.

**Keccak.** The full shared `keccak_f1600` symbol is present with 24-round control and full-word lane loads/stores. It is the unchanged shared implementation previously exercised by DR1/DR2b. The known Phoenix defect concerned vulnerable partial-width coefficient stores in ZOL-end scheduling; the Keccak lane updates here are full-word stores. The derive and helper absorption/extraction loops intentionally use one-byte loads/stores for byte arrays, not high halves of coefficient objects, so the known coefficient-store failure mechanism does not directly apply to them.

Exact rho proves Keccak/state bytes 0–31 and their extraction route for tcId 01. It remains logically possible for bytes 32–63 (`sigma`) to be wrong while rho is right, because sigma was not retained or externally reported. Static code shows no conditional or different extraction algorithm for the second half, but static inspection alone cannot prove those runtime bytes.

**NTT.** Accounting for AIE2 delayed-call semantics, the complete `0x21a0–0x2370` symbol matches the source algorithm:

- seven-stage outer control is present;
- the zeta base is exactly `0x7c020`;
- k starts at 1, is scaled by two, and indexes 16-bit zetas;
- start and lane offsets use 4-byte coefficient stride;
- at `0x224c`, `jl #0x2370` calls `__umodsi3`; its delay slots at `0x2258` and `0x225c` compute/set `r1 = r[j+length] * zeta` and `r2 = 3329` before the callee consumes them;
- returned `r0` is therefore `t = product mod q`, not a stale pre-call operand;
- `0x228c–0x229c` implements `(r[j] - t) mod q`;
- `0x22a0–0x22d4` implements `(r[j] + t) mod q`;
- k, start, and stage counters advance to 127 twiddles across seven stages.

Thus neither the apparent post-`jl` multiply nor divisor setup is a defect; they are call-delay-slot work. No wrong zeta base/index, missing reduction, sign inversion, stage omission, pair-lane swap, or obvious stack/address error is proved.

The full static capture therefore still cannot distinguish:

1. a runtime sigma-value problem before CBD;
2. a target-specific CBD variable-shift/data-staging misexecution;
3. a subtler integrated-context execution issue despite semantically correct NTT assembly;
4. later persistence/copy corruption not visible in the final store-width map.

The safest next discriminator is a read-only target comparison against the physically passed DR2b cache artifact, whose source formulation is intentionally identical. The command below searches cached ELFs for `dr2b_cbd3_ntt_consume`, records hashes/timestamps/cache paths, and disassembles each matching DR2b NTT using its own symbol address and size. It performs no compilation or hardware execution:

```powershell
& {
  $cacheRoot = "`$HOME`\.npu\cache"
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $out = ".\PQC_DR2D_W0_vs_cached_DR2B_NTT_20260818.txt"
  $dr2bSource = ".\phoenix_sdr_dsp\pqc\kernels\dr2b_mlkem512_cbd_ntt.cc"

  & {
    "DR2B_SOURCE_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $dr2bSource).Hash)"
    $matches = @()

    foreach ($elf in Get-ChildItem -LiteralPath $cacheRoot -Recurse -File -Filter *.elf) {
      $symbols = & $objdump -t $elf.FullName 2>$null
      if ($LASTEXITCODE -eq 0 -and
          ($symbols -match 'dr2b_cbd3_ntt_consume')) {
        $matches += [pscustomobject]@{
          File = $elf
          Symbols = $symbols
        }
      }
    }

    "DR2B_MATCHING_ELF_COUNT=$($matches.Count)"
    foreach ($match in $matches) {
      $elf = $match.File
      "===== DR2B ELF: $($elf.FullName) ====="
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $elf.FullName).Hash)"
      "UTC=$($elf.LastWriteTimeUtc.ToString('o')) SIZE=$($elf.Length)"
      $match.Symbols

      $nttLine = $match.Symbols |
        Where-Object { $_ -match '\s_ZN12_GLOBAL__N_13nttEPj\s*$' } |
        Select-Object -First 1
      if ($null -eq $nttLine) {
        "NTT_SYMBOL_NOT_FOUND"
        continue
      }

      $parts = ($nttLine.Trim() -split '\s+')
      $start = [Convert]::ToUInt32($parts[0], 16)
      $size = [Convert]::ToUInt32($parts[4], 16)
      $stop = $start + $size
      "NTT_RANGE=0x$($start.ToString('x'))-0x$($stop.ToString('x'))"
      & $objdump -d --triple=aie2 --disassemble-zeroes `
        --start-address=$start --stop-address=$stop $elf.FullName
      if ($LASTEXITCODE -ne 0) {
        throw "Aligned DR2b NTT disassembly failed for $($elf.FullName)"
      }
    }
  } | Tee-Object -FilePath $out
}
```

### Physically passed DR2b NTT comparison — NTT ruled out

The cache search found exactly one DR2b ELF:

- cache `4311961d4f3a43976aa5a60d`;
- core 0_3;
- ELF SHA-256 `0f1e4f9563a6716c3076bdc8ad4c8d43dc6dfd566cf0de2fd67b14d937261125`;
- NTT symbol `[0x0ab0,0x0c80)`, size `0x1d0`.

That DR2b NTT is instruction-identical to W0's `[0x21a0,0x2370)` NTT after relocating absolute addresses:

- prologue, frame size, saved registers, and register allocation are identical;
- constants `q=0xd01`, `q-1=0xd00`, `-q`, k=1, length=128, stride=2, stage limit=7 are identical;
- loop blocks, zeta index scaling, butterfly pointer calculations, loads, conditionals, stores, and counter updates use the same opcodes and registers in the same order;
- the only zeta-base difference is the expected relocation (`0x7c008` in DR2b versus `0x7c020` in W0);
- the `jl` target differs only because each ELF's identical `__umodsi3` is at a different address;
- call-delay-slot multiply/divisor setup and both modular reductions are byte-for-byte the same apart from relocated branch/call immediates;
- both symbols are exactly `0x1d0` bytes.

This is stronger than semantic similarity: it is the same target implementation modulo layout relocation. Because that implementation physically passed all 13 DR2b silicon vectors, the NTT code itself is ruled out as the root cause. An identical NTT can still transform wrong input correctly, so the remaining leading surfaces are:

1. W0 sigma bytes before PRF;
2. W0 SHAKE256 PRF staging;
3. W0's **inlined** CBD3 lowering;
4. corruption before the NTT call or after it in persistence/copies.

The CBD distinction is now especially important: the physically passed DR2b ELF contains a standalone `cbd3` symbol `[0x8a0,0xab0)`, while W0 has no CBD symbol and inlines the same source into `[0x14ec,0x16d0)`. The next read-only command captures those two forms side by side, along with exact source identities:

```powershell
& {
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $w0 = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $dr2b = "`$HOME`\.npu\cache\4311961d4f3a43976aa5a60d\elfs_main_core_0_3\elfs_main_core_0_3.elf"
  $w0Source = ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc"
  $dr2bSource = ".\phoenix_sdr_dsp\pqc\kernels\dr2b_mlkem512_cbd_ntt.cc"
  $out = ".\PQC_DR2D_W0_inlined_CBD_vs_passed_DR2B_CBD_20260818.txt"

  & {
    "W0_ELF_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0).Hash)"
    "DR2B_ELF_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $dr2b).Hash)"
    "W0_SOURCE_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0Source).Hash)"
    "DR2B_SOURCE_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $dr2bSource).Hash)"

    "===== PHYSICALLY PASSED DR2B STANDALONE CBD3: 0x8a0-0xab0 ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x8a0 --stop-address=0xab0 $dr2b
    if ($LASTEXITCODE -ne 0) { throw "DR2b CBD3 disassembly failed." }

    "===== FAILING W0 INLINED CBD3: bundle-aligned 0x14c0-0x16d0 (body starts 0x14ec) ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x14c0 --stop-address=0x16d0 $w0
    if ($LASTEXITCODE -ne 0) { throw "W0 CBD3 disassembly failed." }

    "===== W0 CBD SOURCE LINES 11-25 ====="
    $s = Get-Content -LiteralPath $w0Source
    11..25 | ForEach-Object { "{0}: {1}" -f $_,$s[$_ - 1] }

    "===== DR2B CBD SOURCE LINES 38-46 ====="
    $d = Get-Content -LiteralPath $dr2bSource
    38..46 | ForEach-Object { "{0}: {1}" -f $_,$d[$_ - 1] }
  } | Tee-Object -FilePath $out
}
```

### Physically passed DR2b CBD comparison — CBD ruled out

The CBD sources are textually the same algorithm, and the target lowerings are semantically identical under a direct renaming.

**Incoming W0 constants and bases.** Before the inlined body, W0 establishes:

- `r19 = 6` (bit-index mask used for `bit & 7` arithmetic);
- `r22 = 1` (single-bit mask);
- `r23 = 7` (low-three-bit mask);
- `r17 = 0`;
- `r20 = 3329`;
- `r0 = -3` (AIE bidirectional shift encoding of division by 8);
- `r1 = 0`;
- PRF base `p7`;
- coefficient-output base `p0`.

These map exactly to standalone DR2b constants/registers:

| Meaning | DR2b | W0 |
|---|---|---|
| PRF base | `p0` | `p7` |
| output base | `p1` | `p0` |
| mask 6 | `r0` | `r19` |
| zero | `r3` | `r1` / `r17` |
| mask 7 | `r2` | `r23` |
| mask 1 | `r1` | `r22` |
| shift -3 | `r5` | `r0` |
| q | `r4` | `r20` |
| bit index | `r7` | `r3` |
| output index | `r8` | `r4` |
| result value | `r9` | `r5` |

All six bit loads, variable-shift extraction, masks, three-bit population sums, `a-b`, negative test, conditional `+q`, output-index scaling, and 32-bit stores match under that renaming.

**ZOL and two-copy lowering.** Both forms use the same pipelined shape:

- an old value of 256 feeds `add.nc lc, old, #-1`;
- the register is simultaneously replaced with 2 for `4*i` output addressing;
- the first copy runs in the ZOL body and commits at DR2b `0x9b0` / W0 `0x15e0`;
- the compiler emits a second full arithmetic copy as the pipelined epilogue;
- the final store is present at DR2b `0xa9c` / W0 `0x16ca`;
- the final output-index increment is present;
- W0 immediately calls NTT at `0x16d0`.

Thus the comparison captures the complete final computation and second store. There is no missing tail, off-by-one count, changed mask, different q correction, PRF/output-base swap, or CBD arithmetic difference. Since the standalone target implementation physically passed DR2b and W0 implements the same operations under register allocation/inlining, CBD itself is ruled out.

The narrowed suspect surface is now:

1. sigma bytes produced/extracted by `derive_g`;
2. SHAKE256 PRF absorption or 136+56-byte staging before CBD;
3. corruption of the local coefficient array between CBD and the identical NTT;
4. post-NTT pair packing or later copies despite correct store widths.

No raw actual vector is available, so the next non-native discriminator tests the known tcId-01 actual first pair `(2281,1067)` against deterministic sigma and PRF-staging hypotheses. It uses only independent host references and prints exact matches plus the nearest candidates:

```powershell
& {
  $python = ".\third_party\mlir-aie\ironenv\Scripts\python.exe"
  $out = ".\PQC_DR2D_tcId01_sigma_PRF_hypotheses_20260818.txt"

  @'
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from tests.pqc_device_resident.dr2b_reference import (
    cbd3_reference,
    ntt_reference,
)
from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_keygen import (
    PRE_SILICON_CORPUS,
)

Q = 3329
ACTUAL = (2281, 1067)
case = PRE_SILICON_CORPUS[0]
g = hashlib.sha3_512(case.d + bytes((2,))).digest()
rho, sigma = g[:32], g[32:]


def first_ntt(prf):
    return ntt_reference(cbd3_reference(prf))[0]


def bit_reverse_byte(x):
    return int(f"{x:08b}"[::-1], 2)


sigma_candidates = {
    "canonical_sigma": sigma,
    "rho_as_sigma": rho,
    "zero_sigma": bytes(32),
    "reversed_sigma": sigma[::-1],
}
for shift in range(1, 32):
    sigma_candidates[f"sigma_rotate_left_{shift}"] = (
        sigma[shift:] + sigma[:shift]
    )
for offset in range(64):
    doubled = g + g
    sigma_candidates[f"g_cyclic_window_{offset}"] = doubled[offset:offset + 32]


def prf_pair(sig, mode):
    if mode == "canonical":
        return tuple(
            hashlib.shake_256(sig + bytes((c,))).digest(192)
            for c in (0, 1)
        )
    if mode == "counter_prefix":
        return tuple(
            hashlib.shake_256(bytes((c,)) + sig).digest(192)
            for c in (0, 1)
        )
    if mode == "counter_omitted":
        p = hashlib.shake_256(sig).digest(192)
        return p, p
    if mode == "stale_counter_zero":
        p = hashlib.shake_256(sig + b"\x00").digest(192)
        return p, p
    if mode == "counter_plus_one":
        return tuple(
            hashlib.shake_256(sig + bytes((c + 1,))).digest(192)
            for c in (0, 1)
        )
    if mode == "shake128":
        return tuple(
            hashlib.shake_128(sig + bytes((c,))).digest(192)
            for c in (0, 1)
        )
    raise AssertionError(mode)


def stage(prf, mode):
    if mode == "exact_136_plus_56":
        return prf
    if mode == "repeat_first_56_as_tail":
        return prf[:136] + prf[:56]
    if mode == "zero_tail_56":
        return prf[:136] + bytes(56)
    if mode == "reverse_all":
        return prf[::-1]
    if mode == "rotate_left_one":
        return prf[1:] + prf[:1]
    if mode == "rotate_right_one":
        return prf[-1:] + prf[:-1]
    if mode == "bit_reverse_each_byte":
        return bytes(bit_reverse_byte(x) for x in prf)
    raise AssertionError(mode)


prf_modes = (
    "canonical",
    "counter_prefix",
    "counter_omitted",
    "stale_counter_zero",
    "counter_plus_one",
    "shake128",
)
stage_modes = (
    "exact_136_plus_56",
    "repeat_first_56_as_tail",
    "zero_tail_56",
    "reverse_all",
    "rotate_left_one",
    "rotate_right_one",
    "bit_reverse_each_byte",
)


def distance(got):
    total = 0
    for a, b in zip(got, ACTUAL):
        d = (a - b) % Q
        total += min(d, Q - d)
    return total


rows = []
for sigma_name, sig in sigma_candidates.items():
    for prf_mode in prf_modes:
        p0, p1 = prf_pair(sig, prf_mode)
        for stage_mode in stage_modes:
            got = (
                first_ntt(stage(p0, stage_mode)),
                first_ntt(stage(p1, stage_mode)),
            )
            rows.append((distance(got), got, sigma_name, prf_mode, stage_mode))

exact = [row for row in rows if row[1] == ACTUAL]
print(f"CASE={case.label}")
print(f"RHO_SHA256={hashlib.sha256(rho).hexdigest()}")
print(f"CANONICAL_SIGMA_SHA256={hashlib.sha256(sigma).hexdigest()}")
print(f"ACTUAL_FIRSTS={ACTUAL}")
print(f"HYPOTHESES={len(rows)} EXACT_MATCHES={len(exact)}")
for row in exact:
    print("EXACT", row)
print("NEAREST_20")
for row in sorted(rows)[:20]:
    print(row)
'@ | & $python - 2>&1 | Tee-Object -FilePath $out

  if ($LASTEXITCODE -ne 0) {
    throw "Offline sigma/PRF hypothesis test failed."
  }
}
```

### Offline sigma/PRF hypothesis matrix — no deterministic match

The tcId-01 matrix evaluated 4,158 combinations and found zero exact matches for actual first coefficients `(2281,1067)`. It covered:

- canonical sigma, rho-as-sigma, zero/reversed/rotated sigma, and every cyclic 32-byte window of G output;
- canonical suffix-counter SHAKE256, prefix counter, omitted/stale/off-by-one counter, and SHAKE128;
- exact 136+56 staging, repeated or zero second-block tail, byte reversal, one-byte rotations, and per-byte bit reversal.

The nearest result, distance 23, was `(2282,1089)` from the implausible compound `g_cyclic_window_10 + SHAKE128 + rotate_right_one`. No canonical or simple one-defect variant matched. The canonical sigma SHA-256 is `0ae20d0e1bfe749b3e324d91e81e140156c6bf8a34063185acae84f0c91c3248`.

This does not mathematically exclude every possible sigma/PRF corruption because only two actual coefficients were retained. It does rule out the broad set of natural source-level mistakes tested and makes an ordinary counter/domain/offset/tail bug unlikely. With NTT and CBD target implementations already ruled out, the strongest remaining static discriminator is the shared Keccak target code.

The physically passed DR2b cache includes the producer and consumer ELFs from the same 13/13 run. The command below searches that exact cache for the shared `keccak_f1600` symbol, records each matching ELF identity, dynamically extracts the symbol range, and prints it beside W0's exact Keccak. It performs no compilation or hardware execution:

```powershell
& {
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $dr2bCache = "`$HOME`\.npu\cache\4311961d4f3a43976aa5a60d"
  $w0 = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $out = ".\PQC_DR2D_W0_vs_passed_DR2B_Keccak_20260818.txt"
  $keccakPattern = '_ZN15phoenix_sdr_dsp3pqc3dr1L12keccak_f1600EPh'

  & {
    "W0_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0).Hash)"
    "===== W0 KECCAK 0x19b0-0x21a0 ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x19b0 --stop-address=0x21a0 $w0
    if ($LASTEXITCODE -ne 0) { throw "W0 Keccak disassembly failed." }

    $matches = @()
    foreach ($elf in Get-ChildItem -LiteralPath $dr2bCache -Recurse -File -Filter *.elf) {
      $symbols = & $objdump -t $elf.FullName 2>$null
      $line = $symbols |
        Where-Object { $_ -match "$keccakPattern\s*$" } |
        Select-Object -First 1
      if ($null -ne $line) {
        $matches += [pscustomobject]@{
          File = $elf
          Line = $line
          Symbols = $symbols
        }
      }
    }

    "PASSED_DR2B_KECCAK_ELF_COUNT=$($matches.Count)"
    foreach ($match in $matches) {
      $elf = $match.File
      $parts = ($match.Line.Trim() -split '\s+')
      $start = [Convert]::ToUInt32($parts[0], 16)
      $size = [Convert]::ToUInt32($parts[4], 16)
      $stop = $start + $size

      "===== PASSED DR2B KECCAK ELF: $($elf.FullName) ====="
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $elf.FullName).Hash)"
      "UTC=$($elf.LastWriteTimeUtc.ToString('o')) SIZE=$($elf.Length)"
      "KECCAK_RANGE=0x$($start.ToString('x'))-0x$($stop.ToString('x'))"
      $match.Line
      & $objdump -d --triple=aie2 --disassemble-zeroes `
        --start-address=$start --stop-address=$stop $elf.FullName
      if ($LASTEXITCODE -ne 0) {
        throw "Passed DR2b Keccak disassembly failed for $($elf.FullName)"
      }
    }
  } | Tee-Object -FilePath $out
}
```

### First Keccak comparison attempt — DR2b portion is no evidence

The W0 Keccak disassembly completed and remains valid. The search reported one DR2b match, but the recorded path, symbol line, hash, timestamp, range, and disassembly were empty. Therefore no passed-DR2b Keccak comparison was produced; that portion is **no evidence**.

Root cause of the command failure: PowerShell variable names are case-insensitive. The script used `$matches` for its result array while `Where-Object { $_ -match ... }` populated the automatic `$Matches` regex hashtable. These are the same variable to PowerShell, so the regex operation overwrote/corrupted the intended object collection. Iteration then saw an object without the expected `File`/`Line` properties, yielding blank fields.

The corrected command avoids both hazards:

- result collection is named `$keccakEntries`, never `$matches`;
- `[regex]::IsMatch` is used instead of `-match`, so the automatic `$Matches` variable is untouched;
- each object stores an immutable `FullName` string and explicit `SymbolLine`;
- path existence, symbol token count, numeric address/size, and nonzero size are validated before disassembly.

```powershell
& {
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $dr2bCache = "`$HOME`\.npu\cache\4311961d4f3a43976aa5a60d"
  $out = ".\PQC_DR2D_passed_DR2B_Keccak_corrected_20260818.txt"
  $symbolName = "_ZN15phoenix_sdr_dsp3pqc3dr1L12keccak_f1600EPh"
  $symbolRegex = [regex]::Escape($symbolName) + "\s*$"

  & {
    $keccakEntries = [System.Collections.Generic.List[object]]::new()

    foreach ($item in Get-ChildItem -LiteralPath $dr2bCache -Recurse -File -Filter *.elf) {
      $fullName = [string]$item.FullName
      $symbolLines = @(& $objdump -t $fullName 2>$null)
      if ($LASTEXITCODE -ne 0) { continue }

      $symbolLine = $symbolLines |
        Where-Object { [regex]::IsMatch([string]$_, $symbolRegex) } |
        Select-Object -First 1

      if ($null -ne $symbolLine) {
        $keccakEntries.Add([pscustomobject]@{
          FullName = $fullName
          SymbolLine = [string]$symbolLine
        })
      }
    }

    "PASSED_DR2B_KECCAK_ELF_COUNT=$($keccakEntries.Count)"
    foreach ($entry in $keccakEntries) {
      $fullName = [string]$entry.FullName
      $symbolLine = [string]$entry.SymbolLine

      if (-not (Test-Path -LiteralPath $fullName)) {
        throw "Matched ELF path does not exist: $fullName"
      }

      $parts = @($symbolLine.Trim() -split "\s+")
      if ($parts.Count -lt 6) {
        throw "Unexpected symbol-table format: $symbolLine"
      }

      $start = [Convert]::ToUInt32($parts[0], 16)
      $size = [Convert]::ToUInt32($parts[4], 16)
      if ($size -eq 0) {
        throw "Matched Keccak symbol has zero size: $symbolLine"
      }
      $stop = $start + $size
      $file = Get-Item -LiteralPath $fullName

      "===== PASSED DR2B KECCAK ELF ====="
      "FULLNAME=$fullName"
      "SYMBOL_LINE=$symbolLine"
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $fullName).Hash)"
      "UTC=$($file.LastWriteTimeUtc.ToString('o'))"
      "FILE_SIZE=$($file.Length)"
      "START_DEC=$start SIZE_DEC=$size STOP_DEC=$stop"
      "KECCAK_RANGE=0x$($start.ToString('x'))-0x$($stop.ToString('x'))"

      & $objdump -d --triple=aie2 --disassemble-zeroes `
        --start-address=$start --stop-address=$stop $fullName
      if ($LASTEXITCODE -ne 0) {
        throw "Passed DR2b Keccak disassembly failed: $fullName"
      }
    }
  } | Tee-Object -FilePath $out
}
```

### Corrected physically passed DR2b Keccak comparison — Keccak ruled out

The corrected extraction found exactly one passed DR2b Keccak:

- DR2b producer core 0_2 in cache `4311961d4f3a43976aa5a60d`;
- ELF SHA-256 `0b83cfe2a1d5a6fe758fd448946ddfd92b863289b8e539cc0273157121321502`;
- symbol `[0x0af0,0x12e0)`, size `0x7f0`;
- W0 symbol `[0x19b0,0x21a0)`, also size `0x7f0`;
- relocation delta exactly `0xec0`.

Both disassemblies contain 330 instructions. Raw instruction bytes and decoded operands are identical except seven control-flow encodings whose local call/branch/ZOL addresses move by the expected layout delta:

1. the internal `__umodsi3` call;
2. the 24-round loop backedge;
3. two ZOL `ls/le` pairs;
4. the final round-loop backedge.

All lane loads/stores, rotations, XOR/AND/selection operations, round constants, round counts, stack layout, registers, and non-control immediates are identical. This is the same target implementation modulo relocation, and it physically passed as part of DR2b's 13/13 silicon run. Keccak itself is therefore ruled out.

The remaining W0-specific surfaces are now sharply limited:

1. derive_g's construction and extraction of sigma despite the shared Keccak;
2. helper-specific SHAKE absorption/domain setup and 136+56 PRF staging around the shared Keccak calls;
3. post-NTT pair-value loading/packing;
4. downstream secret persistence copies.

The strongest next static discriminator compares W0's helper-specific SHAKE path with the physically passed DR2b SHAKE256 PRF producer from the same core-0_2 ELF. The command records the full producer symbol table and dynamically extracts its local `emit` function, then prints W0's helper pre-CBD range and both source formulations:

```powershell
& {
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $passed = "`$HOME`\.npu\cache\4311961d4f3a43976aa5a60d\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $w0 = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $passedSource = ".\phoenix_sdr_dsp\pqc\kernels\dr2b_mlkem512_shake256_prf_service.cc"
  $w0Source = ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc"
  $out = ".\PQC_DR2D_W0_SHAKE_staging_vs_passed_DR2B_PRF_20260818.txt"

  & {
    "PASSED_ELF_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $passed).Hash)"
    "W0_ELF_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0).Hash)"
    "PASSED_SOURCE_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $passedSource).Hash)"
    "W0_SOURCE_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0Source).Hash)"

    $symbols = @(& $objdump -t $passed)
    "===== PASSED DR2B PRODUCER SYMBOL TABLE ====="
    $symbols

    $emitLine = $symbols |
      Where-Object {
        [regex]::IsMatch(
          [string]$_,
          '_ZN12_GLOBAL__N_14emitE.*\s*$'
        )
      } |
      Select-Object -First 1
    if ($null -eq $emitLine) {
      throw "Passed DR2b local emit symbol not found."
    }

    $parts = @(([string]$emitLine).Trim() -split "\s+")
    if ($parts.Count -lt 6) {
      throw "Unexpected emit symbol format: $emitLine"
    }
    $start = [Convert]::ToUInt32($parts[0], 16)
    $size = [Convert]::ToUInt32($parts[4], 16)
    $stop = $start + $size
    "PASSED_EMIT_SYMBOL=$emitLine"
    "PASSED_EMIT_RANGE=0x$($start.ToString('x'))-0x$($stop.ToString('x'))"

    "===== PHYSICALLY PASSED DR2B SHAKE256 PRF EMIT ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=$start --stop-address=$stop $passed
    if ($LASTEXITCODE -ne 0) {
      throw "Passed DR2b emit disassembly failed."
    }

    "===== W0 HELPER: STATE/SIGMA/SHAKE/136+56 PRF STAGING ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x1140 --stop-address=0x14ec $w0
    if ($LASTEXITCODE -ne 0) {
      throw "W0 helper staging disassembly failed."
    }

    "===== PASSED DR2B PRF SOURCE LINES 41-60 ====="
    $p = Get-Content -LiteralPath $passedSource
    41..60 | ForEach-Object { "{0}: {1}" -f $_,$p[$_ - 1] }

    "===== W0 HELPER SOURCE LINES 47-66 ====="
    $s = Get-Content -LiteralPath $w0Source
    47..66 | ForEach-Object { "{0}: {1}" -f $_,$s[$_ - 1] }
  } | Tee-Object -FilePath $out
}
```

### Passed DR2b SHAKE/PRF comparison — helper staging ruled out

The passed DR2b `emit` and W0 helper implement the same SHAKE256 PRF path under different local bases and output framing.

**Sigma absorb.** W0's suspicious-looking software pipeline is the same as the physically passed DR2b pipeline:

- passed DR2b uses sigma base `p0`, state base `p6`/temporary `p2`, data/state registers `r1/r2`, and index `r0`;
- W0 uses sigma base `p0`, state base `p6`/temporary `p2`, data/state registers `r4/r5`, and index `r3`;
- both preload sigma[0] and state[0], commit the first byte in the ZOL body, and rotate later logical iterations through the same index/data register name in the software pipeline.

Specifically, passed DR2b has `add r0,#1` at `0x880`, `st.s8 r0` at `0x890`, then `xor r0,r2,r1` at `0x89c`. W0 has the exact renamed sequence: `add r3,#1` at `0x12f0`, `st.s8 r3` at `0x1300`, then `xor r3,r5,r4` at `0x131a`. Under AIE software-pipeline latency/old-value semantics, the store consumes the prior logical iteration's data value already carried in that register, while the add/XOR stages prepare later logical iterations. It is not a scalar store of the current loop index. The identical schedule physically passed in DR2b, and both forms cover exactly 32 sigma bytes.

**Counter and padding.**

- state[32] receives the counter;
- state[33] receives `0x1f`;
- state[135] receives `0x80`;
- the passed and W0 sequences use the same load/store/XOR scheduling shape, with W0 able to fold the known-zero state into direct constants in places.

**Squeeze staging.**

- both make the first Keccak call and copy exactly 136 bytes from state[0..135];
- both make the second Keccak call and copy exactly 56 bytes from state[0..55];
- passed DR2b writes into output token offsets 16..207;
- W0 writes into local PRF offsets 0..191;
- the `0x100000` value represents the same 20-bit zero source modifier in both binaries;
- passed `r18=-0xfff68` accounts for header+136 destination offset 152, while W0 `r18=-0xfff78` accounts for headerless destination offset 136—the exact expected difference of 16;
- body and pipelined epilogue stores are present for both copies.

No absorb count, counter, domain byte, final bit, source offset, destination offset, second-block tail, or squeeze-call difference is proved. Given correct sigma input, W0's helper-specific SHAKE/PRF staging is semantically equivalent to the physically passed DR2b producer and is ruled out.

The remaining leading surfaces are now:

1. W0 derive_g sigma value/extraction before the helper;
2. W0 post-NTT pair-value loading and full-word packing;
3. downstream persistence copies of s0/s1.

The strongest next read-only discriminator compares W0's post-NTT pair pipeline with the physically passed full-word terminal-probe producer. It searches all caches robustly for the diagnostic probe ELF, records identities, extracts `store_probe_poly_pairs`, and prints W0's pair path:

```powershell
& {
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $cacheRoot = "`$HOME`\.npu\cache"
  $w0 = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $probeSource = ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_terminal_probe.cc"
  $out = ".\PQC_DR2D_W0_pair_pack_vs_passed_terminal_probe_20260818.txt"
  $probeRegex = [regex]::Escape("dr2d_kpke_keygen_terminal_probe") + "\s*$"
  $pairRegex = "store_probe_poly_pairs.*\s*$"
  $produceRegex = '_ZN12_GLOBAL__N_17produceE.*\s*$'

  & {
    "W0_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0).Hash)"
    "PROBE_SOURCE_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $probeSource).Hash)"

    "===== W0 POST-NTT PAIR LOAD/PACK/STORE: 0x16d0-0x17be ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x16d0 --stop-address=0x17be $w0
    if ($LASTEXITCODE -ne 0) {
      throw "W0 pair-pack disassembly failed."
    }

    $probeEntries = [System.Collections.Generic.List[object]]::new()
    foreach ($item in Get-ChildItem -LiteralPath $cacheRoot -Recurse -File -Filter *.elf) {
      $fullName = [string]$item.FullName
      $symbols = @(& $objdump -t $fullName 2>$null)
      if ($LASTEXITCODE -ne 0) { continue }

      $entryLine = $symbols |
        Where-Object { [regex]::IsMatch([string]$_, $probeRegex) } |
        Select-Object -First 1
      $pairLine = $symbols |
        Where-Object { [regex]::IsMatch([string]$_, $pairRegex) } |
        Select-Object -First 1
      $produceLine = $symbols |
        Where-Object { [regex]::IsMatch([string]$_, $produceRegex) } |
        Select-Object -First 1

      if ($null -ne $entryLine) {
        $pairText = if ($null -eq $pairLine) { "" } else { [string]$pairLine }
        $produceText = if ($null -eq $produceLine) { "" } else { [string]$produceLine }
        $chosenLine = if ($null -ne $pairLine) {
          [string]$pairLine
        } elseif ($null -ne $produceLine) {
          [string]$produceLine
        } else {
          [string]$entryLine
        }
        $probeEntries.Add([pscustomobject]@{
          FullName = $fullName
          EntryLine = [string]$entryLine
          PairLine = $pairText
          ProduceLine = $produceText
          ChosenLine = $chosenLine
        })
      }
    }

    "TERMINAL_PROBE_PAIR_ELF_COUNT=$($probeEntries.Count)"
    foreach ($entry in $probeEntries) {
      $fullName = [string]$entry.FullName
      $chosenLine = [string]$entry.ChosenLine
      $parts = @($chosenLine.Trim() -split "\s+")
      if ($parts.Count -lt 6) {
        throw "Unexpected probe symbol format: $chosenLine"
      }

      $start = [Convert]::ToUInt32($parts[0], 16)
      $size = [Convert]::ToUInt32($parts[4], 16)
      if ($size -eq 0) {
        throw "Chosen probe symbol has zero size: $chosenLine"
      }
      $stop = $start + $size
      $file = Get-Item -LiteralPath $fullName

      "===== CACHED TERMINAL-PROBE PAIR PRODUCER ====="
      "FULLNAME=$fullName"
      "ENTRY_SYMBOL=$($entry.EntryLine)"
      "PAIR_SYMBOL=$($entry.PairLine)"
      "PRODUCE_SYMBOL=$($entry.ProduceLine)"
      "DISASSEMBLED_SYMBOL=$chosenLine"
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $fullName).Hash)"
      "UTC=$($file.LastWriteTimeUtc.ToString('o')) SIZE=$($file.Length)"
      "PAIR_RANGE=0x$($start.ToString('x'))-0x$($stop.ToString('x'))"

      & $objdump -d --triple=aie2 --disassemble-zeroes `
        --start-address=$start --stop-address=$stop $fullName
      if ($LASTEXITCODE -ne 0) {
        throw "Terminal-probe pair disassembly failed: $fullName"
      }
    }

    "===== TERMINAL-PROBE PAIR SOURCE LINES 22-33 ====="
    $p = Get-Content -LiteralPath $probeSource
    22..33 | ForEach-Object { "{0}: {1}" -f $_,$p[$_ - 1] }
  } | Tee-Object -FilePath $out
}
```

### Terminal-probe pair comparison — W0 post-NTT packing ruled out

The comparison used the pinned W0 ELF (`042D0CAD7591FF27B68212CB69016C39B24EE417A9A56F85E3DBB7CF89C2BC54`) and the sole cached, physically passed diagnostic producer at cache `65327e3004ee0e016a6394a1`, core `0_2`, ELF SHA-256 `2E07714FB487F689F8FA7B070DD8B8B8BA184060CDD41B0727D92E2A19E99656`. The probe's pair helper was inlined, so the complete `dr2d_kpke_keygen_terminal_probe` entry (`0x210-0xd10`) was inspected.

The probe source fixes the representation unambiguously:

```
word = (a & 0xffffu) | ((b & 0xffffu) << 16)
::new (out + 4 * pair) uint32_t(word)
```

The inlined probe implements that representation with aligned full-word stores in each polynomial region. The visible commit loops are at `0x950-0x960`, `0x9f0-0xa46`, `0xad0-0xae0`, and `0xca0-0xd0c`; their commit instructions at `0x960`, `0xa00`/`0xa46`, `0xae0`, and `0xcb0`/`0xd0c` are unsuffixed `st`. The first and third loops are compact ZOL schedules whose commit is the ZOL end; the second and fourth are software-pipelined schedules with full-word body and epilogue commits. No subword coefficient store occurs. This exact diagnostic producer physically emitted the accepted 1,588-byte terminal record, so its lane representation, aligned placement-new lowering, ZOL end behavior, and pipelined full-word commits are established on Phoenix.

W0 uses the same representation, but its inputs are already-computed `uint32_t coefficients[256]` rather than probe arithmetic:

- `0x1712 lda.u16 [p0+0]` obtains coefficient 0's low 16 bits;
- `0x171c lda [p0+4]` obtains coefficient 1 as its full local `uint32_t` lane;
- `0x172c lda.u16 [p0+8]` and `0x1732 lda [p0+12]` preload coefficients 2 and 3;
- `0x1744` shifts coefficient 1 left by 16 and `0x1748` ORs it with coefficient 0;
- each later iteration repeats the same even-low/odd-shifted mapping. The mixed `lda.u16`/`lda` sequence is therefore intentional: local coefficient lanes are 4 bytes apart, and only the low 16 bits of the even lane need be loaded before OR. The odd full-width load is harmless because the subsequent left shift discards bits above bit 15.

The W0 ZOL setup preserves the previously proved count. `r0=0x80` is consumed by `add.nc lc,r0,#-2` in the same bundle that installs the later `r0=2`; the loop body at `0x1750-0x1790` commits 126 words at `0x1764`, and the software-pipeline epilogue commits the two pending words at `0x17b2` and `0x17b8`. Destination modifiers advance by four bytes, giving exactly 128 consecutive words (512 bytes), with no duplicate, gap, scalar tail, `st.s8`, or `st.s16`.

The probe and W0 are not instruction-identical because the probe synthesizes deterministic values while W0 loads NTT results. They are semantically identical at the relevant boundary: low coefficient in bits 0-15, high coefficient in bits 16-31, consecutive four-byte destinations, and only full-word commits. **No instruction-level pair-lane, load-width, shift, OR, ZOL, epilogue, or destination-progression defect is proved. W0 post-NTT pair packing is ruled out.**

The strongest remaining static split is now:

1. W0 `derive_g` construction/extraction of sigma before the already-cleared PRF/CBD/NTT/pack path; versus
2. full-word persistence of W0's `s0/s1` through the production `copy_words` paths.

The next action is one read-only capture of the W0 derive/extraction window plus the exact `copy_words` symbols from all four downstream workers:

```powershell
& {
  $objdump = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin\llvm-objdump.exe"
  $cache = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6"
  $w0 = "$cache\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $internal = ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_internal.hpp"
  $out = ".\PQC_DR2D_derive_sigma_and_copy_words_20260818.txt"
  $cores = @("0_3","0_4","0_5","1_2")
  $copyRegex = "copy_words.*\s*$"

  & {
    "W0_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0).Hash)"
    "INTERNAL_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $internal).Hash)"
    "===== SOURCE derive_g AND copy_words ====="
    $src = Get-Content -LiteralPath $internal
    139..148 | ForEach-Object { "{0}: {1}" -f $_,$src[$_ - 1] }
    181..191 | ForEach-Object { "{0}: {1}" -f $_,$src[$_ - 1] }

    "===== W0 derive_g / rho-sigma extraction target window ====="
    & $objdump -d --triple=aie2 --disassemble-zeroes `
      --start-address=0x7e0 --stop-address=0xa50 $w0
    if ($LASTEXITCODE -ne 0) { throw "W0 derive_g disassembly failed." }

    foreach ($core in $cores) {
      $elf = "$cache\elfs_main_core_$core\elfs_main_core_$core.elf"
      $symbols = @(& $objdump -t $elf)
      if ($LASTEXITCODE -ne 0) { throw "Symbol read failed for core $core" }
      $copyLine = $symbols |
        Where-Object { [regex]::IsMatch([string]$_, $copyRegex) } |
        Select-Object -First 1
      "===== CORE $core ====="
      "ELF=$elf"
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash)"
      if ($null -eq $copyLine) {
        "COPY_WORDS_SYMBOL_NOT_FOUND"
        continue
      }
      $parts = @(([string]$copyLine).Trim() -split "\s+")
      if ($parts.Count -lt 6) { throw "Unexpected copy_words symbol format: $copyLine" }
      $start = [Convert]::ToUInt32($parts[0],16)
      $size = [Convert]::ToUInt32($parts[4],16)
      if ($size -eq 0) { throw "copy_words symbol has zero size: $copyLine" }
      $stop = $start + $size
      "COPY_SYMBOL=$copyLine"
      "COPY_RANGE=0x$($start.ToString('x'))-0x$($stop.ToString('x'))"
      & $objdump -d --triple=aie2 --disassemble-zeroes `
        --start-address=$start --stop-address=$stop $elf
      if ($LASTEXITCODE -ne 0) { throw "copy_words disassembly failed for core $core" }
    }
  } | Tee-Object -FilePath $out
}
```

### W0 derive/extraction and downstream copy audit — both static paths ruled out

The new capture matches the pinned W0 and internal-header hashes. Combined with the earlier complete W0 entry capture, it closes the pointer identities that are not independently visible from `0x7e0` alone.

**W0 stack and pointer provenance.**

- At worker entry, `p7=sp-352` is the aligned 200-byte Keccak state.
- `p6=sp-92` is the 32-byte rho destination, and `p3=sp-60` is the immediately following, non-overlapping 32-byte sigma destination.
- The ranges are exact and adjacent: state `sp-352..sp-153`, saved-pointer area beginning at `sp-152`, rho `sp-92..sp-61`, and sigma `sp-60..sp-29`.
- On the aligned normal path, `0x6ae` saves `p3` at `sp-148`. The `0x9a0` restore therefore makes `p0` the sigma destination, not the token or rho pointer.
- `p6` remains the rho destination across the Keccak call. `p7` remains the state base.

**G absorb and extraction.**

- `0x7e0-0x870` clears exactly 200 state bytes through `p7`.
- The 32-byte input absorb at `0x8c0-0x930` uses the previously proved AIE2 software-pipeline schedule. The fixed updates target state offsets 32, 33, and 71, corresponding to `K=2`, SHA3 suffix `0x06`, and the final `0x80` bit for the 72-byte SHA3-512 rate.
- `0x98e` calls the already-proved Keccak implementation with `p7` as state.
- Extraction programs 32 iterations. For each old index $i=0..31$, `0x9f0` loads `state[i]`, `0xa00` stores it to `p6[i]` (rho), `0xa20-0xa2c` forms and loads `state[32+i]`, and the ZOL-end store at `0xa30` writes it to `p0[i]` (sigma). `dj0` remains the old $i$ for both destination stores while `dj1=i+32` addresses the second state half.
- There is no swapped destination, state+31/state+33 error, missing byte, extra iteration, or alias overlap.

The one-case physical localizer proved rho is exactly canonical. Since the same deterministic Keccak state supplies both halves, and the second half is now statically proved to copy `state[32..63]` to the correct non-overlapping sigma buffer, no W0 `derive_g` construction or sigma-extraction defect is proved. Together with the earlier physically anchored Keccak comparison, **derive_g/sigma extraction is ruled out as a static root cause**.

**W1/W3 fixed 2,048-byte copy variant.**

- Cores `0_3` and `0_5` are instruction-identical at `0xc70-0xd90`.
- The destination and source low-bit guards precede every store.
- The taken aligned destination branch executes the scheduled `r4=0` initialization before reaching the source check; the helper does not inherit a caller offset.
- Four `lda.u8` operations reconstruct each source word as `b0 | b1<<8 | b2<<16 | b3<<24`, matching `load_le32` and the ELF's proved little-endian encoding.
- Old `r5=0x200` programs `lc=511`; the body makes 511 full `st` commits at `0xd38`, and `0xd8a` commits the single pending epilogue word. Source and destination offsets advance by four.
- Result: exactly 512 words/2,048 bytes, preserving every byte in order.

**W2/W4 length-parametric copy variant.**

- Cores `0_4` and `1_2` are instruction-identical at `0xe40-0xf60`.
- `0xe4a` checks `bytes&3`; the taken aligned branch's delay schedule initializes `r0=0` at `0xe5c` before `0xe70`. Thus the byte offset does not inherit the preceding rho loop's live `r0`.
- `0xe70-0xe98` checks destination and source alignment before the copy ZOL.
- `0xeb8-0xed0` computes the exact word count from bytes and programs the ZOL. The earlier caller evidence fixes the invocations to 1,024/512/512 bytes in W2 and 1,024/512/512 bytes in W4, hence 256/128/128 words.
- `0xf0c-0xf38` reconstructs each little-endian word from four unsigned bytes. `0xf40` is the only copy commit: full `st`, followed by offset `+4`.
- The loop executes the computed number of words and then returns true at `0xf5c`; misaligned size/pointers return false before any commit.

Together with the already proved absolute callers, spans, worker guards, and short-circuit routing, **downstream `copy_words` persistence is ruled out**. The helpers perform representation-preserving copies; they do not alter coefficient values, lane order, or byte order.

No new instruction-level defect is proved. Static evidence now rules out every identified W0 mathematical/dataflow component—G construction/extraction, Keccak, SHAKE staging, CBD3, NTT, pair packing—and the complete downstream persistence route. This does not convert the physical result: the canonical silicon run remains a conclusive production FAIL. It means the remaining fault is an integrated target-runtime effect not distinguishable from the retained static code and two saved first coefficients.

The next safe step is to inventory the exact W0 compiler invocation and any retained LLVM/Machine-IR/assembly intermediates so the failing ELF can be replayed offline with pass-by-pass diagnostics without changing production sources:

```powershell
& {
  $cache = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6"
  $w0 = "$cache\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $needle = "dr2d_mlkem512_kpke_keygen_seed|elfs_main_core_0_2|core_0_2"
  $out = ".\PQC_DR2D_W0_compile_invocation_and_intermediates_20260818.txt"
  $textNames = @("compile_commands.json","build.ninja","rules.ninja")
  $textExt = @(".txt",".log",".cmd",".rsp",".json",".ninja",".yaml",".yml")
  $irExt = @(".ll",".bc",".mir",".s",".S",".o")

  & {
    "CACHE=$cache"
    "W0_ELF_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $w0).Hash)"
    "===== CANDIDATE BUILD/IR FILE INVENTORY ====="
    $files = @(
      Get-ChildItem -LiteralPath $cache -Recurse -File -ErrorAction SilentlyContinue
    ) | Sort-Object FullName -Unique

    foreach ($f in $files) {
      if ($textNames -contains $f.Name -or $textExt -contains $f.Extension -or
          $irExt -contains $f.Extension) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash
        "FILE=$($f.FullName) SIZE=$($f.Length) SHA256=$hash"
      }
    }

    "===== MATCHED COMPILER/BUILD LINES ====="
    foreach ($f in $files) {
      if ($textNames -contains $f.Name -or $textExt -contains $f.Extension) {
        try {
          Select-String -LiteralPath $f.FullName -Pattern $needle -CaseSensitive:$false |
            ForEach-Object { "$($f.FullName):$($_.LineNumber):$($_.Line)" }
        } catch {
          "READ_ERROR=$($f.FullName):$($_.Exception.Message)"
        }
      }
    }
  } | Tee-Object -FilePath $out
}
```

### Retained compiler artifacts — offline IR audit is now possible

The cache inventory is complete enough to move from disassembly-only reasoning to the retained compiler pipeline without rebuilding or modifying production sources.

- The pinned W0 ELF remains SHA-256 `042D0CAD7591FF27B68212CB69016C39B24EE417A9A56F85E3DBB7CF89C2BC54`.
- The retained W0 kernel object is `dr2d_kpke_keygen_seed_noise.o`, 12,828 bytes, SHA-256 `7EA27CC5F6BB905253A161ACD98988C62AFC54855BCFD1C4530A55C441E28B70`.
- The retained per-core wrapper/object is `objects_main_core_0_2.o`, 1,412 bytes, SHA-256 `DC58F2B1A79B5F71C8983CC8EDA6F58FA8C9047B07D76E4048EEB8856A9E8D83`.
- `opted_main_core_0_2.ll` is present, 3,516 bytes, SHA-256 `F17F0A6012867C163FBAE5BDFA6E6C9A9686781F73796E19065F4342F7ABA998`.
- `peano-compat_main_core_0_2.ll` and `peano-linked_main_core_0_2.ll` are both 6,806 bytes and byte-identical at SHA-256 `EC419DFBEB3B9666DA3F23AC3D241BEDE6B966D8BC6607D1D0AC47EF93FBF188`. This proves the compatibility-to-linked stage did not alter the retained textual IR.
- `deps.json` is complete metadata (`"complete": true`), 20,601 bytes, SHA-256 `44553C157965681D141B93FA1F26651C88AFF9DC0FC587462B68F725EEE684DE`. The captured display line is truncated by presentation, not by the file; its visible prefix already matches the pinned V2 worker/internal/serializer hashes.
- `kernels_main.json`, `partition_main.json`, and `memTopology_main.json` are retained with hashes `464FC9FE...AB86`, `AB61611D...8D04`, and `638D0D28...BBC6`, respectively.

This discovery does not itself prove or refute a compiler-pass defect because none of the IR bodies or complete dependency metadata was captured. It does establish a fresh, read-only route to inspect:

1. whether the W0 worker call graph and buffer address spaces survive into optimized IR;
2. whether placement-new coefficient commits remain typed/aligned stores before Peano lowering;
3. whether rho/sigma extraction, helper counter arguments, and zeroization are still represented correctly;
4. whether the Peano compatibility stage introduces address-space casts, lifetime changes, or other target-specific transformations before object emission; and
5. whether the exact object and IR inputs correspond to the pinned source manifest.

The next action captures every retained W0 textual IR file verbatim, the complete dependency/kernel metadata, and read-only object headers/sections/symbols:

```powershell
& {
  $cache = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6"
  $bin = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin"
  $objdump = "$bin\llvm-objdump.exe"
  $readobj = "$bin\llvm-readobj.exe"
  $out = ".\PQC_DR2D_W0_complete_IR_metadata_objects_20260818.txt"
  $rawFiles = @(
    "opted_main_core_0_2.ll",
    "peano-compat_main_core_0_2.ll",
    "peano-linked_main_core_0_2.ll",
    "deps.json",
    "kernels_main.json",
    "partition_main.json",
    "memTopology_main.json"
  )
  $objects = @(
    "dr2d_kpke_keygen_seed_noise.o",
    "objects_main_core_0_2\objects_main_core_0_2.o"
  )

  & {
    "CACHE=$cache"
    foreach ($name in $rawFiles) {
      $path = Join-Path $cache $name
      if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing retained artifact: $path"
      }
      $item = Get-Item -LiteralPath $path
      "===== RAW FILE BEGIN: $name ====="
      "PATH=$path"
      "SIZE=$($item.Length)"
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash)"
      Get-Content -LiteralPath $path -Raw
      "===== RAW FILE END: $name ====="
    }

    "===== DEPS PARSED INPUTS ====="
    $depsPath = Join-Path $cache "deps.json"
    $deps = Get-Content -LiteralPath $depsPath -Raw | ConvertFrom-Json
    "VERSION=$($deps.version) COMPLETE=$($deps.complete) INPUT_COUNT=$($deps.inputs.Count)"
    foreach ($input in $deps.inputs) {
      "INPUT path=$($input.path) size=$($input.size) mtime=$($input.mtime) sha256=$($input.sha256)"
    }

    foreach ($name in $objects) {
      $path = Join-Path $cache $name
      if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing retained object: $path"
      }
      "===== OBJECT BEGIN: $name ====="
      "PATH=$path"
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash)"
      "----- FILE/SECTION/SYMBOL DETAIL -----"
      & $readobj --file-headers --sections --symbols $path
      if ($LASTEXITCODE -ne 0) { throw "llvm-readobj failed for $path" }
      "----- OBJDUMP SYMBOL TABLE -----"
      & $objdump -t $path
      if ($LASTEXITCODE -ne 0) { throw "llvm-objdump failed for $path" }
      "===== OBJECT END: $name ====="
    }
  } | Tee-Object -FilePath $out
}
```

### Wrapper IR, FIFO scheduling, metadata, and object-linkage audit

The retained `.ll` files are wrapper/core-scheduling IR, not the C++ kernel implementation IR. `dr2d_kpke_keygen_seed_noise` remains an external three-pointer declaration and is supplied by the separately retained kernel object. Consequently, these IR files cannot expose the already-audited G/CBD/NTT/store implementation, but they conclusively expose the wrapper ABI and object-FIFO discipline.

**Wrapper pointer order and sizes.**

- The wrapper declares exactly two 32-byte D buffers, two 16-byte descriptor buffers, and two 2,096-byte secret-token buffers.
- The only kernel call is `dr2d_kpke_keygen_seed_noise(ptr D, ptr descriptor, ptr secret_token)` in that exact order. This matches the C entry ABI and the physical runner's ingress ordering.
- The selected pointers are element-zero pointers into the correctly sized globals; there is no GEP offset, cast, lane offset, or source/output swap.
- No matrix, row-state, final-token, or result pointer is passed to W0. Their declarations in the pre-optimized whole-program Peano module are unused by `core_0_2` and are removed from the optimized core-specific module.

**Acquire/release and double buffering.**

- D uses acquire lock 49 and release lock 48.
- Descriptor uses acquire lock 51 and release lock 50.
- Secret output uses acquire lock 52 and release lock 53.
- Each acquire dominates pointer selection and the kernel call. The output is released immediately after the call; both inputs are released afterward. No buffer is released before its final kernel use.
- `_anonymous0[0..2]` holds independent D/descriptor/output buffer indices. All initialize to zero, select only buffer 0 or 1, and toggle exactly once after each completed call.
- The pre-optimized occupancy PHIs decrement after the matching release. The optimized module folds the steady-state acquires to count `-1` while preserving the same lock IDs, selections, releases, and toggles.
- Because all three indices start at zero and advance once per completed call, D and descriptor cannot drift relative to each other in normal execution. There is no extra acquire, skipped release, reversed toggle, or stale output selection in the IR.

This wrapper could not selectively preserve canonical rho while replacing all four polynomial regions: it passes one coherent output buffer to W0, and W0 writes rho and all polynomial regions through that same pointer. The valid status, CRC, rho, and canonical record observed physically further reject a stale or cross-buffer record as the primary explanation.

**Metadata.**

- `deps.json` parses successfully as version 1, `complete=True`, with 81 inputs. The pinned worker, internal header, Keccak header, and serializer hashes match the accepted V2 manifest.
- `kernels_main.json` describes the generic MLIR_AIE DPU launch ABI and host BO slots; it does not add private W0 host transfers or reinterpret W0's three internal FIFO pointers.
- `partition_main.json` maps one four-column partition starting at column zero and the expected DPU kernel ID `0x901`.
- `memTopology_main.json` contains generic HOST/SRAM BO metadata already classified in the topology audit. It does not describe private object-FIFO payload movement and contains no W0-specific anomaly.

**Object linkage.**

- The kernel object is AIE2 little-endian relocatable ELF and globally defines `dr2d_kpke_keygen_seed_noise`, size `0xf30`.
- Its local sections separately contain the helper (`0x870`), Keccak (`0x7f0`), NTT (`0x1d0`), and 256-byte zeta table. The only unresolved arithmetic symbol is the expected compiler runtime `__umodsi3`.
- The wrapper object is AIE2 little-endian relocatable ELF and globally defines `core_0_2`, size `0x1f0`. Its expected unresolved symbols are the six double-buffer globals, `_anonymous0`, and `dr2d_kpke_keygen_seed_noise`.
- The final ELF's previously audited layout maps the kernel sections consecutively and exactly: main `0x210-0x1140` (`0xf30`), helper `0x1140-0x19b0` (`0x870`), Keccak `0x19b0-0x21a0` (`0x7f0`), and NTT `0x21a0-0x2370` (`0x1d0`). These exact size correspondences strongly establish that the retained kernel object, not an unrelated implementation, supplied the final code.

No buffer acquire/release, wrapper ABI, double-buffer index, metadata, or symbol-definition defect is proved. The one remaining linkage-level check is to capture every object relocation and the final core's linker/map resolution, especially the wrapper call, six FIFO globals, zeta reference, Keccak/helper/NTT calls, and `__umodsi3`.

```powershell
& {
  $cache = "`$HOME`\.npu\cache\04f147d54cb01d160974a6e6"
  $bin = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin"
  $readobj = "$bin\llvm-readobj.exe"
  $objdump = "$bin\llvm-objdump.exe"
  $wrapper = "$cache\objects_main_core_0_2\objects_main_core_0_2.o"
  $kernel = "$cache\dr2d_kpke_keygen_seed_noise.o"
  $elf = "$cache\elfs_main_core_0_2\elfs_main_core_0_2.elf"
  $out = ".\PQC_DR2D_W0_relocations_and_final_link_20260818.txt"

  & {
    foreach ($item in @($wrapper,$kernel,$elf)) {
      if (-not (Test-Path -LiteralPath $item -PathType Leaf)) {
        throw "Missing link input: $item"
      }
      "===== FILE BEGIN: $item ====="
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $item).Hash)"
      "----- HEADERS / SECTIONS / SYMBOLS / RELOCATIONS -----"
      & $readobj --file-headers --sections --symbols --relocations $item
      if ($LASTEXITCODE -ne 0) { throw "llvm-readobj failed for $item" }
      "----- DISASSEMBLY WITH RELOCATIONS -----"
      & $objdump -dr --triple=aie2 --disassemble-zeroes $item
      if ($LASTEXITCODE -ne 0) { throw "llvm-objdump failed for $item" }
      "===== FILE END: $item ====="
    }

    "===== FINAL CORE SYMBOL WINDOWS ====="
    $symbols = @(& $objdump -t $elf)
    foreach ($pattern in @(
      "core_0_2$",
      "dr2d_kpke_keygen_seed_noise$",
      "cbd3_ntt_store_dr2b.*$",
      "keccak_f1600.*$",
      "nttEPj$",
      "kZetasE$",
      "__umodsi3$"
    )) {
      $symbols | Where-Object { [regex]::IsMatch([string]$_,$pattern) }
    }

    "===== RETAINED LINKER/MAP CANDIDATES ====="
    $candidates = Get-ChildItem -LiteralPath $cache -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Extension -in @(".map",".ld",".lds") -or
        $_.Name -match "link|core_0_2"
      } | Sort-Object FullName -Unique
    foreach ($candidate in $candidates) {
      "CANDIDATE=$($candidate.FullName) SIZE=$($candidate.Length) SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate.FullName).Hash)"
      if ($candidate.Extension -in @(".map",".ld",".lds") -or
          $candidate.Extension -in @(".txt",".log",".json")) {
        "----- RAW BEGIN: $($candidate.FullName) -----"
        Get-Content -LiteralPath $candidate.FullName -Raw
        "----- RAW END: $($candidate.FullName) -----"
      }
    }
  } | Tee-Object -FilePath $out
}
```

### Final relocation and object-to-ELF identity audit — link stage clean

The relocation capture closes the final static linkage question. The final ELF contains no residual relocations, and every input relocation resolves to the expected local label, implementation function, runtime helper, table, or placed object-FIFO symbol.

**Wrapper resolutions.**

- `R_AIE_44` references resolve D buffer 0/1 to `0x78000/0x7c000`, descriptor buffer 0/1 to `0x71840/0x74840`, secret-token buffer 0/1 to `0x71000/0x74000`, and `_anonymous0` to `0x78020`.
- The wrapper call relocation resolves `dr2d_kpke_keygen_seed_noise` to `0x210`.
- The wrapper back-edge relocation resolves to final `.LBB0_1@0xa0`.
- Final `core_0_2` begins at `0x20`; therefore every wrapper instruction is the retained wrapper-object instruction at object offset plus `0x20`, except for the immediate bits changed by those nine relocations.
- The final call delay schedule selects D into `p0`, descriptor into `p1`, and secret output into `p2` before control arrives at `0x210`, exactly matching the entry ABI.

**Kernel resolutions.**

- Main W0's Keccak relocation resolves to `0x19b0`.
- All four main-to-helper relocations resolve to the single `cbd3_ntt_store_dr2b@0x1140`.
- The helper's two Keccak calls resolve to `0x19b0`; its NTT call resolves to `0x21a0`.
- The NTT zeta relocation resolves to the 256-byte table at `0x7c020`.
- Both required modulo-helper references resolve to the single linked `__umodsi3@0x2370`, size `0x90`.
- Every local ZOL start/end, branch, epilogue, and loop-back relocation resolves to the corresponding final local symbol at the input-section offset plus its final section base.
- Final symbol sizes exactly equal the input sections: main `0xf30`, helper `0x870`, Keccak `0x7f0`, NTT `0x1d0`, zetas `0x100`, wrapper `0x1f0`.

**Exact instruction-byte comparison.**

An address-normalized comparison of every retained wrapper/kernel instruction against the final ELF produced:

| Input section | Instructions | Byte-identical | Differ only at declared relocation | Missing | Unexpected differences |
|---|---:|---:|---:|---:|---:|
| wrapper `core_0_2` | 135 | 126 | 9 | 0 | 0 |
| W0 main | 743 | 688 | 55 | 0 | 0 |
| CBD3/NTT/store helper | 306 | 284 | 22 | 0 | 0 |
| Keccak | 330 | 323 | 7 | 0 | 0 |
| NTT | 116 | 111 | 5 | 0 | 0 |
| **Total** | **1,630** | **1,532** | **98** | **0** | **0** |

Thus every final instruction either remains byte-for-byte identical to the retained input object or differs only in an instruction containing a declared relocation. There is no linker relaxation, section rewrite, unexpected binding, substituted function, missing instruction, reordered section, or unexplained byte modification.

**Static-analysis conclusion.**

The link stage is clean. The accumulated evidence now closes source scope, C++ object lifetime/aliasing, widths and tails, all W0 algorithms and persistence paths, wrapper ABI/FIFO scheduling, memory placement, object provenance, relocation resolution, and final instruction identity. Static analysis of the available production artifacts is exhausted: no evidence supports a production source patch, and changing arithmetic/store code now would be speculative.

### Safest next action — prepare a test-only W0 token tap; do not run it yet

The only justified next action is a narrowly scoped diagnostic artifact that observes the earliest complete semantic boundary without modifying production sources or the canonical runner:

1. Add a **test-only** graph and host harness that invoke the unchanged `dr2d_kpke_keygen_seed_noise` with the normal 32-byte D and 16-byte descriptor ingress, but route its complete 2,096-byte secret token directly to a diagnostic host egress.
2. Prefer linking the exact retained kernel object SHA-256 `7EA27CC5F6BB905253A161ACD98988C62AFC54855BCFD1C4530A55C441E28B70`; if the toolchain requires recompilation, require the implementation-section instruction comparison to match this object modulo declared relocations before any run.
3. Keep all production kernels, production graph, serializer, ABI, canonical runner, xclbin, and existing cache artifacts byte-identical. Record pre/post hashes.
4. Compile only. Before any hardware authorization, require:
   - exact diagnostic ABI: D 32 + descriptor 16 in, secret token 2,096 out;
   - one W0 call and no downstream worker/serializer/reference call;
   - exact W0 object provenance and clean relocations;
   - unchanged W0 stack/program/data limits;
   - fail-closed header and canonical-polynomial validation in the additive harness;
   - output file hashing and no silent fallback.
5. Return the compile-only graph/ELF/store/relocation evidence for independent review.
6. **No native call is authorized now.** Only after those compile-only gates pass may a separate decision authorize exactly one tcId-01 diagnostic call. That call would retain the full raw 2,096-byte W0 token and report rho plus all four polynomial regions independently. It would conclusively distinguish wrong W0 generation from downstream corruption without another 25-case run.

This proposal is diagnostic, not a production fix. Packaging and push remain prohibited regardless of its future result.

### W0 token-tap artifact prepared — compile-only review pending

The recommended additive diagnostic has now been designed and packaged without modifying the user repository and without any IRON dispatch:

- unified patch: `PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_20260818.patch`;
- patch SHA-256: `0fc227a8deaed9b45b4daf39fae0e9e966886b549666ffd87f3c142818f61f5c`;
- handoff: `PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_20260818_HANDOFF.md`;
- scope: exactly three new diagnostic-only files, 567 insertions, zero production modifications or deletions.

The graph has one worker, two normal ingress records (D 32 and descriptor 16), and one direct 2,096-byte W0 secret-token egress. It declares only the unchanged production `dr2d_kpke_keygen_seed_noise` external function with the original pointer order and `0x1000` stack reservation. There is no W1-W4, serializer, terminal-result path, reference implementation, fallback, or canonical-runner integration.

The host layer validates the full W0 layout and every canonical uint16 coefficient, rejects an unwritten `0xA5` sentinel, requires fixed-zero error records, zeroizes staging, and hashes the complete token plus header/rho/s0/s1/e0/e1 regions without computing reference crypto.

Before IRON loading and after any future dispatch it fail-closes on the exact W0 source, internal header, production graph, production ABI, canonical runner, and retained W0 object hashes. The retained comparison object must remain SHA-256 `7EA27CC5F6BB905253A161ACD98988C62AFC54855BCFD1C4530A55C441E28B70`. The serializer is not imported, compiled, linked, or invoked. The pinned `ExternalFunction` API exposes source compilation rather than a reviewed direct-object argument, so the handoff correctly requires the newly built diagnostic implementation sections to match that object instruction-for-instruction modulo declared relocations.

Host-only validation in isolated copies passed `git apply --check`, `py_compile`, `ruff check`, `ruff format --check`, and six diagnostic contracts. The future entrypoint refused without the explicit post-review authorization variable, returned exit code 3, and created no output.

The handoff contains the complete compile-only provenance, graph/FIFO, object/ELF identity, relocation, store, memory, and fail-closed checklist. It explicitly prohibits using the JIT entrypoint to populate a cache because that could dispatch after compilation; the already-established non-executing IRON/aiecc cache-build procedure must be used and its exact command recorded.

**No native execution is authorized.** The next gate is independent review of the patch followed by a non-executing compile-only build and inspection. Only a later separate decision may authorize one tcId-01 tap call.

### Applied token-tap host validation — PASS; exact compile-only API identified

The applied-patch evidence confirms:

- patch SHA-256 `0FC227A8DEAED9B45B4DAF39FAE0E9E966886B549666FFD87F3C142818F61F5C`;
- exactly three added diagnostic files and 567 insertions;
- `py_compile`, `ruff check`, `ruff format --check`, and all six host contracts pass;
- pinned W0 source, internal header, production graph, production ABI, canonical runner, and retained W0 object hashes are exact;
- the unauthorized entrypoint refuses with exit code 3 and creates no output;
- the additional dirty-tree entries and `.gitignore` modification predate this patch; the patch itself adds only its three files.

The pinned IRON v1.4.1 `@iron.jit` decorator returns a `CallableDesign`. Its public `specialize(...).compile()` method is explicitly the eager/ahead-of-time path: it calls `CompilableDesign.compile()` to populate the filesystem cache and returns the xclbin/instruction paths without constructing or calling `NPUKernel`. NPU execution occurs only in `CallableDesign.__call__`, which this gate must never invoke.

The next command therefore:

1. removes and rejects the native-authorization environment variable;
2. runs the full production/retained-object hash gate before graph construction;
3. obtains the token-tap `CallableDesign`, specializes only its four compile-time parameters, and inspects the installed `compile()` implementations;
4. fails if either compile method references `NPUKernel`, `DefaultNPURuntime`, or `pyxrt`, or if `CallableDesign.compile` does not delegate to `self.compilable.compile`;
5. calls only `specialized.compile()`;
6. records the literal compile expression, temporary script hash, returned artifacts, exact cache path, PDI paths, all cache-file hashes, generated metadata/MLIR, and object/ELF headers, relocations, symbols, and disassembly;
7. repeats the pinned hash gate after compilation;
8. rejects the production cache path and any missing xclbin/instruction/cache artifact.

This is compile-only authorization, not native authorization. No XRT tensor is created, no callable design is invoked, no authorization variable is set, and no runner is launched.

## 9. Exact stop/pass criteria for the follow-up

The compile-only audit remains PASS, but the production physical gate is FAIL. The retained log and one-case localizer conclusively classify a systematic full-polynomial cryptographic mismatch beginning no later than W0 secret generation. The single tcId-01 hardware allowance has been consumed. Any further native call, 25-case repeat, source/hash change, reference substitution, runner edit, push, or package is prohibited. Continue only with static/offline evidence.

## 10. Final result

**COMPILE-ONLY PASS / PRODUCTION PHYSICAL FAIL / LINK STAGE CLEAN / STATIC ANALYSIS EXHAUSTED / W0 TAP PATCH PREPARED / NOT SAFE TO PUSH OR PACKAGE.** Across 1,630 wrapper/kernel instructions, 1,532 are byte-identical and the remaining 98 differ only at declared relocation sites; every binding resolves correctly. There is no evidence-based production patch. The additive three-file W0 token-tap patch is prepared and host-validated, but still requires independent review and non-executing compile-only evidence. No native call is currently authorized.
