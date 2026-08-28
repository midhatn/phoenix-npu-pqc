# SPDX-License-Identifier: Apache-2.0
"""ABI contract for unified multi-parameter ML-KEM on AMD Phoenix NPU (DR8).

Parameter Sets:
- ML-KEM-512  (param_id = 0x03, k=2)
- ML-KEM-768  (param_id = 0x04, k=3)
- ML-KEM-1024 (param_id = 0x05, k=4)

Operations:
- KeyGen (op_id = 0x01)
- Encaps (op_id = 0x02)
- Decaps (op_id = 0x03)
"""
import struct

MAGIC_DR8_REQ = 0x527101 # Descriptor magic
MAGIC_DR8_RES = 0x4838524D # b"MR8H"

STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3

PARAM_MLKEM512 = 0x03
PARAM_MLKEM768 = 0x04
PARAM_MLKEM1024 = 0x05

OP_KEYGEN = 0x01
OP_ENCAPS = 0x02
OP_DECAPS = 0x03

# Parameter Set Sizes (in bytes)
# ML-KEM-512
MLKEM512_EK_BYTES = 800
MLKEM512_DK_BYTES = 1632
MLKEM512_C_BYTES = 768

# ML-KEM-768
MLKEM768_EK_BYTES = 1184
MLKEM768_DK_BYTES = 2400
MLKEM768_C_BYTES = 1088

# ML-KEM-1024
MLKEM1024_EK_BYTES = 1568
MLKEM1024_DK_BYTES = 3168
MLKEM1024_C_BYTES = 1568

SHARED_KEY_BYTES = 32
DESCRIPTOR_BYTES = 16

def build_descriptor(request_id: int, param_id: int, op_id: int) -> bytes:
    # 16-byte header: [0..2]=Magic, [3]=0, [4]=param_id, [5]=op_id, [6]=0x08 (DR8), [7]=0, [8..11]=req_id, [12..15]=0
    return struct.pack("<BBBBBBBBII", 1, 0x71, 0x52, 0, param_id, op_id, 0x08, 0, request_id, 0)
