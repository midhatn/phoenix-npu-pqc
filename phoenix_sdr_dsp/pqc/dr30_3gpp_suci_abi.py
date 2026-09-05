# SPDX-License-Identifier: Apache-2.0
"""ABI definitions and descriptor structures for Milestone DR30:
3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor on AMD Phoenix AIE2.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

MAGIC_DESC_DR30 = 0x01305355  # DR30 SU (SUCI Co-Processor magic)

# 3GPP TS 33.501 Protection Scheme Identifiers
PROFILE_NULL            = 0  # Null Scheme (cleartext SUPI)
PROFILE_A_CURVE25519    = 1  # Profile A (X25519 ECIES)
PROFILE_B_SECP256R1     = 2  # Profile B (Secp256r1 ECIES)
PROFILE_C_MLKEM768      = 3  # Profile C (Post-Quantum ML-KEM-768)
PROFILE_D_MLKEM1024     = 4  # Profile D (Post-Quantum ML-KEM-1024)

# Hardware Operation Modes
MODE_SUCI_PARSE_VALIDATE   = 0  # Parse and validate 3GPP wire-format header fields
MODE_SUCI_DECAPSULATE_DERIVE = 1 # Decapsulate shared secret and derive K_enc / K_mac
MODE_SUCI_DECONCEAL_VERIFY = 2  # Decrypt MSIN/SUPI payload and authenticate MAC tag
MODE_SUCI_PIPELINE_FULL    = 3  # End-to-end atomic hardware de-concealment pipeline


class DR30Descriptor(NamedTuple):
    magic: int
    operation_mode: int
    profile_id: int
    hn_key_id: int
    suci_len: int
    epoch: int
    routing_indicator: int
    mcc_mnc: int


def pack_dr30_descriptor(
    operation_mode: int,
    profile_id: int = PROFILE_C_MLKEM768,
    hn_key_id: int = 1,
    suci_len: int = 0,
    epoch: int = 1,
    routing_indicator: int = 0x0001,
    mcc_mnc: int = 0x0310260,  # e.g., MCC 310, MNC 260
) -> bytes:
    """Packs 32-byte hardware descriptor for DR30 SUCI processing."""
    desc = bytearray(32)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR30,
        int(operation_mode),
        int(profile_id),
        int(hn_key_id),
        int(suci_len),
        int(epoch),
        int(routing_indicator),
        int(mcc_mnc),
    )
    return bytes(desc)


def unpack_dr30_descriptor(data: bytes) -> DR30Descriptor:
    if len(data) < 32:
        raise ValueError(f"Descriptor requires 32 bytes, received {len(data)}")
    magic, op_mode, prof_id, key_id, s_len, epoch, r_ind, net_id = struct.unpack_from("<IIIIIIII", data, 0)
    if magic != MAGIC_DESC_DR30:
        raise ValueError(f"Invalid DR30 magic: 0x{magic:08X} != 0x{MAGIC_DESC_DR30:08X}")
    return DR30Descriptor(
        magic=magic,
        operation_mode=op_mode,
        profile_id=prof_id,
        hn_key_id=key_id,
        suci_len=s_len,
        epoch=epoch,
        routing_indicator=r_ind,
        mcc_mnc=net_id,
    )
