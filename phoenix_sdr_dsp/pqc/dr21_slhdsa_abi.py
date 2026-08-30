# SPDX-License-Identifier: Apache-2.0
"""
NIST FIPS 205 (SLH-DSA / SPHINCS+) Parameter Definitions and Types.
Compliant with NIST FIPS PUB 205 (August 2024).
"""

import struct
from dataclasses import dataclass
from typing import Dict, Tuple

MAGIC_DESC_DR21 = b"\x01\x21\x53\x48"  # DR21 Descriptor Magic
MAGIC_RESULT_DR21 = b"SL21"                # DR21 Result Magic

# ADRS Type Constants (NIST FIPS 205 Section 4.2)
ADRS_TYPE_WOTS_HASH  = 0
ADRS_TYPE_WOTS_PK    = 1
ADRS_TYPE_TREE       = 2
ADRS_TYPE_FORS_TREE  = 3
ADRS_TYPE_FORS_ROOTS = 4
ADRS_TYPE_WOTS_PRF   = 5
ADRS_TYPE_FORS_PRF   = 6

@dataclass(frozen=True)
class SlhdsaParams:
    name: str
    n: int       # Security parameter in bytes (hash output length: 16, 24, 32)
    h: int       # Total hypertree height (63, 66, 64, 68)
    d: int       # Number of hypertree layers (7, 22, 8, 17)
    hp: int      # Height of each sub-tree (h/d)
    a: int       # FORS trees height (12, 6, 14, 8)
    k: int       # Number of FORS trees (14, 33, 17, 35)
    w: int       # Winternitz parameter (16)
    len1: int    # WOTS+ number of base-w digits (2*n for w=16)
    len2: int    # WOTS+ checksum digits (3 for 128-bit, 3 for 256-bit)
    len_total: int # len1 + len2
    pk_bytes: int # PK.seed (n) + PK.root (n) = 2*n
    sk_bytes: int # SK.seed (n) + SK.prf (n) + PK.seed (n) + PK.root (n) = 4*n
    sig_bytes: int # R (n) + FORS_SIG (k*(1+a)*n) + HT_SIG (d*(len*n + hp*n))

SLHDSA_PARAMS: Dict[str, SlhdsaParams] = {
    "SLH-DSA-SHAKE-128s": SlhdsaParams(
        name="SLH-DSA-SHAKE-128s",
        n=16, h=63, d=7, hp=9, a=12, k=14, w=16,
        len1=32, len2=3, len_total=35,
        pk_bytes=32, sk_bytes=64, sig_bytes=7856
    ),
    "SLH-DSA-SHAKE-128f": SlhdsaParams(
        name="SLH-DSA-SHAKE-128f",
        n=16, h=66, d=22, hp=3, a=6, k=33, w=16,
        len1=32, len2=3, len_total=35,
        pk_bytes=32, sk_bytes=64, sig_bytes=17088
    ),
    "SLH-DSA-SHAKE-256s": SlhdsaParams(
        name="SLH-DSA-SHAKE-256s",
        n=32, h=64, d=8, hp=8, a=14, k=17, w=16,
        len1=64, len2=3, len_total=67,
        pk_bytes=64, sk_bytes=128, sig_bytes=29792
    ),
    "SLH-DSA-SHAKE-256f": SlhdsaParams(
        name="SLH-DSA-SHAKE-256f",
        n=32, h=68, d=17, hp=4, a=8, k=35, w=16,
        len1=64, len2=3, len_total=67,
        pk_bytes=64, sk_bytes=128, sig_bytes=49856
    ),
}

class ADRS:
    """NIST FIPS 205 32-Byte Address Structure for Domain Separation."""
    __slots__ = ("layer", "tree", "type", "word1", "word2", "word3")

    def __init__(self):
        self.layer = 0       # 4 bytes (offset 0)
        self.tree = 0        # 12 bytes (offset 4..15)
        self.type = 0        # 4 bytes (offset 16..19)
        self.word1 = 0       # 4 bytes (offset 20..23) e.g. keypair_addr
        self.word2 = 0       # 4 bytes (offset 24..27) e.g. chain_addr / tree_height
        self.word3 = 0       # 4 bytes (offset 28..31) e.g. hash_addr / tree_index

    def copy(self) -> 'ADRS':
        c = ADRS()
        c.layer = self.layer
        c.tree = self.tree
        c.type = self.type
        c.word1 = self.word1
        c.word2 = self.word2
        c.word3 = self.word3
        return c

    def set_layer_address(self, layer: int):
        self.layer = layer

    def set_tree_address(self, tree: int):
        self.tree = tree

    def set_type(self, adrs_type: int):
        self.type = adrs_type
        self.word1 = 0
        self.word2 = 0
        self.word3 = 0

    def set_keypair_address(self, kp: int):
        self.word1 = kp

    def set_chain_address(self, chain: int):
        self.word2 = chain

    def set_hash_address(self, h: int):
        self.word3 = h

    def set_tree_height(self, height: int):
        self.word2 = height

    def set_tree_index(self, index: int):
        self.word3 = index

    def to_bytes(self) -> bytes:
        buf = bytearray(32)
        buf[0:4] = self.layer.to_bytes(4, "big")
        buf[4:16] = self.tree.to_bytes(12, "big")
        buf[16:20] = self.type.to_bytes(4, "big")
        buf[20:24] = self.word1.to_bytes(4, "big")
        buf[24:28] = self.word2.to_bytes(4, "big")
        buf[28:32] = self.word3.to_bytes(4, "big")
        return bytes(buf)

def pack_slhdsa_descriptor(
    param_set: str,
    operation_mode: int, # 0 = KeyGen, 1 = Sign, 2 = Verify
    msg_len: int,
    epoch: int = 1
) -> bytes:
    """Pack 32-byte header descriptor for DR21 AIE2 tile dispatch."""
    params = SLHDSA_PARAMS[param_set]
    mode_id = 0 if "128s" in param_set else 1 if "128f" in param_set else 2 if "256s" in param_set else 3
    buf = bytearray(32)
    buf[0:4] = MAGIC_DESC_DR21
    buf[4] = mode_id
    buf[5] = operation_mode
    buf[6:8] = params.n.to_bytes(2, "little")
    buf[8:12] = msg_len.to_bytes(4, "little")
    buf[12:16] = epoch.to_bytes(4, "little")
    buf[16:20] = params.sig_bytes.to_bytes(4, "little")
    buf[20:24] = params.pk_bytes.to_bytes(4, "little")
    return bytes(buf)
