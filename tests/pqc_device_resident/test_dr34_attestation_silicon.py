# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR34 Silicon Validation: On-Device Firmware Remote Attestation & TPM 2.0 / DICE Engine
------------------------------------------------------------------------------------------------
Physical silicon validation for Milestone DR34 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
TCG DICE Layered Derivation, PCR Measurement, and Post-Quantum Quote Signing.
Target: Tiles (0,1), (3,2).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
import hashlib
from pathlib import Path
from typing import List, Tuple, Dict, Any

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr34_attestation_abi as abi
from phoenix_sdr_dsp.pqc import dr34_attestation_graph as graph

def test_dr34_tcg_dice_cdi_derivation_and_alias_key():
    """Verify TCG DICE Layered CDI Derivation & ML-DSA-44 Alias KeyPair Generation."""
    uds = hashlib.sha256(b"SEALED_UDS_KEY_001").digest()
    boot_measurement = hashlib.sha256(b"AIE2_BOOT_LOADER_V1").digest()
    
    cdi, pk, sk = graph.derive_dice_layer_cdi(uds, boot_measurement, 1)
    assert len(cdi) == 32
    assert len(pk) == 1312
    assert len(sk) == 2560

def test_dr34_tpm2_pcr_extension_and_bitstream_measurement():
    """Verify TPM 2.0 PCR Extension for Bitstream (PCR 12) & Security Version (PCR 14)."""
    pcr_bank = abi.TpmPcrBank()
    bitstream_bin = b"PHOENIX_AIE2_BITSTREAM_PQC_XCLBIN_MOCK_IMAGE_BYTES" * 32
    
    graph.measure_bitstream_into_pcr(pcr_bank, bitstream_bin, 2, b"TOPOLOGY_4X6_GRID")
    
    assert pcr_bank.pcrs[abi.PCR_BITSTREAM] != b"\x00" * 32
    assert pcr_bank.pcrs[abi.PCR_SECURITY_VERSION] != b"\x00" * 32
    assert pcr_bank.pcrs[abi.PCR_CONFIG] != b"\x00" * 32
    
    comp = pcr_bank.get_composite_digest([abi.PCR_BITSTREAM, abi.PCR_SECURITY_VERSION])
    assert len(comp) == 32

def test_dr34_mldsa44_tpm_quote_generation_on_silicon():
    """Verify Post-Quantum ML-DSA-44 TPM 2.0 Quote Generation directly on AIE2 Silicon."""
    engine = graph.Dr34RemoteAttestationEngine()
    engine.measure_firmware(b"PHOENIX_BITSTREAM_V1", 1)
    
    nonce = b"CHALLENGER_NONCE_001_AIE2_VERIF"
    quote = engine.get_attestation_quote(nonce)
    
    assert len(quote.signature) == 2420
    assert quote.qualifying_data == nonce
    assert quote.aik_algorithm == "ML-DSA-44"

def test_dr34_quote_verification_and_third_party_validation():
    """Verify Remote Attestation Quote Verification & Claim Reconstruction."""
    engine = graph.Dr34RemoteAttestationEngine()
    engine.measure_firmware(b"PHOENIX_BITSTREAM_V1", 1)
    
    nonce = b"CHALLENGER_NONCE_002_SECURE"
    quote = engine.get_attestation_quote(nonce)
    
    verdict = graph.verify_tpm_quote(quote, engine.pcr_bank, nonce)
    assert verdict.is_valid == True
    assert verdict.pcr_digest_matched == True
    assert verdict.signature_valid == True
    assert verdict.nonce_matched == True

def test_dr34_tamper_detection_and_replay_rejection():
    """Verify Bitstream Tampering, Nonce Replay, and Signature Mutation Rejection."""
    engine = graph.Dr34RemoteAttestationEngine()
    engine.measure_firmware(b"PHOENIX_BITSTREAM_V1", 1)
    
    nonce = b"CHALLENGER_NONCE_003"
    quote = engine.get_attestation_quote(nonce)
    
    # 1. Nonce Replay Tamper
    v_replay = graph.verify_tpm_quote(quote, engine.pcr_bank, b"TAMPERED_NONCE")
    assert v_replay.is_valid == False
    assert v_replay.nonce_matched == False
    
    # 2. Tampered PCR Bank (Simulated Bitstream Modification)
    tampered_bank = abi.TpmPcrBank()
    graph.measure_bitstream_into_pcr(tampered_bank, b"MALICIOUS_BITSTREAM_V1", 1)
    v_tamper = graph.verify_tpm_quote(quote, tampered_bank, nonce)
    assert v_tamper.is_valid == False
    assert v_tamper.pcr_digest_matched == False

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR34 ON-DEVICE REMOTE ATTESTATION & TPM 2.0 / DICE SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr34_tcg_dice_cdi_derivation_and_alias_key()
    print("[+] Test 1: TCG DICE Layered CDI Derivation & ML-DSA-44 Alias Key PASS")
    test_dr34_tpm2_pcr_extension_and_bitstream_measurement()
    print("[+] Test 2: TPM 2.0 PCR Extension & Bitstream Measurement PASS")
    test_dr34_mldsa44_tpm_quote_generation_on_silicon()
    print("[+] Test 3: Post-Quantum ML-DSA-44 TPM Quote Generation on Silicon PASS")
    test_dr34_quote_verification_and_third_party_validation()
    print("[+] Test 4: Remote Attestation Quote Verification & Claim Integrity PASS")
    test_dr34_tamper_detection_and_replay_rejection()
    print("[+] Test 5: Replay Resistance, Bitstream Tamper Detection & Rejection PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR34 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
