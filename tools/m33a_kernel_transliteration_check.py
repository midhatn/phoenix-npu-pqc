"""M33a - transliteration cross-check for dilithium_ntt_kernel.cc.

Reads the C source of tests/m33_mldsa/dilithium_ntt_kernel.cc, extracts the
ZETAS_MONT[256] table + Q + QINV + F_MONT constants, and reproves them from
first principles:

    Q          = 8380417
    QINV       = pow(Q, -1, 2^32) = 58728449         [Q * QINV = 1 mod 2^32]
    R          = 2^32
    F_MONT     = mont2 * n^-1 mod Q, signed         [= 41978]
    ZETAS[i]   = ((1753 ^ bitrev8(i)) * R) mod Q, centered signed int32
    ZETAS[0]   = 0   (ref-C convention: never used in butterfly)

This is the same pattern used for M32b (kyber NTT) - it defends against
silent table drift and constant-of-magic corruption between paste cycles.

Run:
    python tools/m33a_kernel_transliteration_check.py

References
    FIPS 204: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
    pq-crystals dilithium ref: https://github.com/pq-crystals/dilithium/tree/master/ref
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KERNEL = REPO / "tests" / "m33_mldsa" / "dilithium_ntt_kernel.cc"


def _bitrev8(i: int) -> int:
    return int(bin(i & 0xFF)[2:].zfill(8)[::-1], 2)


def derive_zetas(q: int) -> list[int]:
    out = []
    for i in range(256):
        z = pow(1753, _bitrev8(i), q)
        z_mont = (z * (1 << 32)) % q
        if z_mont > q // 2:
            z_mont -= q
        out.append(z_mont)
    out[0] = 0
    return out


def parse_kernel() -> dict:
    src = KERNEL.read_text(encoding="utf-8")

    def _num_of(name: str) -> int:
        m = re.search(rf"constexpr int32_t {name}\s*=\s*(-?\d+);", src)
        if not m:
            raise RuntimeError(f"missing constant {name}")
        return int(m.group(1))

    q = _num_of("Q")
    qinv = _num_of("QINV")
    mont_r_mod = _num_of("MONT_R_MOD")
    f_mont = _num_of("F_MONT")
    n = _num_of("N")

    m = re.search(r"ZETAS_MONT\[256\] = \{(.+?)\};", src, re.DOTALL)
    if not m:
        raise RuntimeError("missing ZETAS_MONT array")
    zetas = [int(x) for x in re.findall(r"-?\d+", m.group(1))]
    if len(zetas) != 256:
        raise RuntimeError(f"expected 256 zetas, got {len(zetas)}")

    return {
        "Q": q,
        "N": n,
        "QINV": qinv,
        "MONT_R_MOD": mont_r_mod,
        "F_MONT": f_mont,
        "ZETAS": zetas,
    }


def main() -> int:
    print("M33a transliteration cross-check")
    print(f"  kernel: {KERNEL}")
    k = parse_kernel()

    checks: list[tuple[str, bool, str]] = []

    checks.append(("Q == 8380417", k["Q"] == 8380417, str(k["Q"])))
    checks.append(("N == 256", k["N"] == 256, str(k["N"])))

    # QINV: Q * QINV congruent to 1 mod 2^32
    got = (k["Q"] * k["QINV"]) & 0xFFFFFFFF
    checks.append(("Q * QINV == 1 mod 2^32", got == 1, f"got {got}"))

    # MONT_R_MOD: 2^32 mod Q
    expected_r_mod = (1 << 32) % k["Q"]
    checks.append(
        ("MONT_R_MOD == 2^32 mod Q",
         k["MONT_R_MOD"] == expected_r_mod,
         f"got {k['MONT_R_MOD']}, want {expected_r_mod}"),
    )

    # F_MONT: mont^2 * n^-1 mod Q, signed (ref-C constant = 41978)
    mont_sq = ((1 << 32) * (1 << 32)) % k["Q"]
    inv_n = pow(256, -1, k["Q"])
    f_expected = (mont_sq * inv_n) % k["Q"]
    if f_expected > k["Q"] // 2:
        f_expected -= k["Q"]
    checks.append(
        ("F_MONT == (2^64 / 256) mod Q signed",
         k["F_MONT"] == f_expected,
         f"got {k['F_MONT']}, want {f_expected}"),
    )
    checks.append(
        ("F_MONT == 41978 (pq-crystals ref-C)",
         k["F_MONT"] == 41978,
         f"got {k['F_MONT']}"),
    )

    # ZETAS_MONT
    z_ref = derive_zetas(k["Q"])
    diffs = [(i, k["ZETAS"][i], z_ref[i]) for i in range(256) if k["ZETAS"][i] != z_ref[i]]
    checks.append(
        ("ZETAS_MONT[256] matches ((1753^br8(i)) * R) mod Q, signed",
         not diffs,
         f"{len(diffs)} diffs, first: {diffs[0] if diffs else 'none'}"),
    )
    # Spot-check first 16 against pq-crystals ref-C ntt.c published values
    ref_c_first16 = [
        0, 25847, -2608894, -518909, 237124, -777960, -876248, 466468,
        1826347, 2353451, -359251, -2091905, 3119733, -2884855, 3111497, 2680103,
    ]
    checks.append(
        ("ZETAS_MONT[0..15] matches pq-crystals ntt.c",
         k["ZETAS"][:16] == ref_c_first16,
         f"got {k['ZETAS'][:8]}"),
    )

    ok = True
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            print(f"         detail: {detail}")
            ok = False
    print("=" * 72)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
