"""M33d / M33e - ML-DSA composer for FIPS 204 (Post-Quantum Cryptography).

Composes ML-DSA KeyGen (Alg 6), Sign_internal (Alg 7), and Verify_internal
(Alg 8) on top of the per-primitive silicon dispatch:

    - M33a  Dilithium NTT / INTT / basemul over Z_q, q = 8380417
    - M33b  Power2Round / Decompose / MakeHint / UseHint / CheckNormBound
            / ReduceModPm on int32 polynomials
    - M32c  Keccak SHAKE128 / SHAKE256 (deployed for M32e, reused as M33c)

Everything that is intrinsically sequential (rejection sampling driven by
SHAKE output, SampleInBall, bit-packing, matrix-vector accumulation) stays in
host Python. Everything data-parallel over the 256 coefficients of a
polynomial dispatches to the NPU via the SiliconBackend abstraction.

Structure is deliberately parallel to `tests/m32_mlkem/mlkem_composer.py`: the
composer here is a thin orchestrator on top of `dilithium-py v1.4.0`, with the
numerical primitives replaced by silicon dispatch. Algorithmic correctness
inherits from `dilithium-py` and NIST ACVP-Server; the composer only needs to
prove the silicon bridge does not alter results.

References
    FIPS 204: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
    pq-crystals dilithium: https://github.com/pq-crystals/dilithium
    dilithium-py: https://github.com/GiacomoPope/dilithium-py
    NIST ACVP-Server ML-DSA vectors:
      https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files
"""

from __future__ import annotations

from collections.abc import Callable

from dilithium_py.ml_dsa.default_parameters import DEFAULT_PARAMETERS
from dilithium_py.ml_dsa.ml_dsa import ML_DSA
from dilithium_py.polynomials.polynomials import PolynomialRing

Q = 8380417
N = 256
R_POW = 32
R_MOD_Q = (1 << R_POW) % Q
R_INV_MOD_Q = pow(1 << R_POW, -1, Q)


# ---------------------------------------------------------------------------
# Silicon backend abstraction. Any callable exposing the same dispatch signature
# as `run_m33a(mode, in_a, in_b) -> list[int]` and `run_m33b(mode, param, in_a,
# in_b) -> tuple[list[int], list[int]]` can be plugged in. The default is the
# native-only Phoenix runner package.  Reference dispatchers remain below only
# as explicit test fixtures; a default composer must not claim silicon while
# silently evaluating those fixtures on the host.
# ---------------------------------------------------------------------------
class SiliconBackend:
    """Dispatch abstraction.

    Two dispatch callables are held:
      m33a: (mode:int, in_a:list[int], in_b:list[int]) -> list[int]
      m33b: (mode:int, param:int, in_a:list[int], in_b:list[int]) -> tuple[list[int], list[int]]

    Semantics MUST match dilithium_ntt_kernel.cc and dilithium_sampler_kernel.cc.
    """

    def __init__(
        self,
        m33a: Callable | None = None,
        m33b: Callable | None = None,
    ) -> None:
        if (m33a is None) != (m33b is None):
            raise ValueError("M33a and M33b dispatchers must be supplied together")
        if m33a is None:
            # Importing the runners is safe on a host without IRON; their
            # MLIR-AIE/XRT imports are intentionally lazy. A real dispatch
            # either reaches the NPU or raises NativeRunnerUnavailable.
            from phoenix_sdr_dsp.silicon.m33a_runner import run_m33a
            from phoenix_sdr_dsp.silicon.m33b_runner import run_m33b

            self._m33a = run_m33a
            self._m33b = run_m33b
        else:
            self._m33a = m33a
            self._m33b = m33b

    @classmethod
    def reference_for_unit_tests(cls) -> SiliconBackend:
        """Return an explicitly named host reference fixture.

        This method exists for isolated host-only tests.  It must not be used
        by a script whose output is evaluated as silicon evidence.
        """
        return cls(m33a=cls._ref_m33a(), m33b=cls._ref_m33b())

    # -- explicit host-only reference fixtures ------------------------------
    @staticmethod
    def _ref_m33a() -> Callable:
        QINV = 58728449

        def _br(i, k=8):
            return int(bin(i & ((1 << k) - 1))[2:].zfill(k)[::-1], 2)

        _z_plain = [pow(1753, _br(i, 8), Q) for i in range(N)]

        def _ctr(x):
            x %= Q
            return x - Q if x > Q // 2 else x

        zetas_mont = [_ctr((z * (1 << 32)) % Q) for z in _z_plain]
        zetas_mont[0] = 0

        def _i32(x):
            x &= 0xFFFFFFFF
            return x - (1 << 32) if x >= (1 << 31) else x

        def _mont(a):
            t = _i32(a * QINV)
            return (a - t * Q) >> 32

        def ntt(coeffs):
            c = list(coeffs)
            k = 0
            length = 128
            while length > 0:
                start = 0
                while start < N:
                    k += 1
                    zeta = zetas_mont[k]
                    j = start
                    for j in range(start, start + length):
                        t = _mont(zeta * c[j + length])
                        c[j + length] = c[j] - t
                        c[j] = c[j] + t
                    start = j + length + 1
                length >>= 1
            return c

        def invntt(coeffs):
            f_mont = 41978
            c = list(coeffs)
            k = 256
            length = 1
            while length < N:
                start = 0
                while start < N:
                    k -= 1
                    zeta = -zetas_mont[k]
                    j = start
                    for j in range(start, start + length):
                        t = c[j]
                        c[j] = t + c[j + length]
                        c[j + length] = t - c[j + length]
                        c[j + length] = _mont(zeta * c[j + length])
                    start = j + length + 1
                length <<= 1
            return [_mont(f_mont * c[j]) for j in range(N)]

        def basemul(a, b):
            return [_mont(a[i] * b[i]) for i in range(N)]

        def reduce_mode(a):
            out = []
            for x in a:
                t = (x + (1 << 22)) >> 23
                out.append(x - t * Q)
            return out

        def dispatch(mode: int, in_a, in_b=None):
            if mode == 0:
                return ntt(in_a)
            if mode == 1:
                return invntt(in_a)
            if mode == 2:
                return basemul(in_a, in_b)
            if mode == 3:
                return reduce_mode(in_a)
            raise ValueError(mode)

        return dispatch

    @staticmethod
    def _ref_m33b() -> Callable:
        D_BITS = 13
        POW2D = 1 << D_BITS

        def canon(r):
            return r % Q

        def cmod_pm(r, m):
            r %= m
            if r > (m >> 1):
                r -= m
            return r

        def power2round(r):
            rp = canon(r)
            r0 = rp & (POW2D - 1)
            if r0 > (POW2D >> 1):
                r0 -= POW2D
            return (rp - r0) >> D_BITS, r0

        def decompose(r, alpha):
            rp = canon(r)
            r0 = cmod_pm(rp, alpha)
            if rp - r0 == Q - 1:
                return 0, r0 - 1
            return (rp - r0) // alpha, r0

        def high_bits(r, alpha):
            return decompose(r, alpha)[0]

        def low_bits(r, alpha):
            return decompose(r, alpha)[1]

        def make_hint(z, r, alpha):
            # 1 if HighBits(r + z) != HighBits(r), else 0.
            return int(high_bits((r + z) % Q, alpha) != high_bits(r, alpha))

        def use_hint(h, r, alpha):
            m = (Q - 1) // alpha
            r1, r0 = decompose(r, alpha)
            if h == 0:
                return r1
            if r0 > 0:
                return (r1 + 1) % m
            return (r1 - 1) % m

        def check_norm(coeffs, bound):
            for x in coeffs:
                y = cmod_pm(x, Q)
                if abs(y) >= bound:
                    return 0
            return 1

        def dispatch(mode: int, param: int, in_a, in_b=None):
            if mode == 0:  # POWER2ROUND
                c, d = [], []
                for r in in_a:
                    r1, r0 = power2round(r)
                    c.append(r1)
                    d.append(r0)
                return c, d
            if mode == 1:  # DECOMPOSE
                c, d = [], []
                for r in in_a:
                    r1, r0 = decompose(r, param)
                    c.append(r1)
                    d.append(r0)
                return c, d
            if mode == 2:  # MAKEHINT: in_a=z, in_b=r
                c = [make_hint(in_a[i], in_b[i], param) for i in range(N)]
                return c, [0] * N
            if mode == 3:  # USEHINT: in_a=h, in_b=r
                c = [use_hint(in_a[i], in_b[i], param) for i in range(N)]
                return c, [0] * N
            if mode == 4:  # CHECKNORM: in_a=r, param=bound
                c = [check_norm(in_a, param)] + [0] * (N - 1)
                return c, [0] * N
            if mode == 5:  # REDUCE_PM
                c = [cmod_pm(x, Q) for x in in_a]
                return c, [0] * N
            raise NotImplementedError(f"m33b mode {mode}")

        return dispatch

    # -- public composer primitives -----------------------------------------
    def poly_ntt(self, coeffs):
        """Plain-modular in, plain-modular out (matches dilithium-py to_ntt)."""
        out = self._m33a(0, list(coeffs), None)
        return [x % Q for x in out]

    def poly_invntt(self, coeffs):
        """Plain-modular in, plain-modular out. Strip the implicit R factor."""
        out = self._m33a(1, list(coeffs), None)
        return [(x * R_INV_MOD_Q) % Q for x in out]

    def poly_basemul(self, a, b):
        """Plain-modular in/out. Post-scale by R to strip Montgomery R^-1."""
        out = self._m33a(2, list(a), list(b))
        return [(x * R_MOD_Q) % Q for x in out]

    def poly_add_mod(self, a, b):
        """Coefficient-wise (a + b) mod q. Trivial: host Python."""
        return [(a[i] + b[i]) % Q for i in range(N)]

    def poly_power2round(self, r):
        """FIPS 204 Alg 29 Power2Round via M33b MODE 0."""
        r1, r0 = self._m33b(0, 0, list(r), None)
        return r1, r0

    def poly_decompose(self, r, alpha):
        """FIPS 204 Alg 30 Decompose via M33b MODE 1. Returns (r1, r0)."""
        r1, r0 = self._m33b(1, alpha, list(r), None)
        return r1, r0

    def poly_high_bits(self, r, alpha):
        """FIPS 204 Alg 31 HighBits via M33b MODE 1 (first output)."""
        r1, _ = self._m33b(1, alpha, list(r), None)
        return r1

    def poly_low_bits(self, r, alpha):
        """FIPS 204 Alg 32 LowBits via M33b MODE 1 (second output)."""
        _, r0 = self._m33b(1, alpha, list(r), None)
        return r0

    def poly_make_hint(self, z, r, alpha):
        """FIPS 204 Alg 33 MakeHint via M33b MODE 2."""
        h, _ = self._m33b(2, alpha, list(z), list(r))
        return h

    def poly_use_hint(self, h, r, alpha):
        """FIPS 204 Alg 34 UseHint via M33b MODE 3."""
        w1, _ = self._m33b(3, alpha, list(h), list(r))
        return w1

    def poly_check_norm(self, r, bound):
        """CheckNormBound via M33b MODE 4. Returns True if all |r_i| < bound."""
        c, _ = self._m33b(4, bound, list(r), None)
        return c[0] == 1


# ---------------------------------------------------------------------------
# ML-DSA KeyGen composer. Mirrors ML_DSA._keygen_internal exactly, but every
# NTT / INTT / basemul / power_2_round call routes through SiliconBackend.
# ---------------------------------------------------------------------------
class MLDSAComposer:
    """One instance per (param_set, backend) pair.

    param_set ∈ {"ML-DSA-44", "ML-DSA-65", "ML-DSA-87"}.
    """

    def __init__(self, param_set: str, backend: SiliconBackend | None = None) -> None:
        key = param_set.replace("-", "_")   # "ML_DSA_44"
        cfg = DEFAULT_PARAMETERS[key]
        # Reuse dilithium-py's algorithm object for its helpers (SHAKE, packing,
        # rejection sampling), then replace the numerical primitives at call
        # sites in _keygen with silicon dispatch.
        self._ml = ML_DSA(cfg)
        self._backend = backend or SiliconBackend()
        self._R: PolynomialRing = self._ml.R

    # ---- KeyGen ----
    def keygen_internal(self, zeta: bytes) -> tuple[bytes, bytes]:
        """FIPS 204 Alg 6 ML-DSA.KeyGen_internal, composed via silicon dispatch.

        Bit-identical output to `dilithium_py.ml_dsa.ML_DSA._keygen_internal`.
        """
        ml = self._ml
        k, ell = ml.k, ml.l

        seed_domain_sep = zeta + bytes([k]) + bytes([ell])
        seed_bytes = ml._h(seed_domain_sep, 128)
        rho, rho_prime, K_bytes = (
            seed_bytes[:32],
            seed_bytes[32:96],
            seed_bytes[96:],
        )

        # ExpandA - k*l polynomials sampled directly in the NTT domain.
        A_hat = ml._expand_matrix_from_seed(rho)

        # ExpandS - s1 (length l), s2 (length k).
        s1, s2 = ml._expand_vector_from_seed(rho_prime)

        # Vector storage in dilithium-py is 2D even for row-vectors:
        # s1._data has shape (1, ell); s2._data has shape (1, k).
        s1_polys = s1._data[0]
        s2_polys = s2._data[0]

        # s1 -> NTT domain via silicon (one poly at a time).
        # Coefficients in s1/s2 are centred in (-eta, eta]; reduce mod q first.
        s1_hat_coeffs = [
            self._backend.poly_ntt([c % Q for c in p.coeffs])
            for p in s1_polys
        ]

        # Matrix-vector multiply in NTT domain: t_hat[i] = sum_j A_hat[i][j] * s1_hat[j].
        t_hat_coeffs = []
        for i in range(k):
            acc = [0] * N
            for j in range(ell):
                a_ij = [c % Q for c in A_hat._data[i][j].coeffs]
                prod = self._backend.poly_basemul(a_ij, s1_hat_coeffs[j])
                acc = self._backend.poly_add_mod(acc, prod)
            t_hat_coeffs.append(acc)

        # INTT each row of t_hat, then + s2.
        t_coeffs = []
        for i in range(k):
            t_i = self._backend.poly_invntt(t_hat_coeffs[i])
            s2_i = [c % Q for c in s2_polys[i].coeffs]
            t_i = self._backend.poly_add_mod(t_i, s2_i)
            t_coeffs.append(t_i)

        # Power2Round split -> (t1, t0).
        t1_coeffs = []
        t0_coeffs = []
        for i in range(k):
            r1, r0 = self._backend.poly_power2round(t_coeffs[i])
            t1_coeffs.append(r1)
            t0_coeffs.append(r0)

        # Wrap back into dilithium-py types so we can reuse the packing.
        t1_polys = [self._R(c) for c in t1_coeffs]
        t0_polys = [self._R(c) for c in t0_coeffs]
        t1_vec = ml.M.vector(t1_polys)
        t0_vec = ml.M.vector(t0_polys)

        pk = ml._pack_pk(rho, t1_vec)
        tr = ml._h(pk, 64)
        sk = ml._pack_sk(rho, K_bytes, tr, s1, s2, t0_vec)
        return pk, sk

    # ------------------------------------------------------------------
    # M33e helpers: bridge polys / vectors between host (dilithium-py) and
    # silicon-dispatched coeff lists.
    # ------------------------------------------------------------------
    def _vec_to_ntt(self, vec) -> list[list[int]]:
        """Silicon NTT on each poly of a dilithium-py Vector. Returns coeff lists."""
        return [
            self._backend.poly_ntt([c % Q for c in p.coeffs])
            for p in vec._data[0]
        ]

    def _matmul_A_vec_ntt(self, A_hat, v_hat_coeffs: list[list[int]]) -> list[list[int]]:
        """NTT-domain matrix-vector product: out[i] = sum_j A[i][j] * v[j]."""
        k = len(A_hat._data)
        ell = len(A_hat._data[0])
        out = []
        for i in range(k):
            acc = [0] * N
            for j in range(ell):
                a_ij = [c % Q for c in A_hat._data[i][j].coeffs]
                prod = self._backend.poly_basemul(a_ij, v_hat_coeffs[j])
                acc = self._backend.poly_add_mod(acc, prod)
            out.append(acc)
        return out

    def _scale_vec_ntt(self, c_hat: list[int], v_hat_coeffs: list[list[int]]) -> list[list[int]]:
        """NTT-domain scalar-polynomial * vector: out[i] = c * v[i]."""
        return [self._backend.poly_basemul(c_hat, v_i) for v_i in v_hat_coeffs]

    def _vec_from_ntt(self, v_hat_coeffs: list[list[int]]) -> list[list[int]]:
        """Silicon INTT on each poly. Returns plain-modular coeff lists."""
        return [self._backend.poly_invntt(v_i) for v_i in v_hat_coeffs]

    def _vec_add(self, a, b) -> list[list[int]]:
        return [self._backend.poly_add_mod(a[i], b[i]) for i in range(len(a))]

    def _vec_sub(self, a, b) -> list[list[int]]:
        return [[(a[i][j] - b[i][j]) % Q for j in range(N)] for i in range(len(a))]

    def _vec_neg(self, a) -> list[list[int]]:
        return [[(-x) % Q for x in row] for row in a]

    def _wrap_vec(self, coeff_lists):
        """Wrap a list of coefficient-lists back into a dilithium-py Vector."""
        return self._ml.M.vector([self._R(c) for c in coeff_lists])

    # ------------------------------------------------------------------
    # ML-DSA.Sign_internal (FIPS 204 Alg 7). Deterministic when rnd = 0^32.
    # ------------------------------------------------------------------
    def sign_internal(
        self,
        sk: bytes,
        m_or_mu: bytes,
        rnd: bytes,
        external_mu: bool = False,
    ) -> bytes:
        ml = self._ml
        rho, k_seed, tr, s1, s2, t0 = ml._unpack_sk(sk)

        # Precompute A_hat, s1_hat, s2_hat, t0_hat via silicon NTT.
        A_hat = ml._expand_matrix_from_seed(rho)
        s1_hat = self._vec_to_ntt(s1)
        s2_hat = self._vec_to_ntt(s2)
        t0_hat = self._vec_to_ntt(t0)

        # mu and rho'' derivation (Alg 7, lines 6-7).
        if external_mu:
            mu = m_or_mu
        else:
            mu = ml._h(tr + m_or_mu, 64)
        rho_pp = ml._h(k_seed + rnd + mu, 64)

        alpha = ml.gamma_2 << 1
        kappa = 0
        while True:
            # ExpandMask + NTT.
            y = ml._expand_mask_vector(rho_pp, kappa)
            kappa += ml.l
            y_hat = self._vec_to_ntt(y)

            # w = A * y (NTT domain), then INTT.
            w_hat = self._matmul_A_vec_ntt(A_hat, y_hat)
            w = self._vec_from_ntt(w_hat)

            # w1 = HighBits(w, alpha), packed to bytes via host.
            w1 = [self._backend.poly_high_bits(w_i, alpha) for w_i in w]
            w1_vec = self._wrap_vec(w1)
            w1_bytes = w1_vec.bit_pack_w(ml.gamma_2)

            # Challenge c and its NTT.
            c_tilde = ml._h(mu + w1_bytes, ml.c_tilde_bytes)
            c_poly = self._R.sample_in_ball(c_tilde, ml.tau)
            c_hat = self._backend.poly_ntt([x % Q for x in c_poly.coeffs])

            # z = y + c*s1 (INTT). Norm check on z.
            c_s1_hat = self._scale_vec_ntt(c_hat, s1_hat)
            c_s1 = self._vec_from_ntt(c_s1_hat)
            y_coeffs = [[c % Q for c in p.coeffs] for p in y._data[0]]
            z = self._vec_add(y_coeffs, c_s1)
            if not all(self._backend.poly_check_norm(z_i, ml.gamma_1 - ml.beta) for z_i in z):
                continue

            # r0 = LowBits(w - c*s2). Norm check on r0.
            c_s2_hat = self._scale_vec_ntt(c_hat, s2_hat)
            c_s2 = self._vec_from_ntt(c_s2_hat)
            w_minus_cs2 = self._vec_sub(w, c_s2)
            r0 = [self._backend.poly_low_bits(x, alpha) for x in w_minus_cs2]
            if not all(self._backend.poly_check_norm(r_i, ml.gamma_2 - ml.beta) for r_i in r0):
                continue

            # Norm check on c*t0.
            c_t0_hat = self._scale_vec_ntt(c_hat, t0_hat)
            c_t0 = self._vec_from_ntt(c_t0_hat)
            if not all(self._backend.poly_check_norm(x, ml.gamma_2) for x in c_t0):
                continue

            # h = MakeHint(-c*t0, w - c*s2 + c*t0, alpha). Popcount check.
            neg_c_t0 = self._vec_neg(c_t0)
            r_plus_ct0 = self._vec_add(w_minus_cs2, c_t0)
            h = [
                self._backend.poly_make_hint(neg_c_t0[i], r_plus_ct0[i], alpha)
                for i in range(ml.k)
            ]
            popcount = sum(sum(row) for row in h)
            if popcount > ml.omega:
                continue

            # Pack signature via dilithium-py helpers.
            z_vec = self._wrap_vec(z)
            # dilithium-py packing expects centred z; convert once for packing.
            z_centred = [
                [((v + Q // 2) % Q) - Q // 2 for v in row] for row in z
            ]
            z_vec = self._wrap_vec(z_centred)
            h_vec = self._wrap_vec(h)
            return ml._pack_sig(c_tilde, z_vec, h_vec)

    # ------------------------------------------------------------------
    # ML-DSA.Verify_internal (FIPS 204 Alg 8).
    # ------------------------------------------------------------------
    def verify_internal(
        self,
        pk: bytes,
        m_or_mu: bytes,
        sig: bytes,
        external_mu: bool = False,
    ) -> bool:
        ml = self._ml
        try:
            rho, t1 = ml._unpack_pk(pk)
            c_tilde, z, h = ml._unpack_sig(sig)
        except (ValueError, IndexError):
            return False

        # Sanity checks up front (unrelated to silicon).
        popcount = sum(sum(row) for row in [[int(x) for x in p.coeffs] for p in h._data[0]])
        if popcount > ml.omega:
            return False

        alpha = 2 * ml.gamma_2
        z_coeffs = [[c % Q for c in p.coeffs] for p in z._data[0]]
        if not all(self._backend.poly_check_norm(z_i, ml.gamma_1 - ml.beta) for z_i in z_coeffs):
            return False

        A_hat = ml._expand_matrix_from_seed(rho)

        if external_mu:
            mu = m_or_mu
        else:
            tr = ml._h(pk, 64)
            mu = ml._h(tr + m_or_mu, 64)

        c_poly = self._R.sample_in_ball(c_tilde, ml.tau)
        c_hat = self._backend.poly_ntt([x % Q for x in c_poly.coeffs])
        z_hat = [self._backend.poly_ntt(z_i) for z_i in z_coeffs]

        # t1 * 2^d, then NTT.
        t1_scaled = [[(c * (1 << ml.d)) % Q for c in p.coeffs] for p in t1._data[0]]
        t1_scaled_hat = [self._backend.poly_ntt(row) for row in t1_scaled]

        # Az_hat - c*t1_hat.
        Az_hat = self._matmul_A_vec_ntt(A_hat, z_hat)
        c_t1_hat = self._scale_vec_ntt(c_hat, t1_scaled_hat)
        diff_hat = [
            [(Az_hat[i][j] - c_t1_hat[i][j]) % Q for j in range(N)]
            for i in range(ml.k)
        ]
        diff = self._vec_from_ntt(diff_hat)

        # w' = UseHint(h, diff, alpha).
        h_coeffs = [[int(c) & 1 for c in p.coeffs] for p in h._data[0]]
        w_prime = [
            self._backend.poly_use_hint(h_coeffs[i], diff[i], alpha)
            for i in range(ml.k)
        ]
        w_prime_vec = self._wrap_vec(w_prime)
        w_prime_bytes = w_prime_vec.bit_pack_w(ml.gamma_2)

        return c_tilde == ml._h(mu + w_prime_bytes, ml.c_tilde_bytes)
