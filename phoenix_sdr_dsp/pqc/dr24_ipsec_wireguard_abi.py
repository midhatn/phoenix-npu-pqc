# SPDX-License-Identifier: Apache-2.0
"""ABI definitions and descriptor structures for Milestone DR24:
RFC 9370 Multi-KEM IPsec / WireGuard Inline VPN Co-Processor on AMD Phoenix AIE2.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

MAGIC_DESC_DR24 = 0x01244957  # DR24 IPsec/WireGuard magic identifier

# Operation Modes
MODE_RFC9370_COMBINE  = 0  # Multi-KEM combiner (Classic DH + ML-KEM + optional QKD PSK)
MODE_WIREGUARD_ENCAPS = 1  # Packet encapsulation (AEAD encryption + anti-replay tag)
MODE_WIREGUARD_DECAPS = 2  # Packet decapsulation (AEAD decryption + replay check)
MODE_ASYNC_REKEY      = 3  # Continuous asynchronous rekey generation


class DR24Descriptor(NamedTuple):
    magic: int
    operation_mode: int
    payload_len: int
    seq_num: int
    epoch: int
    kem_mode: int  # 0: ML-KEM-512, 1: ML-KEM-768, 2: ML-KEM-1024


def pack_dr24_descriptor(
    operation_mode: int,
    payload_len: int,
    seq_num: int = 0,
    epoch: int = 1,
    kem_mode: int = 1,
) -> bytes:
    """Packs 32-byte hardware descriptor for DR24 tile processing."""
    desc = bytearray(32)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR24,
        int(operation_mode),
        int(payload_len),
        int(seq_num & 0xFFFFFFFF),
        int((seq_num >> 32) & 0xFFFFFFFF),
        int(epoch),
        int(kem_mode),
        0,  # Reserved padding
    )
    return bytes(desc)


def unpack_dr24_descriptor(data: bytes) -> DR24Descriptor:
    if len(data) < 32:
        raise ValueError(f"Descriptor requires 32 bytes, received {len(data)}")
    magic, op_mode, payload_len, seq_lo, seq_hi, epoch, kem_mode, _ = struct.unpack_from("<IIIIIIII", data, 0)
    if magic != MAGIC_DESC_DR24:
        raise ValueError(f"Invalid DR24 magic: 0x{magic:08X} != 0x{MAGIC_DESC_DR24:08X}")
    seq_num = seq_lo | (seq_hi << 32)
    return DR24Descriptor(
        magic=magic,
        operation_mode=op_mode,
        payload_len=payload_len,
        seq_num=seq_num,
        epoch=epoch,
        kem_mode=kem_mode,
    )
