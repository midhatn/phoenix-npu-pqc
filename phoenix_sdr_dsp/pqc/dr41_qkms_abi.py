# SPDX-License-Identifier: Apache-2.0
"""Milestone DR41: Quantum Key Management System (Q-KMS) Integration & Hybrid Key Lifecycle Engine.
Execution Boundary: [HOST RUNTIME] / [HOST FORMATTER].
Compliant with ETSI GS QKD 014/015, OASIS KMIP, and NIST SP 800-57 / SP 800-56C.
"""

from dataclasses import dataclass
import hashlib
import struct
import time
from typing import Dict, List, Optional, Tuple

MAGIC_HEADER = 0x44523431  # 'DR41'

# Status Codes
STATUS_SUCCESS = 0x00000000
STATUS_ERR_INVALID_MAGIC = 0x80000001
STATUS_ERR_INVALID_SLOT = 0x80000002
STATUS_ERR_ILLEGAL_TRANSITION = 0x80000003
STATUS_ERR_SLOT_EXPIRED = 0x80000004
STATUS_ERR_UNSUPPORTED_OP = 0x80000005
STATUS_ERR_KEY_COMPROMISED = 0x80000006

# Operations
OP_VAULT_STORE = 0x0001
OP_VAULT_DERIVE = 0x0002
OP_VAULT_TRANSITION = 0x0003
OP_VAULT_ZEROIZE = 0x0004
OP_VAULT_QUERY = 0x0005

# Lifecycle States (NIST SP 800-57 / KMIP)
STATE_EMPTY = 0
STATE_PRE_ACTIVE = 1
STATE_ACTIVE = 2
STATE_DEACTIVATED = 3
STATE_COMPROMISED = 4
STATE_DESTROYED = 5

# Key Types
KEY_TYPE_QKD = 0x01
KEY_TYPE_PQC_SHARED_SECRET = 0x02
KEY_TYPE_DERIVED_SESSION = 0x03

DESCRIPTOR_SIZE = 64
REQUEST_BUFFER_SIZE = 4096
RESULT_BUFFER_SIZE = 2048
NUM_VAULT_SLOTS = 8

# Valid NIST SP 800-57 State Transitions: from_state -> set of allowed to_states
VALID_TRANSITIONS = {
    STATE_EMPTY: {STATE_PRE_ACTIVE, STATE_ACTIVE},
    STATE_PRE_ACTIVE: {STATE_ACTIVE, STATE_DESTROYED},
    STATE_ACTIVE: {STATE_DEACTIVATED, STATE_COMPROMISED, STATE_DESTROYED},
    STATE_DEACTIVATED: {STATE_COMPROMISED, STATE_DESTROYED},
    STATE_COMPROMISED: {STATE_DESTROYED},
    STATE_DESTROYED: set(),  # Terminal state: cannot transition out
}


@dataclass
class QkmsDescriptor:
    op_code: int
    slot_id: int
    target_state: int = STATE_ACTIVE
    param_0: int = 0
    param_1: int = 0
    key_type: int = KEY_TYPE_QKD
    epoch: int = 1
    seq_id: int = 1
    magic: int = MAGIC_HEADER

    def pack(self) -> bytes:
        data = bytearray(DESCRIPTOR_SIZE)
        struct.pack_into(
            "<IIIIIIII",
            data,
            0,
            self.magic,
            self.op_code,
            self.slot_id,
            self.target_state,
            self.param_0,
            self.param_1,
            self.key_type,
            self.epoch,
        )
        struct.pack_into("<I", data, 32, self.seq_id)
        return bytes(data)

    @classmethod
    def unpack(cls, buf: bytes) -> 'QkmsDescriptor':
        if len(buf) < DESCRIPTOR_SIZE:
            raise ValueError(f"Buffer length {len(buf)} < required {DESCRIPTOR_SIZE}")
        fields = struct.unpack_from("<IIIIIIII", buf, 0)
        seq_id = struct.unpack_from("<I", buf, 32)[0]
        return cls(
            magic=fields[0],
            op_code=fields[1],
            slot_id=fields[2],
            target_state=fields[3],
            param_0=fields[4],
            param_1=fields[5],
            key_type=fields[6],
            epoch=fields[7],
            seq_id=seq_id,
        )


@dataclass
class QkmsResultHeader:
    status: int
    op_code: int
    slot_id: int
    current_state: int
    checksum: int
    payload: bytes

    def pack(self) -> bytes:
        hdr = struct.pack(
            "<IIIII12x",
            self.status,
            self.op_code,
            self.slot_id,
            self.current_state,
            self.checksum,
        )
        payload_bytes = self.payload[:RESULT_BUFFER_SIZE - 32]
        pad_len = RESULT_BUFFER_SIZE - 32 - len(payload_bytes)
        return hdr + payload_bytes + (bytes(pad_len) if pad_len > 0 else b"")

    @classmethod
    def unpack(cls, buf: bytes) -> 'QkmsResultHeader':
        if len(buf) < 32:
            raise ValueError(f"Buffer length {len(buf)} < header size 32")
        status, op_code, slot_id, state, checksum = struct.unpack_from("<IIIII", buf, 0)
        payload = buf[32:]
        return cls(
            status=status,
            op_code=op_code,
            slot_id=slot_id,
            current_state=state,
            checksum=checksum,
            payload=payload,
        )


@dataclass
class VaultSlot:
    state: int = STATE_EMPTY
    key_type: int = 0
    key_id: bytes = bytes(16)
    key_material: bytes = bytes(32)
    epoch: int = 0

    def checksum(self) -> int:
        chk = 0
        for b in self.key_id:
            chk = (chk * 31 + b) & 0xFFFFFFFF
        for b in self.key_material:
            chk = (chk * 37 + b) & 0xFFFFFFFF
        chk = (chk + self.state * 101 + self.key_type * 17 + self.epoch) & 0xFFFFFFFF
        return chk


def is_valid_state_transition(from_state: int, to_state: int) -> bool:
    """Verifies NIST SP 800-57 / KMIP key lifecycle state transitions."""
    allowed = VALID_TRANSITIONS.get(from_state, set())
    return to_state in allowed


def sp800_56c_dual_kdf_ref(pqc_secret: bytes, qkd_key: bytes, context_salt: bytes) -> bytes:
    """NIST SP 800-56C two-step dual KDF combining PQC shared secret and QKD optical key.
    Step 1: Extract PRK = HMAC-SHA256(salt=context_salt, IKM = pqc_secret || qkd_key)
    Step 2: Expand OKM = HMAC-SHA256(PRK, info = "SP800-56C-DUAL-KDF" || 0x01)
    """
    import hmac
    # Step 1: Extract
    ikm = pqc_secret[:32] + qkd_key[:32]
    prk = hmac.new(context_salt[:32], ikm, hashlib.sha256).digest()

    # Step 2: Expand
    info = b"SP800-56C-DUAL-KDF\x01"
    okm = hmac.new(prk, info, hashlib.sha256).digest()
    return okm


def pack_vault_bank(vault: List[VaultSlot]) -> bytes:
    buf = bytearray(NUM_VAULT_SLOTS * 64)
    for idx in range(min(NUM_VAULT_SLOTS, len(vault))):
        s = vault[idx]
        offset = idx * 64
        struct.pack_into("<II", buf, offset, s.state, s.key_type)
        buf[offset + 8 : offset + 24] = s.key_id[:16].ljust(16, b"\x00")
        buf[offset + 24 : offset + 56] = s.key_material[:32].ljust(32, b"\x00")
        struct.pack_into("<I", buf, offset + 56, s.epoch)
    return bytes(buf)


def unpack_vault_bank(buf: bytes) -> List[VaultSlot]:
    slots: List[VaultSlot] = []
    for idx in range(NUM_VAULT_SLOTS):
        offset = idx * 64
        if offset + 64 > len(buf):
            slots.append(VaultSlot())
            continue
        state, key_type = struct.unpack_from("<II", buf, offset)
        key_id = buf[offset + 8 : offset + 24]
        key_material = buf[offset + 24 : offset + 56]
        epoch = struct.unpack_from("<I", buf, offset + 56)[0]
        slots.append(VaultSlot(
            state=state,
            key_type=key_type,
            key_id=key_id,
            key_material=key_material,
            epoch=epoch,
        ))
    return slots


def build_request_tensor(
    payload: bytes = b"",
    vault: Optional[List[VaultSlot]] = None,
) -> bytes:
    req = bytearray(REQUEST_BUFFER_SIZE)
    if payload:
        p_len = min(len(payload), 128)
        req[:p_len] = payload[:p_len]
    if vault is not None:
        bank = pack_vault_bank(vault)
        req[128 : 128 + len(bank)] = bank
    return bytes(req)


def compute_reference_oracle(
    op_code: int,
    slot_id: int,
    request_bytes: bytes,
    target_state: int = STATE_ACTIVE,
    param_0: int = 0,
    param_1: int = 0,
    key_type: int = KEY_TYPE_QKD,
    epoch: int = 1,
    initial_vault: Optional[List[VaultSlot]] = None,
) -> Tuple[QkmsResultHeader, List[VaultSlot]]:
    """Independent Host Reference Oracle for Q-KMS Lifecycle Engine."""
    vault = [VaultSlot() for _ in range(NUM_VAULT_SLOTS)]
    if initial_vault is not None:
        for idx in range(min(NUM_VAULT_SLOTS, len(initial_vault))):
            s = initial_vault[idx]
            vault[idx] = VaultSlot(
                state=s.state,
                key_type=s.key_type,
                key_id=bytes(s.key_id),
                key_material=bytes(s.key_material),
                epoch=s.epoch,
            )
    elif len(request_bytes) >= 640:
        vault = unpack_vault_bank(request_bytes[128:640])

    payload = bytearray(RESULT_BUFFER_SIZE - 32)

    # Validate slot_id
    if op_code != OP_VAULT_ZEROIZE or slot_id != 0xFF:
        if slot_id < 0 or slot_id >= NUM_VAULT_SLOTS:
            return QkmsResultHeader(
                status=STATUS_ERR_INVALID_SLOT,
                op_code=op_code,
                slot_id=slot_id,
                current_state=STATE_EMPTY,
                checksum=0,
                payload=bytes(payload),
            ), vault

    if op_code == OP_VAULT_STORE:
        raw_key = request_bytes[:32]
        raw_id = request_bytes[32:48]
        vault[slot_id] = VaultSlot(
            state=target_state if target_state in (STATE_PRE_ACTIVE, STATE_ACTIVE) else STATE_ACTIVE,
            key_type=key_type,
            key_id=raw_id,
            key_material=raw_key,
            epoch=epoch,
        )
        chk = vault[slot_id].checksum()
        payload[:32] = raw_key
        payload[32:48] = raw_id
        return QkmsResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            slot_id=slot_id,
            current_state=vault[slot_id].state,
            checksum=chk,
            payload=bytes(payload),
        ), vault

    elif op_code == OP_VAULT_DERIVE:
        s0 = param_0
        s1 = param_1
        if s0 < 0 or s0 >= NUM_VAULT_SLOTS or s1 < 0 or s1 >= NUM_VAULT_SLOTS:
            return QkmsResultHeader(
                status=STATUS_ERR_INVALID_SLOT,
                op_code=op_code,
                slot_id=slot_id,
                current_state=STATE_EMPTY,
                checksum=0,
                payload=bytes(payload),
            ), vault

        slot_a = vault[s0]
        slot_b = vault[s1]
        if slot_a.state == STATE_COMPROMISED or slot_b.state == STATE_COMPROMISED:
            return QkmsResultHeader(
                status=STATUS_ERR_KEY_COMPROMISED,
                op_code=op_code,
                slot_id=slot_id,
                current_state=STATE_COMPROMISED,
                checksum=0,
                payload=bytes(payload),
            ), vault

        if slot_a.state != STATE_ACTIVE or slot_b.state != STATE_ACTIVE:
            return QkmsResultHeader(
                status=STATUS_ERR_SLOT_EXPIRED,
                op_code=op_code,
                slot_id=slot_id,
                current_state=slot_a.state,
                checksum=0,
                payload=bytes(payload),
            ), vault

        context_salt = request_bytes[:32]
        derived_key = sp800_56c_dual_kdf_ref(slot_a.key_material, slot_b.key_material, context_salt)
        derived_id = hashlib.sha256(derived_key + b"ID").digest()[:16]

        vault[slot_id] = VaultSlot(
            state=STATE_ACTIVE,
            key_type=KEY_TYPE_DERIVED_SESSION,
            key_id=derived_id,
            key_material=derived_key,
            epoch=epoch,
        )
        chk = vault[slot_id].checksum()
        payload[:32] = derived_key
        payload[32:48] = derived_id
        return QkmsResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            slot_id=slot_id,
            current_state=STATE_ACTIVE,
            checksum=chk,
            payload=bytes(payload),
        ), vault

    elif op_code == OP_VAULT_TRANSITION:
        cur_state = vault[slot_id].state
        if not is_valid_state_transition(cur_state, target_state):
            return QkmsResultHeader(
                status=STATUS_ERR_ILLEGAL_TRANSITION,
                op_code=op_code,
                slot_id=slot_id,
                current_state=cur_state,
                checksum=vault[slot_id].checksum(),
                payload=bytes(payload),
            ), vault

        vault[slot_id].state = target_state
        if target_state == STATE_DESTROYED:
            vault[slot_id].key_material = bytes(32)
            vault[slot_id].key_id = bytes(16)

        chk = vault[slot_id].checksum()
        payload[:32] = vault[slot_id].key_material
        payload[32:48] = vault[slot_id].key_id
        return QkmsResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            slot_id=slot_id,
            current_state=target_state,
            checksum=chk,
            payload=bytes(payload),
        ), vault

    elif op_code == OP_VAULT_ZEROIZE:
        if slot_id == 0xFF:
            # Wipe all slots
            for idx in range(NUM_VAULT_SLOTS):
                vault[idx] = VaultSlot(state=STATE_DESTROYED)
            return QkmsResultHeader(
                status=STATUS_SUCCESS,
                op_code=op_code,
                slot_id=0xFF,
                current_state=STATE_DESTROYED,
                checksum=0,
                payload=bytes(payload),
            ), vault
        else:
            vault[slot_id] = VaultSlot(state=STATE_DESTROYED)
            return QkmsResultHeader(
                status=STATUS_SUCCESS,
                op_code=op_code,
                slot_id=slot_id,
                current_state=STATE_DESTROYED,
                checksum=0,
                payload=bytes(payload),
            ), vault

    elif op_code == OP_VAULT_QUERY:
        slot = vault[slot_id]
        chk = slot.checksum()
        payload[:32] = slot.key_material
        payload[32:48] = slot.key_id
        struct.pack_into("<III", payload, 48, slot.state, slot.key_type, slot.epoch)
        return QkmsResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            slot_id=slot_id,
            current_state=slot.state,
            checksum=chk,
            payload=bytes(payload),
        ), vault

    else:
        return QkmsResultHeader(
            status=STATUS_ERR_UNSUPPORTED_OP,
            op_code=op_code,
            slot_id=slot_id,
            current_state=STATE_EMPTY,
            checksum=0,
            payload=bytes(payload),
        ), vault
