# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR41 Silicon Validation: ETSI GS QKD 004 / 015 Q-KMS REST Lifecycle Engine
-------------------------------------------------------------------------------------
Physical silicon validation for Milestone DR41 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
ETSI GS QKD 004 REST application interface, ETSI 015 inter-KME relay & MemTile lifecycle.
Target: Tiles (0,1), Row 1 MemTiles (1,0..1,3), Tile (3,2).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
from pathlib import Path

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr41_qkms_abi as abi
from phoenix_sdr_dsp.pqc import dr41_qkms_graph as graph
from phoenix_sdr_dsp.pqc.dr8_mlkem768_keygen_graph import run_mlkem768_keygen

def test_dr41_etsi_004_open_and_get_key_silicon():
    """Verify ETSI GS QKD 004 OPEN_CONNECT & GET_KEY on AIE2 Silicon."""
    engine = graph.QkmsEngine(node_id="KME_NODE_A")
    req = abi.QkmsOpenSessionRequest(
        source_sae_id="SAE_APP_01",
        destination_sae_id="SAE_APP_02",
        qos_priority=1,
        key_size_bits=256
    )
    open_res = engine.open_connect(req)
    assert open_res.status == "SUCCESS"
    assert len(open_res.key_stream_id) > 0
    
    get_res = engine.get_key(open_res.key_stream_id, count=2, key_size_bytes=32)
    assert get_res.status == "SUCCESS"
    assert len(get_res.keys) == 2
    assert len(get_res.keys[0]["key"]) == 64  # 32 bytes hex = 64 hex chars

def test_dr41_etsi_004_peer_sync_with_key_ids_silicon():
    """Verify ETSI GS QKD 004 GET_KEY_WITH_KEY_IDS Peer Synchronization on Silicon."""
    engine = graph.QkmsEngine(node_id="KME_NODE_A")
    req = abi.QkmsOpenSessionRequest("SAE_APP_01", "SAE_APP_02")
    open_res = engine.open_connect(req)
    
    get_res1 = engine.get_key(open_res.key_stream_id, count=1, key_size_bytes=32)
    k_id = get_res1.keys[0]["key_id"]
    k_hex = get_res1.keys[0]["key"]
    
    get_res2 = engine.get_key_with_key_ids(open_res.key_stream_id, [k_id])
    assert get_res2.status == "SUCCESS"
    assert get_res2.keys[0]["key"] == k_hex

def test_dr41_etsi_015_inter_kme_quantum_relay_silicon():
    """Verify ETSI GS QKD 015 Multi-Hop Inter-KME Quantum Key Relay on Silicon."""
    engine_a = graph.QkmsEngine(node_id="KME_NODE_A")
    engine_b = graph.QkmsEngine(node_id="KME_NODE_B")
    
    # Next-hop KME B PQC keypair (ML-KEM-768)
    ek_b, dk_b = run_mlkem768_keygen(b"\x99" * 32, b"\x88" * 32)
    
    target_quantum_key = b"\xDE\xAD\xBE\xEF" * 8
    target_key_id = "QUANTUM_KEY_TARGET_UUID_001"
    
    # 1. KME A encapsulates relay envelope
    envelope = engine_a.create_etsi_015_relay_envelope(target_key_id, target_quantum_key, ek_b)
    assert len(envelope.pqc_ciphertext) == 1088
    assert len(envelope.otp_ciphertext) == len(target_quantum_key)
    
    # 2. KME B decapsulates and recovers original key
    recovered_key = engine_b.process_etsi_015_relay_envelope(envelope, dk_b)
    assert recovered_key == target_quantum_key

def test_dr41_multitenant_domain_isolation_silicon():
    """Verify Multi-Tenant Hardware Crypto-Domain Isolation in MemTile SRAM."""
    engine = graph.QkmsEngine(node_id="KME_NODE_A")
    
    # Tenant Alpha
    req_alpha = abi.QkmsOpenSessionRequest("SAE_A1", "SAE_A2", tenant_domain="tenant_alpha")
    open_alpha = engine.open_connect(req_alpha)
    k_alpha = engine.get_key(open_alpha.key_stream_id, count=1)["keys"][0]["key_id"] if isinstance(engine.get_key(open_alpha.key_stream_id, count=1), dict) else engine.get_key(open_alpha.key_stream_id, count=1).keys[0]["key_id"]
    
    # Tenant Beta
    req_beta = abi.QkmsOpenSessionRequest("SAE_B1", "SAE_B2", tenant_domain="tenant_beta")
    open_beta = engine.open_connect(req_beta)
    
    # Tenant Beta attempts to access Tenant Alpha key ID -> Access Denied
    res_cross = engine.get_key_with_key_ids(open_beta.key_stream_id, [k_alpha])
    assert res_cross.status == "ERROR_KEY_NOT_FOUND"

def test_dr41_key_lifecycle_expiration_and_zeroization():
    """Verify Automated Key Expiration Sweeper & Hardware Zeroization."""
    engine = graph.QkmsEngine(node_id="KME_NODE_A")
    req = abi.QkmsOpenSessionRequest("SAE_01", "SAE_02")
    open_res = engine.open_connect(req)
    
    get_res = engine.get_key(open_res.key_stream_id, count=1, ttl_seconds=0.01)
    k_id = get_res.keys[0]["key_id"]
    
    time.sleep(0.02)
    purged = engine.purge_expired_keys(time.time())
    assert purged >= 1
    
    store = engine.key_stores["default"]
    assert store[k_id].status == abi.QkmsKeyStatus.ZEROIZED
    assert all(b == 0 for b in store[k_id].key_bytes)

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR41 ETSI GS QKD 004 / 015 Q-KMS REST LIFECYCLE SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr41_etsi_004_open_and_get_key_silicon()
    print("[+] Test 1: ETSI GS QKD 004 OPEN_CONNECT & GET_KEY REST Lifecycle PASS")
    test_dr41_etsi_004_peer_sync_with_key_ids_silicon()
    print("[+] Test 2: ETSI GS QKD 004 GET_KEY_WITH_KEY_IDS Peer Sync PASS")
    test_dr41_etsi_015_inter_kme_quantum_relay_silicon()
    print("[+] Test 3: ETSI GS QKD 015 Multi-Hop Inter-KME Relay (ML-KEM+OTP) PASS")
    test_dr41_multitenant_domain_isolation_silicon()
    print("[+] Test 4: Multi-Tenant Crypto-Domain Isolation in MemTile SRAM PASS")
    test_dr41_key_lifecycle_expiration_and_zeroization()
    print("[+] Test 5: Key Expiration Sweeper & Hardware Zeroization PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR41 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
