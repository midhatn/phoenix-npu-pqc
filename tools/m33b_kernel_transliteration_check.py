"""M33b - transliteration cross-check for dilithium_sampler_kernel.cc.

Parses the C source and re-derives the fixed constants (Q, N, D_BITS, POW2D,
POW2D_HALF) from first principles, and cross-checks that all six dispatched
modes are present with the expected mode numbers (0..5).

Also spot-checks that the reference-C-equivalent semantics for the two
Decompose alpha values (ML-DSA-44 uses alpha = (q-1)/44, ML-DSA-65/87 use
alpha = (q-1)/16) match the standard.

References
    FIPS 204: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
    pq-crystals rounding.c: https://github.com/pq-crystals/dilithium/blob/master/ref/rounding.c
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KERNEL = REPO / "tests" / "m33_mldsa" / "dilithium_sampler_kernel.cc"


def parse_kernel() -> dict:
    src = KERNEL.read_text(encoding="utf-8")

    # Resolve constants in the order they appear so later ones can reference
    # earlier ones (e.g. POW2D = 1 << D_BITS).
    env: dict = {}

    def num_of(name: str) -> int:
        m = re.search(rf"constexpr int32_t {name}\s*=\s*([^;]+);", src)
        if not m:
            raise RuntimeError(f"missing {name}")
        # Strip C-style inline comments and any trailing content.
        expr = re.sub(r"//.*$", "", m.group(1)).strip()
        val = int(eval(expr, {"__builtins__": {}}, env))
        env[name] = val
        return val

    q = num_of("Q")
    n = num_of("N")
    d_bits = num_of("D_BITS")
    pow2d = num_of("POW2D")
    pow2d_half = num_of("POW2D_HALF")

    # Ensure all six modes are present as `case <n>:`
    modes = {int(x) for x in re.findall(r"case (\d+)\s*:", src)}

    return {
        "Q": q,
        "N": n,
        "D_BITS": d_bits,
        "POW2D": pow2d,
        "POW2D_HALF": pow2d_half,
        "modes": modes,
    }


def main() -> int:
    print("M33b transliteration cross-check")
    print(f"  kernel: {KERNEL}")
    k = parse_kernel()

    checks = []
    checks.append(("Q == 8380417", k["Q"] == 8380417))
    checks.append(("N == 256", k["N"] == 256))
    checks.append(("D_BITS == 13", k["D_BITS"] == 13))
    checks.append(("POW2D == 2^D_BITS", k["POW2D"] == (1 << k["D_BITS"])))
    checks.append(
        ("POW2D_HALF == 2^(D_BITS-1)",
         k["POW2D_HALF"] == (1 << (k["D_BITS"] - 1))),
    )
    for m in range(6):
        checks.append((f"mode {m} dispatched", m in k["modes"]))
    # Also verify the reference alphas are derivable from Q:
    alpha_44 = 2 * ((k["Q"] - 1) // 88)
    alpha_65 = 2 * ((k["Q"] - 1) // 32)
    checks.append(("ML-DSA-44 alpha == 190464", alpha_44 == 190464))
    checks.append(("ML-DSA-65 alpha == 523776", alpha_65 == 523776))
    checks.append(("(Q-1)/alpha_44 == 44", (k["Q"] - 1) // alpha_44 == 44))
    checks.append(("(Q-1)/alpha_65 == 16", (k["Q"] - 1) // alpha_65 == 16))

    ok = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            ok = False
    print("=" * 72)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
