# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator on AMD Phoenix NPU (AIE2).
-----------------------------------------------------------------------------------------
Chains DR16 (ETSI 014 Ingress) -> DR17 (ML-DSA Auth) -> DR5-DR8 (ML-KEM KEM) ->
       DR18 (SP 800-56C Combiner) -> DR10 (Hardware Zeroization).
"""

import base64
import json
import secrets
import time
import uuid
from typing import NamedTuple, Tuple
from hashlib import shake_256

from . import dr16_etsi_qkd014_abi as dr16_abi
from . import dr16_etsi_qkd014_graph as dr16_graph
from . import dr17_mldsa_qkd_auth_abi as dr17_abi
from . import dr17_mldsa_qkd_auth_graph as dr17_graph
from . import dr18_dual_key_combiner_graph as dr18_graph
from . import dr10_sealed_lifecycle_graph as dr10_graph
from . import dr10_sealed_lifecycle_abi as dr10_abi
from . import dr5_mlkem512_keygen_graph as kg512
from . import dr6_mlkem512_encaps_graph as enc512
from . import dr7_mlkem512_decaps_graph as dec512
from . import dr8_mlkem768_keygen_graph as kg768
from . import dr8_mlkem768_encaps_graph as enc768
from . import dr8_mlkem768_decaps_graph as dec768
from . import dr8_mlkem1024_keygen_graph as kg1024
from . import dr8_mlkem1024_encaps_graph as enc1024
from . import dr8_mlkem1024_decaps_graph as dec1024
from . import dr11_mldsa44_keygen_graph as mldsa_kg44
from . import dr12_mldsa44_sign_graph as mldsa_sign44
from . import dr14_mldsa65_keygen_graph as mldsa_kg65
from . import dr14_mldsa65_sign_graph as mldsa_sign65

class HybridSessionResult(NamedTuple):
    session_id: uuid.UUID
    k_final_master: bytes
    k_final_slave: bytes
    is_authenticated: bool
    is_key_matched: bool
    total_latency_ms: float
    zeroized_status: int

def run_hybrid_handshake_on_aie2(
    kem_param: str = "ML-KEM-512",
    dsa_param: str = "ML-DSA-44",
    epoch: int = 1000
) -> HybridSessionResult:
    """Execute complete dual-node Hybrid QKD + PQC handshake on physical AIE2 silicon."""
    t0 = time.time()
    session_key_id = uuid.uuid4()
    raw_qkd_secret = secrets.token_bytes(32)

    # 1. Node B (Slave) generates ML-KEM and ML-DSA Identity KeyPairs on AIE2
    if kem_param == "ML-KEM-512":
        ek_kem, dk_kem = kg512.run_mlkem512_keygen(secrets.token_bytes(32), secrets.token_bytes(32))
    elif kem_param == "ML-KEM-768":
        ek_kem, dk_kem = kg768.run_mlkem768_keygen(secrets.token_bytes(32), secrets.token_bytes(32))
    else:
        ek_kem, dk_kem = kg1024.run_mlkem1024_keygen(secrets.token_bytes(32), secrets.token_bytes(32))

    if dsa_param == "ML-DSA-44":
        pk_dsa, sk_dsa = mldsa_kg44.run_mldsa44_keygen(secrets.token_bytes(32))
    else:
        pk_dsa, sk_dsa = mldsa_kg65.run_mldsa65_keygen(secrets.token_bytes(32))

    # 2. Node A (Master) ingests QKD Key via ETSI GS QKD 014 (DR16)
    container_json = json.dumps({
        "keys": [{"key_ID": str(session_key_id), "key": base64.b64encode(raw_qkd_secret).decode("ascii")}]
    })
    parsed_qkd = dr16_abi.parse_etsi_014_json(container_json, epoch=epoch)
    k_qkd_node_a = parsed_qkd[0].key_bytes

    desc_a = dr16_abi.pack_dr16_descriptor(session_key_id, epoch, len(k_qkd_node_a))
    req_a = dr16_abi.pack_dr16_request(k_qkd_node_a)
    dr16_graph.run_dr16_ingress_service(req_a, desc_a)

    # 3. Node A signs QKD session manifest using ML-DSA (DR17)
    nonce = secrets.token_bytes(12)
    manifest = dr17_abi.pack_dr17_manifest("SAE_MASTER", "SAE_SLAVE", session_key_id, epoch, nonce)

    if dsa_param == "ML-DSA-44":
        sig_dsa = mldsa_sign44.run_mldsa44_sign(sk_dsa, manifest)
    else:
        tr = shake_256(pk_dsa).digest(64)
        mu = shake_256(tr + manifest).digest(64)
        sig_dsa = mldsa_sign65.run_mldsa65_sign(sk_dsa, mu, external_mu=True)

    # 4. Node B verifies ML-DSA signature on AIE2 before proceeding
    is_auth_valid, _, _ = dr17_graph.verify_qkd_manifest_on_aie2(
        dsa_param, pk_dsa, "SAE_MASTER", "SAE_SLAVE", session_key_id, epoch, nonce, sig_dsa
    )

    if not is_auth_valid:
        return HybridSessionResult(session_key_id, b"", b"", False, False, (time.time() - t0)*1000, -1)

    # 5. Node A encapsulates ML-KEM shared secret on AIE2
    m_rand = secrets.token_bytes(32)
    if kem_param == "ML-KEM-512":
        ct_pqc, ss_pqc_master = enc512.run_mlkem512_encaps(ek_kem, m_rand)
        ss_pqc_slave = dec512.run_mlkem512_decaps(dk_kem, ct_pqc)
    elif kem_param == "ML-KEM-768":
        ct_pqc, ss_pqc_master = enc768.run_mlkem768_encaps(ek_kem, m_rand)
        ss_pqc_slave = dec768.run_mlkem768_decaps(dk_kem, ct_pqc)
    else:
        ct_pqc, ss_pqc_master = enc1024.run_mlkem1024_encaps(ek_kem, m_rand)
        ss_pqc_slave = dec1024.run_mlkem1024_decaps(dk_kem, ct_pqc)

    # 6. Both Nodes fuse K_QKD and K_PQC via NIST SP 800-56C Dual Combiner (DR18)
    k_final_master, _ = dr18_graph.combine_keys_on_aie2(k_qkd_node_a, ss_pqc_master, session_key_id, epoch=epoch)
    k_final_slave, _ = dr18_graph.combine_keys_on_aie2(raw_qkd_secret, ss_pqc_slave, session_key_id, epoch=epoch)

    # 7. Session Teardown & DR10 Zeroization
    req_zero = bytes(256)
    desc_zero = dr10_abi.pack_dr10_descriptor(dr10_abi.SOURCE_MODE_SEALED_SESSION, 1, request_id=epoch, epoch=epoch)
    _, zero_status, _, _ = dr10_graph.run_dr10_service(req_zero, desc_zero)

    total_time = (time.time() - t0) * 1000
    is_match = (k_final_master == k_final_slave) and (len(k_final_master) == 32)

    return HybridSessionResult(
        session_id=session_key_id,
        k_final_master=k_final_master,
        k_final_slave=k_final_slave,
        is_authenticated=is_auth_valid,
        is_key_matched=is_match,
        total_latency_ms=total_time,
        zeroized_status=zero_status
    )
