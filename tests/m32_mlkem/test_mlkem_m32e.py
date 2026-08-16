# test_mlkem_m32e.py -- M32e ML-KEM-512 end-to-end on Phoenix NPU.
# ==================================================================================
# Post-Quantum Cryptography (PQC) milestone M32e for the phoenix-sdr-dsp roadmap.
#
# What this test does:
#   Loads NIST ACVP-Server ML-KEM-512 known-answer test vectors, then composes a
#   full FIPS 203 KEM operation (KeyGen / Encaps / Decaps) using Phoenix NPU
#   dispatches for every primitive: SHA-3, SHAKE, SampleNTT, SamplePolyCBD (M32c);
#   NTT, INTT, MultiplyNTTs, PolyAdd/Sub (M32b); Compress d=4/d=10, ByteEncode/
#   ByteDecode d=12, poly frommsg/tomsg (M32d).  The composition itself runs on
#   the laptop CPU; every primitive round-trips host <-> NPU.
#
# Sandbox mode:
#   When aie.iron is not importable (sandbox / CI without silicon), the tests
#   fall back to the pure-Python HostBackend so that ruff / import / bit-exact
#   composer checks still run.  Silicon gates only fire on the laptop.
#
# References:
#   FIPS 203 (Aug 2024)  https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
#   NIST ACVP-Server ML-KEM vectors
#     https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files/ML-KEM-keyGen-FIPS203
#     https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files/ML-KEM-encapDecap-FIPS203
#   kyber-py PyPI  https://pypi.org/project/kyber-py/
#   CCTV notes on unlucky vectors  https://github.com/C2SP/CCTV/blob/main/ML-KEM/README.md
# ==================================================================================

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR))

from mlkem_composer import (
    KYBER_N,
    Backend,
    HostBackend,
    mlkem_decaps_internal,
    mlkem_encaps_internal,
    mlkem_keygen_internal,
)

VECTOR_DIR = TEST_DIR / "vectors"

# ------------------------------------------------------------------
# Silicon backend: wraps @iron.jit dispatchers from sibling M32b/M32c/M32d
# test modules.  Falls back to HostBackend when aie.iron isn't importable
# (sandbox / CI runs).
# ------------------------------------------------------------------

_SILICON_AVAILABLE: bool | None = None


def _silicon_available() -> bool:
    global _SILICON_AVAILABLE
    if _SILICON_AVAILABLE is None:
        try:
            import aie.iron  # noqa: F401
            _SILICON_AVAILABLE = True
        except Exception:  # noqa: BLE001 - any import failure means silicon absent
            _SILICON_AVAILABLE = False
    return _SILICON_AVAILABLE


class SiliconBackend(Backend):
    """Dispatch M32b/M32c/M32d primitives through Phoenix NPU."""

    def __init__(self):
        # Late imports so pytest can collect this file in sandbox.
        from test_keccak_shake_m32c import (
            MODE_SAMPLE_CBD,
            MODE_SAMPLE_NTT,
            MODE_SHA3_256,
            MODE_SHA3_512,
            MODE_SHAKE128,
            MODE_SHAKE256,
        )
        from test_keccak_shake_m32c import (  # type: ignore
            _dispatch as m32c_dispatch,
        )
        from test_keccak_shake_m32c import (
            _pack_ctrl as m32c_pack,
        )
        from test_kpke_m32d import (
            MODE_COMPRESS_D4,
            MODE_COMPRESS_D10,
            MODE_DECOMPRESS_D4,
            MODE_DECOMPRESS_D10,
            MODE_FROMBYTES_D12,
            MODE_FROMMSG,
            MODE_TOBYTES_D12,
            MODE_TOMSG,
        )
        from test_kpke_m32d import (  # type: ignore
            _dispatch as m32d_dispatch,
        )
        from test_kpke_m32d import (
            _pack_ctrl as m32d_pack,
        )
        from test_ntt_m32b import (
            MODE_BASEMUL,
            MODE_INTT,
            MODE_NTT,
            MODE_POLY_ADD,
            MODE_POLY_SUB,
        )
        from test_ntt_m32b import (  # type: ignore
            _dispatch as m32b_dispatch,
        )
        from test_ntt_m32b import (
            _pack_ctrl as m32b_pack,
        )
        self._m32c = (m32c_dispatch, m32c_pack)
        self._m32c_modes = {
            "sha3_256": MODE_SHA3_256, "sha3_512": MODE_SHA3_512,
            "shake128": MODE_SHAKE128, "shake256": MODE_SHAKE256,
            "sample_ntt": MODE_SAMPLE_NTT, "sample_cbd": MODE_SAMPLE_CBD,
        }
        self._m32b = (m32b_dispatch, m32b_pack)
        self._m32b_modes = {
            "ntt": MODE_NTT, "intt": MODE_INTT, "basemul": MODE_BASEMUL,
            "add": MODE_POLY_ADD, "sub": MODE_POLY_SUB,
        }
        self._m32d = (m32d_dispatch, m32d_pack)
        self._m32d_modes = {
            "compress_d4": MODE_COMPRESS_D4, "decompress_d4": MODE_DECOMPRESS_D4,
            "compress_d10": MODE_COMPRESS_D10, "decompress_d10": MODE_DECOMPRESS_D10,
            "tobytes_d12": MODE_TOBYTES_D12, "frombytes_d12": MODE_FROMBYTES_D12,
            "frommsg": MODE_FROMMSG, "tomsg": MODE_TOMSG,
        }

    # ---- M32c dispatch helpers ------------------------------------------
    def _shake_or_sha(self, mode: int, data: bytes, out_len: int) -> bytes:
        dispatch, pack = self._m32c
        in_np = np.frombuffer(data, dtype=np.uint8)
        ctrl = pack(mode, len(data), out_len)
        out_np = dispatch(in_np, ctrl, tag=f"m32e/mode={mode}")
        return bytes(out_np[:out_len])

    def sha3_256(self, data: bytes) -> bytes:
        return self._shake_or_sha(self._m32c_modes["sha3_256"], data, 32)

    def sha3_512(self, data: bytes) -> bytes:
        return self._shake_or_sha(self._m32c_modes["sha3_512"], data, 64)

    def shake128(self, data: bytes, out_len: int) -> bytes:
        return self._shake_or_sha(self._m32c_modes["shake128"], data, out_len)

    def shake256(self, data: bytes, out_len: int) -> bytes:
        return self._shake_or_sha(self._m32c_modes["shake256"], data, out_len)

    def sample_ntt(self, rho: bytes, j: int, i: int) -> list[int]:
        dispatch, pack = self._m32c
        # 34-byte input (rho || j || i), 512-byte output (256 int16 coeffs).
        in_bytes = rho + bytes([j & 0xFF, i & 0xFF])
        in_np = np.frombuffer(in_bytes, dtype=np.uint8)
        ctrl = pack(self._m32c_modes["sample_ntt"], len(in_bytes), 2 * KYBER_N)
        out_np = dispatch(in_np, ctrl, tag=f"m32e/sample_ntt j={j} i={i}")
        # Silicon returns 512 bytes = 256 int16 (positive residues [0, q)).
        coeffs_i16 = np.frombuffer(bytes(out_np[:2 * KYBER_N]),
                                   dtype=np.int16).tolist()
        return [int(c) % 3329 for c in coeffs_i16]

    def sample_poly_cbd(self, seed_s: bytes, b_counter: int, eta: int) -> list[int]:
        dispatch, pack = self._m32c
        in_bytes = seed_s + bytes([b_counter & 0xFF])
        in_np = np.frombuffer(in_bytes, dtype=np.uint8)
        ctrl = pack(self._m32c_modes["sample_cbd"], len(in_bytes),
                    2 * KYBER_N, eta=eta)
        out_np = dispatch(in_np, ctrl, tag=f"m32e/sample_cbd b={b_counter} eta={eta}")
        coeffs_i16 = np.frombuffer(bytes(out_np[:2 * KYBER_N]),
                                   dtype=np.int16).tolist()
        # M32c returns signed CBD values in {-eta..+eta}
        return [int(c) for c in coeffs_i16]

    # ---- M32b dispatch helpers ------------------------------------------
    def _m32b_unary(self, mode: int, poly: list[int]) -> list[int]:
        dispatch, pack = self._m32b
        a = np.asarray(poly, dtype=np.int16)
        ctrl = pack(mode, n_polys=1)
        out = dispatch(a, ctrl, tag=f"m32e/m32b mode={mode}")
        return [int(v) for v in out[:KYBER_N]]

    def _m32b_binary(self, mode: int, a: list[int], b: list[int]) -> list[int]:
        dispatch, pack = self._m32b
        ab = np.concatenate([np.asarray(a, dtype=np.int16),
                             np.asarray(b, dtype=np.int16)])
        ctrl = pack(mode, n_polys=2)
        out = dispatch(ab, ctrl, tag=f"m32e/m32b mode={mode}")
        return [int(v) for v in out[:KYBER_N]]

    # ------------------------------------------------------------------
    # Montgomery convention bridge for pq-crystals NTT primitives.
    #
    # The M32b silicon kernels are line-for-line pq-crystals/kyber-ref.
    # The ZETAS table stored in ntt_kernel.cc is pre-scaled by R = 2^16
    # mod q, and each fqmul(zeta_mont, x) is a montgomery_reduce that
    # cancels one R factor.  Working out the algebra for each primitive:
    #
    #   * silicon.ntt(f)      = ntt_true(f)            mod q  (plain)
    #   * silicon.intt(x)     = R * invntt_true(x)     mod q  (one R factor)
    #   * silicon.basemul(a,b) = (a * b) * R^{-1}      mod q  (one R^{-1})
    #
    # Round-trip: silicon.intt(silicon.ntt(f)) == R * f (verified by M32b
    # gate (a)).
    #
    # FIPS 203 (kyber-py, mlkem_composer.HostBackend) uses plain positive
    # residues throughout - no R factor anywhere.  To make silicon behave
    # identically to HostBackend from the composer's point of view, strip
    # the residual R from intt and add a compensating R to basemul:
    #
    #   * ntt      -> passthrough      (already plain)
    #   * intt     -> multiply by R^{-1} = 169  mod q
    #   * basemul  -> multiply by R    = 2285   mod q
    #
    # poly_add / poly_sub are Z_q-linear and need no bridging.
    #
    # References: pq-crystals/kyber ref/reduce.c (montgomery_reduce, R),
    # ref/ntt.c (Montgomery-pre-scaled ZETAS), FIPS 203 Algs 9/10/12.
    # ------------------------------------------------------------------
    _MONT_Q     = 3329
    _MONT_R     = (1 << 16) % 3329              # 2285
    _MONT_R_INV = pow((1 << 16) % 3329, -1, 3329)  # 169

    @classmethod
    def _scale_mod_q(cls, poly, factor):
        q = cls._MONT_Q
        return [(int(c) * factor) % q for c in poly]

    @classmethod
    def _reduce_to_plain(cls, poly):
        # Fold each int16 lane into [0, q). The pq-crystals ntt/invntt output
        # can sit in (-2q, 2q); poly_add / poly_sub use a single barrett_reduce
        # which lands in (-q/2, q/2]; poly_tobytes only applies one sign-add-q
        # (t += (t>>15) & q) and therefore requires already-reduced input.
        # A pure Python `% q` handles all cases uniformly.
        q = cls._MONT_Q
        return [int(c) % q for c in poly]

    def ntt(self, poly):
        # Plain-in; R cancels via Montgomery-pre-scaled ZETAS.  Output must be
        # reduced to [0, q) before it can be fed to poly_tobytes_d12 (M32d
        # only applies one conditional-add-q, insufficient for raw ntt output).
        out = self._m32b_unary(self._m32b_modes["ntt"], poly)
        return self._reduce_to_plain(out)

    def intt(self, poly):
        # Silicon output has one residual R factor. Strip with R^{-1}.
        out = self._m32b_unary(self._m32b_modes["intt"], poly)
        return self._scale_mod_q(out, self._MONT_R_INV)

    def multiply_ntts(self, a, b):
        # Silicon output has one residual R^{-1}. Compensate with R and reduce
        # so the downstream accumulator sees a proper positive residue.
        out = self._m32b_binary(self._m32b_modes["basemul"], a, b)
        return self._scale_mod_q(out, self._MONT_R)

    def poly_add(self, a, b):
        return self._m32b_binary(self._m32b_modes["add"], a, b)

    def poly_sub(self, a, b):
        return self._m32b_binary(self._m32b_modes["sub"], a, b)

    # ---- M32d dispatch helpers ------------------------------------------
    def _m32d_poly_to_bytes(self, mode: int, poly: list[int], out_len: int) -> bytes:
        dispatch, pack = self._m32d
        # M32d takes int16 lanes; bytes come out as low byte of int16 lanes.
        a = np.asarray(poly, dtype=np.int16)
        ctrl = pack(mode)
        out_lanes = dispatch(a, ctrl, tag=f"m32e/m32d mode={mode}")
        return bytes((int(v) & 0xFF) for v in out_lanes[:out_len])

    def _m32d_bytes_to_poly(self, mode: int, packed: bytes) -> list[int]:
        dispatch, pack = self._m32d
        # Bytes -> int16 lanes (byte in low byte).
        lanes = np.asarray(list(packed), dtype=np.int16)
        ctrl = pack(mode)
        out = dispatch(lanes, ctrl, tag=f"m32e/m32d mode={mode}")
        return [int(v) for v in out[:KYBER_N]]

    def compress_d4(self, poly):
        return self._m32d_poly_to_bytes(self._m32d_modes["compress_d4"], poly, 128)

    def decompress_d4(self, packed):
        return self._m32d_bytes_to_poly(self._m32d_modes["decompress_d4"], packed)

    def compress_d10(self, poly):
        return self._m32d_poly_to_bytes(self._m32d_modes["compress_d10"], poly, 320)

    def decompress_d10(self, packed):
        return self._m32d_bytes_to_poly(self._m32d_modes["decompress_d10"], packed)

    def poly_tobytes_d12(self, poly):
        return self._m32d_poly_to_bytes(self._m32d_modes["tobytes_d12"], poly, 384)

    def poly_frombytes_d12(self, packed):
        return self._m32d_bytes_to_poly(self._m32d_modes["frombytes_d12"], packed)

    def poly_frommsg(self, msg32):
        return self._m32d_bytes_to_poly(self._m32d_modes["frommsg"], msg32)

    def poly_tomsg(self, poly):
        return self._m32d_poly_to_bytes(self._m32d_modes["tomsg"], poly, 32)


# ------------------------------------------------------------------
# Vector loaders.
# ------------------------------------------------------------------

def _load_json(name: str):
    with open(VECTOR_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _hx(s: str) -> bytes:
    return bytes.fromhex(s)


def _keygen_kats():
    out = []
    p = _load_json("keygen_prompt.json")
    e = _load_json("keygen_expected.json")
    for tg_p, tg_e in zip(p["testGroups"], e["testGroups"]):
        if tg_p["parameterSet"] != "ML-KEM-512":
            continue
        exp_by_id = {t["tcId"]: t for t in tg_e["tests"]}
        for t in tg_p["tests"]:
            exp = exp_by_id[t["tcId"]]
            out.append({"tcId": t["tcId"], "d": _hx(t["d"]), "z": _hx(t["z"]),
                            "ek": _hx(exp["ek"]), "dk": _hx(exp["dk"])})
    return out


def _encap_kats():
    out = []
    p = _load_json("encapdecap_prompt.json")
    e = _load_json("encapdecap_expected.json")
    for tg_p, tg_e in zip(p["testGroups"], e["testGroups"]):
        if tg_p["parameterSet"] != "ML-KEM-512": continue
        if tg_p.get("function") != "encapsulation": continue
        exp_by_id = {t["tcId"]: t for t in tg_e["tests"]}
        for t in tg_p["tests"]:
            exp = exp_by_id[t["tcId"]]
            out.append({"tcId": t["tcId"], "ek": _hx(t["ek"]), "m": _hx(t["m"]),
                            "K": _hx(exp["k"]), "c": _hx(exp["c"])})
    return out


def _decap_kats():
    out = []
    p = _load_json("encapdecap_prompt.json")
    e = _load_json("encapdecap_expected.json")
    for tg_p, tg_e in zip(p["testGroups"], e["testGroups"]):
        if tg_p["parameterSet"] != "ML-KEM-512": continue
        if tg_p.get("function") != "decapsulation": continue
        exp_by_id = {t["tcId"]: t for t in tg_e["tests"]}
        for t in tg_p["tests"]:
            exp = exp_by_id[t["tcId"]]
            dk_bytes = _hx(t.get("dk") or tg_p.get("dk"))
            out.append({"tcId": t["tcId"], "dk": dk_bytes, "c": _hx(t["c"]),
                            "K": _hx(exp["k"])})
    return out


# ------------------------------------------------------------------
# Backend factory (env-driven).
# ------------------------------------------------------------------

def _backend_for_gate() -> tuple[Backend, str]:
    """Prefer silicon on the laptop; fall back to HostBackend in sandbox."""
    if _silicon_available() and os.environ.get("M32E_FORCE_HOST", "") != "1":
        return SiliconBackend(), "silicon"
    return HostBackend(), "host"


# ------------------------------------------------------------------
# Gate (a): Sandbox reference gate.  Composer HostBackend must be
# byte-exact against all 60 NIST ACVP KATs.  Always runs.
# ------------------------------------------------------------------

@pytest.mark.parametrize("kat", _keygen_kats(), ids=lambda k: f"kg{k['tcId']}")
def test_reference_keygen(kat):
    be = HostBackend()
    keys = mlkem_keygen_internal(be, kat["d"], kat["z"])
    assert keys.ek == kat["ek"], f"ek mismatch tcId={kat['tcId']}"
    assert keys.dk == kat["dk"], f"dk mismatch tcId={kat['tcId']}"


@pytest.mark.parametrize("kat", _encap_kats(), ids=lambda k: f"en{k['tcId']}")
def test_reference_encaps(kat):
    be = HostBackend()
    K, c = mlkem_encaps_internal(be, kat["ek"], kat["m"])
    assert K == kat["K"], f"K mismatch tcId={kat['tcId']}"
    assert c == kat["c"], f"c mismatch tcId={kat['tcId']}"


@pytest.mark.parametrize("kat", _decap_kats(), ids=lambda k: f"de{k['tcId']}")
def test_reference_decaps(kat):
    be = HostBackend()
    K = mlkem_decaps_internal(be, kat["dk"], kat["c"])
    assert K == kat["K"], f"K mismatch tcId={kat['tcId']}"


# ------------------------------------------------------------------
# Gate (b): Silicon-composed KeyGen against 3 NIST KATs.
# Skipped in sandbox.  On laptop, exercises M32b, M32c, M32d in one shot.
#
# The full 60-KAT gate is guarded by M32E_FULL_KAT=1 because each KAT
# dispatches roughly 30 (KG), 40 (Enc), or 70 (Dec) individual primitives
# to the NPU.  A 3-KAT smoke gate proves silicon composition works.
# ------------------------------------------------------------------

def _pick_kats(kats, env_var):
    if os.environ.get(env_var, "") == "1":
        return kats
    # Smoke set: first three vectors of each type.
    return kats[:3]


@pytest.mark.skipif(not _silicon_available(),
                    reason="aie.iron not available in sandbox")
@pytest.mark.parametrize("kat", _pick_kats(_keygen_kats(), "M32E_FULL_KAT"),
                         ids=lambda k: f"kg{k['tcId']}")
def test_silicon_keygen(kat):
    be, mode = _backend_for_gate()
    assert mode == "silicon"
    keys = mlkem_keygen_internal(be, kat["d"], kat["z"])
    assert keys.ek == kat["ek"], f"ek mismatch tcId={kat['tcId']}"
    assert keys.dk == kat["dk"], f"dk mismatch tcId={kat['tcId']}"


@pytest.mark.skipif(not _silicon_available(),
                    reason="aie.iron not available in sandbox")
@pytest.mark.parametrize("kat", _pick_kats(_encap_kats(), "M32E_FULL_KAT"),
                         ids=lambda k: f"en{k['tcId']}")
def test_silicon_encaps(kat):
    be, mode = _backend_for_gate()
    assert mode == "silicon"
    K, c = mlkem_encaps_internal(be, kat["ek"], kat["m"])
    assert K == kat["K"], f"K mismatch tcId={kat['tcId']}"
    assert c == kat["c"], f"c mismatch tcId={kat['tcId']}"


@pytest.mark.skipif(not _silicon_available(),
                    reason="aie.iron not available in sandbox")
@pytest.mark.parametrize("kat", _pick_kats(_decap_kats(), "M32E_FULL_KAT"),
                         ids=lambda k: f"de{k['tcId']}")
def test_silicon_decaps(kat):
    be, mode = _backend_for_gate()
    assert mode == "silicon"
    K = mlkem_decaps_internal(be, kat["dk"], kat["c"])
    assert K == kat["K"], f"K mismatch tcId={kat['tcId']}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"] + sys.argv[1:]))
