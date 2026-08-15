# Milestone 32: FIPS 203 ML-KEM (planned)

Not in `run_all_silicon_tests.py`. No silicon result yet.

Implements the approved key-encapsulation mechanism in
[NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)
on top of the shipped M10–M15b ring / NTT stack.

- Ring `R_q = Z_3329[X]/(X^{256}+1)` — already proven by M15b schoolbook.
- Product used by the KEM is FIPS 203 Algorithms 9–12 (NTT), not M15b O(N²).
- First parameter set: ML-KEM-512 (`k=2`). Default later: ML-KEM-768
  ([FIPS 203 §8](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)).
- Hashes from [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf).
- K-PKE (Algorithms 13–15) is a component only
  ([FIPS 203 §3.3](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)).

Gates and citations: [`docs/M32_FIPS203_MLKEM.md`](../../docs/M32_FIPS203_MLKEM.md).
