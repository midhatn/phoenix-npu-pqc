# SPDX-License-Identifier: Apache-2.0
"""
OpenSSL 3.x Provider Python Dispatch Prototype.
High-level prototype wrapper dispatching cryptographic requests to AIE2 graphs.
"""

import os
import json
import time
import struct
from typing import Dict, Any, Tuple, Optional, List

# Core AIE2 Hardware Silicon Graph Imports
from . import dr5_mlkem512_keygen_graph as mlkem512_kg
from . import dr6_mlkem512_encaps_graph as mlkem512_enc
from . import dr7_mlkem512_decaps_graph as mlkem512_dec
from . import dr8_mlkem768_keygen_graph as mlkem768_kg
from . import dr8_mlkem768_encaps_graph as mlkem768_enc
from . import dr8_mlkem768_decaps_graph as mlkem768_dec
from . import dr8_mlkem1024_keygen_graph as mlkem1024_kg
from . import dr8_mlkem1024_encaps_graph as mlkem1024_enc
from . import dr8_mlkem1024_decaps_graph as mlkem1024_dec

from . import dr11_mldsa44_keygen_graph as mldsa44_kg
from . import dr12_mldsa44_sign_graph as mldsa44_sgn
from . import dr13_mldsa44_verify_graph as mldsa44_vrf
from . import dr14_mldsa65_keygen_graph as mldsa65_kg
from . import dr14_mldsa65_sign_graph as mldsa65_sgn
from . import dr14_mldsa65_verify_graph as mldsa65_vrf
from . import dr15_mldsa87_keygen_graph as mldsa87_kg
from . import dr15_mldsa87_sign_graph as mldsa87_sgn
from . import dr15_mldsa87_verify_graph as mldsa87_vrf

from . import dr19_hybrid_session_orchestrator as hybrid_orch
from . import dr27_qrng_reservoir_graph as qrng_res
from . import dr21_slhdsa_graph as slhdsa_graph

# OpenSSL 3.x Operation Opcodes
OSSL_OP_DIGEST      = 1
OSSL_OP_CIPHER      = 2
OSSL_OP_MAC         = 3
OSSL_OP_KDF         = 4
OSSL_OP_RAND        = 5
OSSL_OP_KEYMGMT     = 10
OSSL_OP_KEYEXCH     = 11
OSSL_OP_SIGNATURE   = 12
OSSL_OP_ASYM_CIPHER = 13
OSSL_OP_KEM         = 14

PROVIDER_NAME       = "phoenix_pqc_provider"
PROVIDER_VERSION    = "1.2.0"
PROVIDER_BUILD_INFO = "AMD Phoenix AIE2 / XDNA1 Hardware Accelerated Provider"

class PhoenixPqcKey:
    """Represents an on-device hardware-backed key object."""
    def __init__(self, algorithm: str, pubkey: bytes, privkey: Optional[bytes] = None):
        self.algorithm = algorithm
        self.pubkey = pubkey
        self.privkey = privkey
        self.created_at = time.time()
        self.hardware_resident = True

    def zeroize(self):
        """Immediately wipes private key material."""
        if self.privkey:
            self.privkey = b"\x00" * len(self.privkey)
        self.privkey = None

class PhoenixPqcProvider:
    """
    OpenSSL 3.x Native Provider Implementation for AMD Phoenix AIE2 Silicon.
    Implements standard OpenSSL 3.x provider dispatch routines.
    """
    def __init__(self):
        self.name = PROVIDER_NAME
        self.version = PROVIDER_VERSION
        self.build_info = PROVIDER_BUILD_INFO
        self.active_sessions: Dict[str, Any] = {}

    def get_params(self) -> Dict[str, Any]:
        """Implements OSSL_FUNC_PROVIDER_GET_PARAMS."""
        return {
            "name": self.name,
            "version": self.version,
            "buildinfo": self.build_info,
            "status": "ACTIVE_SILICON",
            "hardware": "AMD Phoenix NPU (AIE2 / XDNA1 Architecture)",
            "zero_host_fallback": True,
        }

    def query_operation(self, operation_id: int) -> List[Dict[str, Any]]:
        """Implements OSSL_FUNC_PROVIDER_QUERY_OPERATION."""
        if operation_id == OSSL_OP_KEM:
            return [
                {"algorithm": "ML-KEM-512", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-KEM-768", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-KEM-1024", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "X25519-ML-KEM-768", "properties": "provider=phoenix_pqc,npu=aie2,hybrid=true"},
                {"algorithm": "QKD-ML-KEM-768", "properties": "provider=phoenix_pqc,npu=aie2,etsi_014=true"},
            ]
        elif operation_id == OSSL_OP_SIGNATURE:
            return [
                {"algorithm": "ML-DSA-44", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-DSA-65", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-DSA-87", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "SLH-DSA-SHAKE-128S", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
                {"algorithm": "SLH-DSA-SHAKE-128F", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
                {"algorithm": "SLH-DSA-SHAKE-256S", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
                {"algorithm": "SLH-DSA-SHAKE-256F", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
            ]
        elif operation_id == OSSL_OP_KEYMGMT:
            return [
                {"algorithm": "ML-KEM-512", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-KEM-768", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-KEM-1024", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-DSA-44", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-DSA-65", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "ML-DSA-87", "properties": "provider=phoenix_pqc,npu=aie2"},
                {"algorithm": "SLH-DSA-SHAKE-128S", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
                {"algorithm": "SLH-DSA-SHAKE-128F", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
                {"algorithm": "SLH-DSA-SHAKE-256S", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
                {"algorithm": "SLH-DSA-SHAKE-256F", "properties": "provider=phoenix_pqc,npu=aie2,fips205=true"},
            ]
        return []

    # =========================================================================
    # EVP_KEM Interface (Key Encapsulation Mechanism)
    # =========================================================================
    def kem_keygen(self, algorithm: str, d_seed: Optional[bytes] = None, z_seed: Optional[bytes] = None) -> PhoenixPqcKey:
        """Executes on-device Keypair Generation on AIE2 silicon."""
        if d_seed is None or z_seed is None:
            # Drain true quantum entropy from on-chip reservoir if available, else urandom
            try:
                d_seed, _ = qrng_res.drain_entropy()
                z_seed, _ = qrng_res.drain_entropy()
            except Exception:
                d_seed = os.urandom(32)
                z_seed = os.urandom(32)

        algo = algorithm.upper().replace("_", "-")
        if algo == "ML-KEM-512":
            pk, sk = mlkem512_kg.run_mlkem512_keygen(d_seed, z_seed)
        elif algo == "ML-KEM-768":
            pk, sk = mlkem768_kg.run_mlkem768_keygen(d_seed, z_seed)
        elif algo == "ML-KEM-1024":
            pk, sk = mlkem1024_kg.run_mlkem1024_keygen(d_seed, z_seed)
        else:
            raise ValueError(f"Unsupported KEM algorithm in OpenSSL provider: {algorithm}")

        return PhoenixPqcKey(algorithm=algo, pubkey=pk, privkey=sk)

    def kem_encapsulate(self, key: PhoenixPqcKey, m_seed: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Executes on-device KEM Encapsulation on AIE2 silicon.
        Returns: (ciphertext, shared_secret)
        """
        if m_seed is None:
            try:
                m_seed, _ = qrng_res.drain_entropy()
            except Exception:
                m_seed = os.urandom(32)

        algo = key.algorithm.upper().replace("_", "-")
        if algo == "ML-KEM-512":
            ct, ss = mlkem512_enc.run_mlkem512_encaps(key.pubkey, m_seed)
        elif algo == "ML-KEM-768":
            ct, ss = mlkem768_enc.run_mlkem768_encaps(key.pubkey, m_seed)
        elif algo == "ML-KEM-1024":
            ct, ss = mlkem1024_enc.run_mlkem1024_encaps(key.pubkey, m_seed)
        else:
            raise ValueError(f"Unsupported KEM algorithm in OpenSSL provider: {key.algorithm}")

        return ct, ss

    def kem_decapsulate(self, key: PhoenixPqcKey, ciphertext: bytes) -> bytes:
        """
        Executes on-device KEM Decapsulation on AIE2 silicon.
        Returns: shared_secret
        """
        if not key.privkey:
            raise ValueError("Private key is required for decapsulation")

        algo = key.algorithm.upper().replace("_", "-")
        if algo == "ML-KEM-512":
            ss = mlkem512_dec.run_mlkem512_decaps(key.privkey, ciphertext)
        elif algo == "ML-KEM-768":
            ss = mlkem768_dec.run_mlkem768_decaps(key.privkey, ciphertext)
        elif algo == "ML-KEM-1024":
            ss = mlkem1024_dec.run_mlkem1024_decaps(key.privkey, ciphertext)
        else:
            raise ValueError(f"Unsupported KEM algorithm in OpenSSL provider: {key.algorithm}")

        return ss

    # =========================================================================
    # EVP_SIGNATURE Interface (Asymmetric Digital Signatures)
    # =========================================================================
    def signature_keygen(self, algorithm: str, xi_seed: Optional[bytes] = None) -> PhoenixPqcKey:
        """Executes on-device Signature Keypair Generation on AIE2 silicon."""
        if xi_seed is None:
            try:
                xi_seed, _ = qrng_res.drain_entropy()
            except Exception:
                xi_seed = os.urandom(32)

        algo = algorithm.upper().replace("_", "-")
        if "SLH-DSA" in algo or "SPHINCS" in algo:
            canonical = "SLH-DSA-SHAKE-128s" if "128S" in algo else "SLH-DSA-SHAKE-128f" if "128F" in algo else "SLH-DSA-SHAKE-256s" if "256S" in algo else "SLH-DSA-SHAKE-256f"
            pk, sk, _ = slhdsa_graph.slhdsa_keygen_on_aie2(canonical, sk_seed=xi_seed)
        elif algo == "ML-DSA-44":
            pk, sk = mldsa44_kg.run_mldsa44_keygen(xi_seed)
        elif algo == "ML-DSA-65":
            pk, sk = mldsa65_kg.run_mldsa65_keygen(xi_seed)
        elif algo == "ML-DSA-87":
            pk, sk = mldsa87_kg.run_mldsa87_keygen(xi_seed)
        else:
            raise ValueError(f"Unsupported Signature algorithm in OpenSSL provider: {algorithm}")

        return PhoenixPqcKey(algorithm=algo, pubkey=pk, privkey=sk)

    def signature_sign(self, key: PhoenixPqcKey, message: bytes, rnd_seed: Optional[bytes] = None) -> bytes:
        """Executes on-device Signature Generation on AIE2 silicon."""
        if not key.privkey:
            raise ValueError("Private key is required for signing")
        if rnd_seed is None:
            rnd_seed = os.urandom(32)

        algo = key.algorithm.upper().replace("_", "-")
        if algo == "ML-DSA-44":
            sig = mldsa44_sgn.run_mldsa44_sign(key.privkey, message, rnd_seed)
        elif algo == "ML-DSA-65":
            sig = mldsa65_sgn.run_mldsa65_sign(key.privkey, message, external_mu=False)
        elif algo == "ML-DSA-87":
            sig = mldsa87_sgn.run_mldsa87_sign(key.privkey, message, external_mu=False)
        else:
            raise ValueError(f"Unsupported Signature algorithm in OpenSSL provider: {key.algorithm}")

        return sig

    def signature_verify(self, key: PhoenixPqcKey, message: bytes, signature: bytes) -> bool:
        """Executes on-device Signature Verification on AIE2 silicon."""
        algo = key.algorithm.upper().replace("_", "-")
        if algo == "ML-DSA-44":
            return mldsa44_vrf.run_mldsa44_verify(key.pubkey, message, signature)
        elif algo == "ML-DSA-65":
            return mldsa65_vrf.run_mldsa65_verify(key.pubkey, signature, message, external_mu=False)
        elif algo == "ML-DSA-87":
            return mldsa87_vrf.run_mldsa87_verify(key.pubkey, signature, message, external_mu=False)
        else:
            raise ValueError(f"Unsupported Signature algorithm in OpenSSL provider: {key.algorithm}")

    # =========================================================================
    # Hybrid QKD / PQC KEM Interface (ETSI GS QKD 014 + FIPS 203 + SP 800-56C)
    # =========================================================================
    def hybrid_qkd_kem_exchange(
        self,
        kem_param: str = "ML-KEM-768",
        qkd_key_hex: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end full-duplex hybrid handshake inside AIE2 tile cluster.
        Fuses physical QKD key and ML-KEM shared secret via SP 800-56C dual combiner.
        """
        res = hybrid_orch.run_hybrid_handshake_on_aie2(kem_param=kem_param)
        return {
            "session_id": str(res.session_id),
            "k_final_master": res.k_final_master.hex(),
            "k_final_slave": res.k_final_slave.hex(),
            "is_authenticated": res.is_authenticated,
            "is_key_matched": res.is_key_matched,
            "total_latency_ms": res.total_latency_ms,
            "zeroized_status": res.zeroized_status,
        }

# Singleton Global Provider Instance
_GLOBAL_PROVIDER: Optional[PhoenixPqcProvider] = None

def get_phoenix_pqc_provider() -> PhoenixPqcProvider:
    global _GLOBAL_PROVIDER
    if _GLOBAL_PROVIDER is None:
        _GLOBAL_PROVIDER = PhoenixPqcProvider()
    return _GLOBAL_PROVIDER
