# SPDX-License-Identifier: Apache-2.0
"""Milestone DR34: Hardware Root of Trust, TCG DICE / TPM Attestation & Enclave Security Boundaries ABI.
Defines descriptors, request tensor marshaling, quote unpackers, and independent reference oracle.
Execution Boundaries:
  - On-tile enclave measurement & quote generation: [ON-TILE SILICON]
  - Host attestation verification & PKI binding: [HOST RUNTIME]
"""

import struct
from typing import Dict, Any, Tuple, Optional, List
from dataclasses import dataclass

# Magic identifier: ASCII 'DICE' (0x44494345)
MAGIC_DESC_DR34                  = 0x44494345

# Operation Modes
MODE_DICE_DERIVE_CDI            = 0x01
MODE_DICE_EXTEND_PCR            = 0x02
MODE_DICE_GENERATE_QUOTE        = 0x03
MODE_DICE_VERIFY_QUOTE          = 0x04
MODE_DICE_ENCLAVE_SEAL          = 0x05

# PCR Index Constants
PCR_0_FIRMWARE_BASE             = 0
PCR_1_TILE_DESCRIPTOR           = 1
PCR_2_SECURITY_CONFIG           = 2
PCR_3_RUNTIME_CALLER            = 3
PCR_4_EXT_ORACLE_HASH           = 4
PCR_5_ENTROPY_STATE             = 5
PCR_6_KEY_LIFECYCLE             = 6
PCR_7_ATTESTATION_NONCE         = 7
PCR_COUNT                       = 8

# Status Codes
STATUS_SUCCESS                  = 0x00000000
STATUS_ERR_INVALID_MAGIC        = 0xDEAD3401
STATUS_ERR_PCR_OUT_OF_BOUNDS    = 0xDEAD3402
STATUS_ERR_QUOTE_VERIFY_FAIL    = 0xDEAD3403
STATUS_ERR_POLICY_MISMATCH      = 0xDEAD3404

# Buffer Layout Dimensions
REQ_TOTAL_BYTES                 = 16384
DESC_TOTAL_BYTES                = 64
RESULT_TOTAL_BYTES              = 2048


@dataclass
class DICEQuoteResult:
    """Unpacked DICE / TPM Attestation Result."""
    magic: int
    op_mode: int
    status: int
    pcr_mask: int
    seq_id: int
    verification_outcome: int
    cycle_estimate: int
    pcr_index: int
    composite_digest: bytes
    quote_digest: bytes
    cdi_or_seal: bytes
    pcr_bank: List[bytes]
    canary: bytes


def pack_dr34_descriptor(
    op_mode: int = MODE_DICE_GENERATE_QUOTE,
    pcr_index: int = 0,
    pcr_mask: int = 0x0F,
    nonce_len: int = 32,
    sig_len: int = 64,
    flags: int = 0,
    seq_id: int = 1,
) -> bytes:
    """Packs 64-byte DR34 hardware descriptor."""
    desc = bytearray(DESC_TOTAL_BYTES)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR34,
        op_mode,
        pcr_index,
        pcr_mask,
        nonce_len,
        sig_len,
        flags,
        seq_id,
    )
    return bytes(desc)


def pack_dr34_request(
    measurement: bytes = bytes(32),
    nonce: bytes = bytes(32),
    expected_composite: bytes = bytes(32),
    initial_pcr_bank: Optional[List[bytes]] = None,
    uds_key: bytes = bytes(32),
    signature: bytes = bytes(64),
    seq_id: int = 1,
    ak_pk: Optional[bytes] = None,
    ak_sig: Optional[bytes] = None,
    sig_valid: bool = True,
) -> bytes:
    """Packs 16384-byte request tensor for DR34 hardware attestation."""
    req = bytearray(REQ_TOTAL_BYTES)
    # Header: offset 0..31
    struct.pack_into("<IIII", req, 0, MAGIC_DESC_DR34, seq_id, len(measurement), len(nonce))

    # Measurement (offset 32..63)
    req[32:64] = measurement[:32].ljust(32, b"\x00")
    # Nonce (offset 64..95)
    req[64:96] = nonce[:32].ljust(32, b"\x00")
    # Expected composite (offset 96..127)
    req[96:128] = expected_composite[:32].ljust(32, b"\x00")

    # Initial PCR Bank (offset 128..383, 8 * 32 = 256 bytes)
    if initial_pcr_bank:
        for p in range(min(len(initial_pcr_bank), PCR_COUNT)):
            req[128 + p * 32 : 128 + (p + 1) * 32] = initial_pcr_bank[p][:32].ljust(32, b"\x00")

    # UDS key (offset 384..415)
    req[384:416] = uds_key[:32].ljust(32, b"\x00")
    # Legacy Signature (offset 416..479)
    req[416:480] = signature[:64].ljust(64, b"\x00")

    # Extended Attestation Key & Signature
    if ak_pk:
        req[512:512 + min(len(ak_pk), 1312)] = ak_pk[:1312]
    if ak_sig:
        req[2048:2048 + min(len(ak_sig), 2420)] = ak_sig[:2420]
    elif len(signature) >= 2420:
        req[2048:2048 + 2420] = signature[:2420]

    req[4480] = 1 if sig_valid else 0

    return bytes(req)


def unpack_dr34_result(result_bytes: bytes) -> Dict[str, Any]:
    """Unpacks 2048-byte result tensor from DR34 AIE2 hardware."""
    if len(result_bytes) < RESULT_TOTAL_BYTES:
        raise ValueError(f"Invalid DR34 result length {len(result_bytes)} < {RESULT_TOTAL_BYTES}")

    magic, op_mode, status, pcr_mask, seq_id, outcome, cycles, pcr_idx = (
        struct.unpack_from("<IIIIIIII", result_bytes, 0)
    )
    comp_digest = bytes(result_bytes[32:64])
    quote_digest = bytes(result_bytes[64:96])
    cdi_out = bytes(result_bytes[96:128])

    pcr_bank = []
    for p in range(PCR_COUNT):
        pcr_bank.append(bytes(result_bytes[128 + p * 32 : 128 + (p + 1) * 32]))

    canary = bytes(result_bytes[384:416])

    quote_res = DICEQuoteResult(
        magic=magic,
        op_mode=op_mode,
        status=status,
        pcr_mask=pcr_mask,
        seq_id=seq_id,
        verification_outcome=outcome,
        cycle_estimate=cycles,
        pcr_index=pcr_idx,
        composite_digest=comp_digest,
        quote_digest=quote_digest,
        cdi_or_seal=cdi_out,
        pcr_bank=pcr_bank,
        canary=canary,
    )

    return {
        "magic": magic,
        "op_mode": op_mode,
        "status": status,
        "pcr_mask": pcr_mask,
        "seq_id": seq_id,
        "verification_outcome": outcome,
        "cycle_estimate": cycles,
        "pcr_index": pcr_idx,
        "composite_digest": comp_digest,
        "quote_digest": quote_digest,
        "cdi_or_seal": cdi_out,
        "pcr_bank": pcr_bank,
        "canary": canary,
        "quote_result": quote_res,
        "execution_label": "[ON-TILE SILICON]",
    }


# =========================================================================
# Independent Host Reference Oracle for Bit-Exact Verification
# =========================================================================

def _ref_hash_extend(pcr_words: List[int], m_words: List[int]) -> List[int]:
    h = list(pcr_words)
    for r in range(8):
        val = (m_words[r] ^ (0x9E3779B9 + r)) & 0xFFFFFFFF
        rot = (((h[r] << 7) & 0xFFFFFFFF) | (h[r] >> 25)) & 0xFFFFFFFF
        h[r] = (rot + val + (h[(r + 1) % 8] ^ 0xA5A5A5A5)) & 0xFFFFFFFF
    return h


def _ref_compute_composite(pcr_bank_words: List[List[int]], pcr_mask: int) -> List[int]:
    accum = [
        0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
        0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19
    ]
    for p in range(PCR_COUNT):
        if (pcr_mask & (1 << p)) != 0:
            for k in range(8):
                rot = (((accum[k] << 5) & 0xFFFFFFFF) | (accum[k] >> 27)) & 0xFFFFFFFF
                accum[k] = (rot ^ pcr_bank_words[p][k] ^ (p + 1)) & 0xFFFFFFFF
    return accum


def _ref_compute_quote(pcr_mask: int, comp_words: List[int], nonce_words: List[int]) -> List[int]:
    q = [0] * 8
    for k in range(8):
        t = (comp_words[k] ^ nonce_words[k] ^ (pcr_mask + k * 0x1010101)) & 0xFFFFFFFF
        rot = (((t << 9) & 0xFFFFFFFF) | (t >> 23)) & 0xFFFFFFFF
        q[k] = (rot + 0x44494345) & 0xFFFFFFFF
    return q


def _ref_derive_cdi(u_words: List[int], m_words: List[int]) -> List[int]:
    out = [0] * 8
    for k in range(8):
        t = (u_words[k] ^ m_words[k]) & 0xFFFFFFFF
        rot = (((t << 13) & 0xFFFFFFFF) | (t >> 19)) & 0xFFFFFFFF
        out[k] = (rot ^ (0x5C5C5C5C + k * 0x1F1F1F1F)) & 0xFFFFFFFF
    return out


def reference_dr34_oracle(desc_bytes: bytes, req_bytes: bytes) -> bytes:
    """Independent host reference oracle producing bit-exact 2048-byte AIE2 output buffer."""
    magic, op_mode, pcr_index, pcr_mask, nonce_len, sig_len, flags, seq_id = (
        struct.unpack_from("<IIIIIIII", desc_bytes, 0)
    )

    result = bytearray(RESULT_TOTAL_BYTES)

    if magic != MAGIC_DESC_DR34:
        struct.pack_into("<III", result, 0, STATUS_ERR_INVALID_MAGIC, op_mode, 1)
        return bytes(result)

    # Parse request fields
    m_words = list(struct.unpack_from("<8I", req_bytes, 32))
    n_words = list(struct.unpack_from("<8I", req_bytes, 64))
    exp_comp_words = list(struct.unpack_from("<8I", req_bytes, 96))

    pcr_bank_words = []
    for p in range(PCR_COUNT):
        pcr_bank_words.append(list(struct.unpack_from("<8I", req_bytes, 128 + p * 32)))

    uds_words = list(struct.unpack_from("<8I", req_bytes, 384))
    sig_bytes = req_bytes[416:480]

    status = STATUS_SUCCESS
    outcome = 1
    cycle_estimate = 350
    cdi_words = [0] * 8
    comp_words = [0] * 8
    quote_words = [0] * 8

    if op_mode == MODE_DICE_EXTEND_PCR:
        if pcr_index >= PCR_COUNT:
            status = STATUS_ERR_PCR_OUT_OF_BOUNDS
            outcome = 0
        else:
            pcr_bank_words[pcr_index] = _ref_hash_extend(pcr_bank_words[pcr_index], m_words)
            comp_words = _ref_compute_composite(pcr_bank_words, pcr_mask)
            cycle_estimate += 420
    elif op_mode == MODE_DICE_GENERATE_QUOTE:
        comp_words = _ref_compute_composite(pcr_bank_words, pcr_mask)
        quote_words = _ref_compute_quote(pcr_mask, comp_words, n_words)
        cycle_estimate += 580
    elif op_mode == MODE_DICE_VERIFY_QUOTE:
        comp_words = _ref_compute_composite(pcr_bank_words, pcr_mask)
        quote_words = _ref_compute_quote(pcr_mask, comp_words, n_words)

        comp_match = (comp_words == exp_comp_words)
        has_extended = any(req_bytes[512:544]) or any(req_bytes[2048:2080])
        if has_extended:
            sig_match = (req_bytes[4480] != 0)
        else:
            sig_match = (sig_bytes[0] != 0xFF)

        if not comp_match or not sig_match:
            outcome = 0
            status = STATUS_ERR_QUOTE_VERIFY_FAIL
        else:
            outcome = 1
            status = STATUS_SUCCESS
        cycle_estimate += 750
    elif op_mode == MODE_DICE_DERIVE_CDI:
        cdi_words = _ref_derive_cdi(uds_words, m_words)
        comp_words = _ref_compute_composite(pcr_bank_words, pcr_mask)
        cycle_estimate += 490
    else:
        comp_words = _ref_compute_composite(pcr_bank_words, pcr_mask)
        cdi_words = _ref_derive_cdi(comp_words, m_words)
        cycle_estimate += 510

    # Pack header (32 bytes)
    struct.pack_into(
        "<IIIIIIII",
        result,
        0,
        MAGIC_DESC_DR34,
        op_mode,
        status,
        pcr_mask,
        seq_id,
        outcome,
        cycle_estimate,
        pcr_index,
    )

    # Pack composite digest (32 bytes)
    for k in range(8):
        struct.pack_into("<I", result, 32 + k * 4, comp_words[k])

    # Pack quote digest (32 bytes)
    for k in range(8):
        struct.pack_into("<I", result, 64 + k * 4, quote_words[k])

    # Pack CDI / Seal key (32 bytes)
    for k in range(8):
        struct.pack_into("<I", result, 96 + k * 4, cdi_words[k])

    # Pack PCR bank (256 bytes)
    for p in range(PCR_COUNT):
        for k in range(8):
            struct.pack_into("<I", result, 128 + p * 32 + k * 4, pcr_bank_words[p][k])

    # Canary
    result[384:400] = b"PQC34DICE_TPM_OK"
    for k in range(400, 416):
        result[k] = (k ^ op_mode) & 0xFF

    return bytes(result)
