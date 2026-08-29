# PQC DR2d Design: Partitioned Device-Resident ML-KEM-512 K-PKE.KeyGen

**Status:** **PHYSICALLY VALIDATED ON PHOENIX NPU SILICON (25/25 ACVP PASS).** DR2d
is one complete device-resident FIPS 203 ML-KEM-512 `K-PKE.KeyGen` operation, not full
approved ML-KEM `KeyGen`, encapsulation, or decapsulation. See `docs/PQC_DR2D_SILICON_VALIDATION_20260828.md`.

## Public boundary (unchanged)

The public operation accepts exactly two host fills: raw `d[32]` and one
16-byte descriptor. The descriptor fixes ABI v1, opcode `0x24`, ML-KEM-512
parameter `0x52`, `k=2`, `eta1=3`, SampleNTT cap five, and a u32 request ID.
It has no seed, key, or host-computed cryptographic intermediate. There is one
terminal 1,588-byte drain and one result CPU transfer. Its unchanged wire ABI
is a 20-byte little-endian header followed by `ekPKE[800] || dkPKE[768]`:

```
magic || request_id || status || ek_bytes || dk_bytes || CRC32(payload)
```

`ekPKE` is `ByteEncode12(t_hat[0]) || ByteEncode12(t_hat[1]) || rho`; `dkPKE`
is `ByteEncode12(s_hat[0]) || ByteEncode12(s_hat[1])`. Successful records are
committed by the final magic store. Errors have zero lengths, checksum, and
1,568-byte payload. The host checks magic, request, status, CRC, all packed
canonical lanes, and rejects all-zero successful payloads.

## Memory-fit six-worker topology

The previous monolithic derive worker is not referenced by the production
graph. The graph has six independently compiled workers and five internal-only
ObjectFIFOs; each worker consumes exactly one record and produces exactly one
record. No private FIFO has a shim endpoint, host allocation, fill, drain, or
CPU transfer.

```
d[32] + descriptor[16]
       │
       ▼
W0 seed_noise ─ secret(2,096) ─► W1 row0_expand ─ row0_matrix(3,120) ─►
W2 row0_accumulate ─ row_state(2,096) ─► W3 row1_expand ─ row1_matrix(3,120) ─►
W4 row1_accumulate ─ final(2,112) ─► W5 serialize ─► result(1,588)
```

| Worker | Independently compiled operation | IRON stack reservation | host g++ stack-use* | host g++ `.text`* |
|---|---|---:|---:|---:|
| W0 | descriptor validation; `G(d || Encode(2,1))`; DR2b-compatible `s_hat[0..1]`, `e_hat[0..1]` noise/NTT | 4,096 B | 1,504 B | 2,953 B |
| W1 | row-0 `A[0,0]`, `A[0,1]` expansion | 2,048 B | 424 B | 2,242 B |
| W2 | row-0 MultiplyNTTs accumulation | 2,048 B | 160 B | 1,519 B |
| W3 | row-1 `A[1,0]`, `A[1,1]` expansion | 2,048 B | 424 B | 2,242 B |
| W4 | row-1 MultiplyNTTs accumulation/final token | 2,048 B | 160 B | 1,583 B |
| W5 | canonical serializer and terminal commit | 2,048 B | 48 B | 826 B |


*Measured locally with host `g++ -O2 -fstack-usage` and `size`; these are
only comparative host estimates, not Phoenix program-memory or stack evidence.
W0's local CBD3/NTT frame contains `uint32_t coefficients[256]` (1,024 B),
Keccak state (200 B), and PRF bytes (192 B); the measured 1,504 B includes
compiler frame overhead. W0 contains SHA3/SHAKE and NTT only; it does not
contain SampleNTT or MultiplyNTTs. W1/W3 contain
SHAKE128/SampleNTT only; W2/W4 contain CBD3/NTT and MultiplyNTTs only. This
scope split is the reason the former program-memory-overflow operation is not
reused.

Each FIFO carries one logical invocation record. The IRON default buffering
must remain at its conservative two-record allocation unless a physical build
reports otherwise; at that depth the largest adjacent payload pair is
`2 × (3,120 + 2,096) = 10,432 B`. Adding the largest declared worker stack
(4,096 B) remains below 16 KiB before toolchain/runtime bookkeeping. Actual
FIFO placement, data-memory accounting, and program-memory sizes remain
physical-build acceptance evidence, not host claims.

| Private FIFO | Bytes | Fixed layout after header | Producer → consumer |
|---|---:|---|---|
| `dr2d_secret_token` | 2,096 | 16-byte `{request,status,reserved}`; `rho[32]`; `s_hat[2]`; `e_hat[2]` | W0 → W1 |
| `dr2d_row0_matrix` | 3,120 | header; `rho`; `s_hat[2]`; `e_hat[0..1]`; `A[0,0]`; `A[0,1]` | W1 → W2 |
| `dr2d_row_state` | 2,096 | header; `rho`; `s_hat[2]`; `t_hat[0]`; `e_hat[1]` | W2 → W3 |
| `dr2d_row1_matrix` | 3,120 | header; `rho`; `s_hat[2]`; `t_hat[0]`; `e_hat[1]`; `A[1,0]`; `A[1,1]` | W3 → W4 |
| `dr2d_final_token` | 2,112 | 32-byte `{request,status,reserved}`; `rho`; `s_hat[2]`; `t_hat[2]` | W4 → W5 |

All NTT polynomial lanes in private tokens are fixed little-endian `uint16`
values and validated as `< 3329` at each consuming trust boundary. Headers
validate reserved zero bytes and status in `{OK, LIMIT_EXCEEDED,
BAD_DESCRIPTOR, BAD_TOKEN}`. A malformed header or lane becomes
`BAD_TOKEN`; valid non-OK statuses and request IDs propagate unchanged. Every
producer clears its full output before header construction, and every consumer
clears its input token on success and reachable errors.

## Algorithm and implementation constraints

W0 derives `(rho, sigma) = G(d || Encode(k,1))`, then derives all four
CBD3/NTT polynomials with the physically validated DR2b formulation:
direct `bit_at` CBD3 into local `uint32_t coefficients[256]`, an
`__attribute__((noinline))` uint32 NTT, then canonical uint16 serialization
into the private token. The active W0 path does not perform an in-place NTT
over packed token lanes and does not use the prior fixed 24-bit mask path.
W1/W3 use bounded five-block SampleNTT. W2/W4 compute:

$$
\widehat{t}[i] = \sum_{j=0}^{1} \text{MultiplyNTTs}(\widehat{A}[i,j], \widehat{s}[j]) + \widehat{e}[i] \pmod{3329}
$$

The frozen 128-entry FIPS 203 zeta table is copied from physically validated
DR2c. No worker computes runtime bit-reversed indices or modular powers. The
static contract compares it byte-for-byte with DR2c and checks SHA-256
`ecc64560d6b8e28e2c3954ea934dfd35ad6ca41703bf713718ce94b3b1d2381b`.

### Full-word coefficient stores

Every normal-path coefficient store in the production partition writes a full
aligned 32-bit word. The installed Peano (llvm-aie 21.0.0 commit `c9c5ecb7`,
ancestral to upstream fix `f1baf5a` / PR #1221) drops the high half of a
sub-word store scheduled into a zero-overhead-loop end bundle, which was
confirmed by ELF inspection of the failing diagnostic producer and by the
physical PASS of the full-word diagnostic producer. Accordingly:

- `store_pair_word(out, pair, a, b)` commits one coefficient pair as
  `(a & 0xffff) | ((b & 0xffff) << 16)`;
- `copy_words(destination, source, bytes)` copies whole 32-bit words for bulk
  polynomial and polynomial-carry transfers between tokens;
- `store_le16` no longer exists in the DR2d internal header, so no DR2d
  coefficient loop can regress to a 16-bit coefficient store;
- W0 serializes 128 pair words, `sample_matrix_store` buffers the even accepted
  lane and commits 128 pair words, and `add_product_ntt` commits its four
  reduced lanes as two aligned words at byte offset `8*i`;
- each word begins a `uint32_t` object's lifetime with C++17 placement new in
  the token's `unsigned char` storage, never an assignment through a cast
  pointer, so no strict-aliasing or object-lifetime rule is violated; only byte
  reads of that representation, and volatile byte zeroization, act on it later;
- alignment is justified statically (`static_assert` on every polynomial offset
  and copy span) and dynamically (`word_aligned` on each token base), and a
  misaligned base fails closed with `BAD_TOKEN` and an all-zero record.

The repair is scoped to coefficient-bearing and polynomial-carry token regions
only. These byte stores are deliberately retained, because they are outside
coefficient storage and the diagnostic probe physically validated their shapes
on target:

- local Keccak/SHAKE `state[200]` absorption and domain padding, local `prf[192]`
  buffers, and local `rho`/`sigma` extraction in `derive_g`,
  `sample_matrix_store`, and `cbd3_ntt_store_dr2b`;
- the 32-byte token `rho` copies in W0 and in all four row workers, which were
  explicitly reverted from a full-word variant to keep the repair minimal;
- token and result header fields via `write_header` / `store_le32`;
- volatile zeroization via `clear_bytes`;
- the entire unchanged serializer translation unit, including `encode_poly12`
  packing, CRC32, and commit-magic-last.

Consequently the Phoenix ELF gate must classify each store by loop and
destination and reject sub-word stores only for coefficient/carry destinations.
A global "no `st.s8`/`st.s16`" grep is invalid for these workers; see
`PQC_DR2D_SILICON_VALIDATION_PENDING.md`.

No host SHA3/SHAKE, matrix expansion, noise sampling, NTT, multiplication,
serialization, reference fallback, intermediate transfer, or test dependency
exists in the production dispatch path. `run_all_silicon_tests.py` remains
unchanged and DR2d is not admitted to it by host evidence.

## Diagnostic-only terminal probe

`dr2d_mlkem512_kpke_keygen_terminal_probe_graph.py` is not part of the
production graph. It is a two-worker physical discriminator for case 1 only:
the producer accepts the same `d[32]` and descriptor fills, requires request ID
`0xD2D00001`, creates one 2,112-byte private final token with known canonical
lanes, and passes it directly to the unchanged production serializer. It
retains one 1,588-byte normal terminal record and one result CPU transfer.

The fixture uses only descriptor byte 8 (`seed = 1` for case 1):

$$
\begin{aligned}
t_0[i] &= 13i + \text{seed}, & t_1[i] &= 3328 - (13i + \text{seed}) \\
s_0[i] &= 11i + 3\text{seed}, & s_1[i] &= 3328 - (11i + 3\text{seed})
\end{aligned}
$$

All 1,024 lanes are canonical. The 32-byte `rho` is
`0xa5 ^ descriptor[8 + (i mod 4)] ^ i`. The test-only expected terminal bytes
are independently regenerated from that descriptor; no host KeyGen value is
used. The normal 1,588-byte record, including magic-last header and CRC32, is
pinned by SHA-256
`309c9dd65e843edb15bc67766aff8f37b302ef815a435813881d6908d567adb4`.
A Phoenix byte-exact record pass isolates this diagnostic artifact's
final-token FIFO and the existing `ByteEncode12` serializer path from upstream
W0/matrix/arithmetic. A failure keeps those terminal-path concerns open.
Neither outcome is a production DR2d KeyGen pass.

For the vulnerable Windows Peano diagnostic probe only, each two-coefficient
little-endian slot is initialized with C++17 placement construction of one
aligned `uint32_t`, after an explicit byte-address alignment check. It avoids
the earlier byte stores in coefficient loops without a typed-pointer assignment
to `uint8_t` storage. Subsequent serializer byte reads are permitted character
accesses to the constructed word representation. This source-level workaround
must still be confirmed as full-word target stores by physical ELF inspection.

## Host evidence and remaining physical requirement

The independent C++ harness compiles and invokes every six production kernels
with `g++ -Wall -Wextra -Werror -pedantic`. It links the whole private pipeline,
checks all 25 pinned NIST ACVP-Server FIPS 203 ML-KEM-512 KeyGen cases against
the independent test-only oracle. Before W1 consumes the secret token, the
harness also compares every `s_hat` and `e_hat` polynomial against the
independent DR2b SHAKE256/CBD3/NTT reference for counters 0 through 3. It tests
bad descriptor, every private FIFO reserved-byte/status corruption boundary,
fixed-zero terminal errors, and input/token zeroization. This is host evidence
only.

Before changing status, run:

```powershell
py .\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_keygen_silicon.py
```

The Phoenix record must include a 25/25 native pass plus a repeat in the same
process, artifact IDs/timestamps, worker program-memory reports, per-tile data
memory and FIFO-depth/placement reports, DMA routes, and confirmation of only
two shim MM2S channels and one terminal S2MM channel. It must distinguish
correctness evidence from remanence, side-channel, constant-time, performance,
CMVP, or certification claims.

## References

- NIST FIPS 203, Algorithms 4, 7, 8, 9, 12, and 13; Table 2; Appendix B.
  https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf
- NIST FIPS 202, SHA3-512, SHAKE128, SHAKE256, and Keccak-f[1600].
  https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- NIST ACVP-Server ML-KEM KeyGen FIPS 203 vectors, commit
  `975de31eb83d87039ec88934fdc47d8c312b892d`.
  https://github.com/usnistgov/ACVP-Server/tree/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-KEM-keyGen-FIPS203
