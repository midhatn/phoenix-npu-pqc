# Purpose: Master Prompt Milestone 12: Independent CPU NTT/INTT Reference & Constant Generator.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Prime Modulus: q = 3329.
# Transform Lengths: N = 16 and N = 256.

import numpy as np

MOD_Q = 3329

def is_prime(n):
    if n < 2: return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0: return False
    return True

def prime_factors(n):
    factors = set()
    d = 2
    while d * d <= n:
        if n % d == 0:
            factors.add(d)
            n //= d
        else:
            d += 1
    if n > 1:
        factors.add(n)
    return factors

def find_primitive_root(q):
    phi = q - 1
    factors = prime_factors(phi)
    for g in range(2, q):
        if all(pow(g, phi // p, q) != 1 for p in factors):
            return g
    return None

def find_nth_root_of_unity(N, q):
    phi = q - 1
    if phi % N != 0:
        raise ValueError(f"N = {N} does not divide q - 1 = {phi}")
    g = find_primitive_root(q)
    # omega = g^((q-1)/N) mod q
    omega = pow(g, phi // N, q)
    return omega

def verify_nth_root(omega, N, q):
    # Rule 1: omega^N mod q == 1
    if pow(omega, N, q) != 1:
        return False
    # Rule 2: For every prime divisor p of N, omega^(N/p) mod q != 1
    for p in prime_factors(N):
        if pow(omega, N // p, q) == 1:
            return False
    return True

def bit_reverse_indices(n_bits):
    n = 1 << n_bits
    rev = np.zeros(n, dtype=int)
    for i in range(n):
        r = 0
        for b in range(n_bits):
            if (i >> b) & 1:
                r |= (1 << (n_bits - 1 - b))
        rev[i] = r
    return rev

def bit_reverse_permute(arr):
    n = len(arr)
    n_bits = int(np.log2(n))
    rev = bit_reverse_indices(n_bits)
    return arr[rev]

def direct_dft_ntt(x, omega, q=MOD_Q):
    """ Direct O(N^2) Discrete NTT Reference """
    N = len(x)
    X = np.zeros(N, dtype=np.int64)
    for k in range(N):
        s = 0
        for n in range(N):
            w = pow(int(omega), n * k, q)
            s = (s + int(x[n]) * w) % q
        X[k] = s
    return X.astype(np.int16)

def iterative_radix2_ntt(x, omega, q=MOD_Q):
    """ Iterative Radix-2 Cooley-Tukey NTT (Bit-reversed output or input) """
    N = len(x)
    n_stages = int(np.log2(N))
    # Bit reverse input (DIT)
    a = bit_reverse_permute(x.astype(np.int64)).copy()
    
    for stage in range(1, n_stages + 1):
        m = 1 << stage
        half_m = m >> 1
        # Root for this sub-transform size m
        w_m = pow(int(omega), N // m, q)
        for k in range(0, N, m):
            w = 1
            for j in range(half_m):
                u = a[k + j]
                v = (a[k + j + half_m] * w) % q
                a[k + j] = (u + v) % q
                a[k + j + half_m] = (u - v + q) % q
                w = (w * w_m) % q
    return a.astype(np.int16)

def iterative_radix2_intt(X, omega, q=MOD_Q):
    """ Iterative Radix-2 Inverse NTT (using omega^-1 and scaled by N^-1 mod q) """
    N = len(X)
    omega_inv = pow(int(omega), q - 2, q)
    N_inv = pow(N, q - 2, q)
    
    x_unscaled = iterative_radix2_ntt(X, omega_inv, q)
    x = (x_unscaled.astype(np.int64) * N_inv) % q
    return x.astype(np.int16)

def main():
    print("======================================================================")
    print("      PHOENIX SDR-DSP MASTER PROMPT MILESTONE 12: NTT CONSTANTS       ")
    print("                   AND CPU REFERENCE ENGINE                           ")
    print("======================================================================")

    print(f"Modulus q: {MOD_Q} (Prime: {is_prime(MOD_Q)})")
    g = find_primitive_root(MOD_Q)
    print(f"Primitive generator g: {g}")

    # Generate constants for N = 16 and N = 256
    for N in [16, 256]:
        print(f"\n--- Parameters for Transform Length N = {N} ---")
        omega = find_nth_root_of_unity(N, MOD_Q)
        omega_inv = pow(omega, MOD_Q - 2, MOD_Q)
        N_inv = pow(N, MOD_Q - 2, MOD_Q)

        print(f"  Primitive N-th Root of Unity (omega):      {omega}")
        print(f"  Inverse Root of Unity (omega^-1):          {omega_inv}")
        print(f"  Multiplicative Inverse of N (N^-1 mod q):  {N_inv}")

        # Programmatic Verification of Root Rules
        is_valid = verify_nth_root(omega, N, MOD_Q)
        print(f"  Root Verification (omega^{N} mod q == 1, omega^{N}/p != 1): [{'VALID' if is_valid else 'INVALID'}]")
        
        # Verify N * N^-1 mod q == 1
        inv_check = (N * N_inv) % MOD_Q == 1
        print(f"  Inverse Check (N * N^-1 mod q == 1):         [{'VALID' if inv_check else 'INVALID'}]")

        # Generate twiddle factor table
        twiddles = [pow(omega, i, MOD_Q) for i in range(N // 2)]
        print(f"  Twiddle Table Size: {len(twiddles)} elements")
        print(f"  Twiddles [0..7]: {twiddles[:8]}")

        # Test Vectors: All zeros, Unit impulse, Constant, Random
        print(f"\n  Running Mathematical Test Suite for N = {N}...")
        
        # 1. Impulse
        impulse = np.zeros(N, dtype=np.int16)
        impulse[0] = 1
        dft_imp = direct_dft_ntt(impulse, omega)
        radix_imp = iterative_radix2_ntt(impulse, omega)
        intt_imp = iterative_radix2_intt(radix_imp, omega)
        assert np.array_equal(dft_imp, np.ones(N, dtype=np.int16)), "Impulse DFT failed"
        assert np.array_equal(radix_imp, dft_imp), "Radix-2 Impulse NTT failed"
        assert np.array_equal(intt_imp, impulse), "Round-trip Impulse INTT failed"
        print("    [PASS] Unit Impulse & Round-trip INTT")

        # 2. Constant Vector
        const_vec = np.full(N, 42, dtype=np.int16)
        radix_const = iterative_radix2_ntt(const_vec, omega)
        intt_const = iterative_radix2_intt(radix_const, omega)
        assert np.array_equal(intt_const, const_vec), "Constant INTT failed"
        print("    [PASS] Constant Vector & Round-trip INTT")

        # 3. Random Vector & Equivalence with O(N^2) Direct DFT
        np.random.seed(12345)
        rand_vec = np.random.randint(0, MOD_Q, size=N, dtype=np.int16)
        dft_rand = direct_dft_ntt(rand_vec, omega)
        radix_rand = iterative_radix2_ntt(rand_vec, omega)
        intt_rand = iterative_radix2_intt(radix_rand, omega)

        assert np.array_equal(radix_rand, dft_rand), f"Radix-2 vs Direct DFT mismatch for N={N}"
        assert np.array_equal(intt_rand, rand_vec), f"Round-trip INTT failed for random vector N={N}"
        print("    [PASS] Random Vector: Bit-exact match between Direct DFT and Radix-2 Cooley-Tukey!")
        print("    [PASS] Complete Round-Trip (x == INTT(NTT(x))) verified bit-exact!")

    print("\n" + "=" * 70)
    print("PASS!")
    print("SUCCESS: All NTT/INTT mathematical constants and reference transforms verified!")
    print("PASS!")

if __name__ == "__main__":
    main()
