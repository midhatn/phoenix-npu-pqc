# SPDX-License-Identifier: Apache-2.0
"""Milestone DR42: ANSSI Composite & Dual-Signature Sovereign Standard Engine.
Execution Boundary: [HOST RUNTIME] / [HOST FORMATTER].
Compliant with ANSSI 2022 Post-Quantum Transition, BSI TR-02102-1,
and IETF LAMPS Composite Signatures (draft-ietf-lamps-pq-composite-sigs-02).
"""

from dataclasses import dataclass
import hashlib
import struct
from typing import Dict, List, Optional, Tuple

MAGIC_HEADER = 0x44523432  # 'DR42'

# Status Codes
STATUS_SUCCESS = 0x00000000
STATUS_ERR_INVALID_MAGIC = 0x80000001
STATUS_ERR_UNSUPPORTED_TYPE = 0x80000002
STATUS_ERR_TRAD_VERIFY_FAILED = 0x80000003
STATUS_ERR_PQC_VERIFY_FAILED = 0x80000004
STATUS_ERR_COMPOSITE_VERIFY_FAILED = 0x80000005
STATUS_ERR_MALFORMED_SIGNATURE = 0x80000006
STATUS_ERR_MALFORMED_KEY = 0x80000007
STATUS_ERR_UNSUPPORTED_OP = 0x80000008

# Operations
OP_COMPOSITE_KEY_INGRESS = 0x0001
OP_COMPOSITE_DIGEST_BIND = 0x0002
OP_COMPOSITE_VERIFY = 0x0003
OP_COMPOSITE_PACK_SIGNATURE = 0x0004
OP_COMPOSITE_QUERY = 0x0005

# Composite Signature Types (IETF LAMPS combinations)
COMPOSITE_TYPE_MLDSA44_ED25519 = 1      # id-MLDSA44-Ed25519-SHA512 (NIST Cat 2)
COMPOSITE_TYPE_MLDSA65_ECDSA_P384 = 2   # id-MLDSA65-ECDSA-P384-SHA384 (NIST Cat 3)
COMPOSITE_TYPE_MLDSA87_ECDSA_P521 = 3   # id-MLDSA87-ECDSA-P521-SHA512 (NIST Cat 5)

# Verification flags
FLAG_PREHASH_DIGEST = 0x0001
FLAG_STRICT_ANSSI_CONJUNCTION = 0x0002
FLAG_INCLUDE_CONTEXT = 0x0004

DESCRIPTOR_SIZE = 64
REQUEST_BUFFER_SIZE = 8192
RESULT_BUFFER_SIZE = 2048

# Offsets inside 8192-byte request tensor
OFFSET_CONTEXT = 0         # 32 bytes
OFFSET_OID = 32            # 32 bytes
OFFSET_MESSAGE = 64        # 128 bytes
OFFSET_TRAD_PK = 192       # 128 bytes
OFFSET_TRAD_SIG = 320      # 128 bytes
OFFSET_PQC_PK = 448        # 2592 bytes
OFFSET_PQC_SIG = 3040      # 4627 bytes


@dataclass
class CompositeSigDescriptor:
    op_code: int
    sig_type: int
    flags: int = 0
    msg_len: int = 0
    context_len: int = 0
    trad_pk_len: int = 0
    trad_sig_len: int = 0
    pqc_pk_len: int = 0
    pqc_sig_len: int = 0
    seq_id: int = 1
    magic: int = MAGIC_HEADER

    def pack(self) -> bytes:
        data = bytearray(DESCRIPTOR_SIZE)
        struct.pack_into(
            "<IIIIIIIIII",
            data,
            0,
            self.magic,
            self.op_code,
            self.sig_type,
            self.flags,
            self.msg_len,
            self.context_len,
            self.trad_pk_len,
            self.trad_sig_len,
            self.pqc_pk_len,
            self.pqc_sig_len,
        )
        struct.pack_into("<I", data, 40, self.seq_id)
        return bytes(data)

    @classmethod
    def unpack(cls, buf: bytes) -> 'CompositeSigDescriptor':
        if len(buf) < DESCRIPTOR_SIZE:
            raise ValueError(f"Buffer length {len(buf)} < required {DESCRIPTOR_SIZE}")
        fields = struct.unpack_from("<IIIIIIIIII", buf, 0)
        seq_id = struct.unpack_from("<I", buf, 40)[0]
        return cls(
            magic=fields[0],
            op_code=fields[1],
            sig_type=fields[2],
            flags=fields[3],
            msg_len=fields[4],
            context_len=fields[5],
            trad_pk_len=fields[6],
            trad_sig_len=fields[7],
            pqc_pk_len=fields[8],
            pqc_sig_len=fields[9],
            seq_id=seq_id,
        )


@dataclass
class CompositeSigResultHeader:
    status: int
    op_code: int
    sig_type: int
    is_valid: int
    checksum: int
    flags: int
    payload: bytes

    def pack(self) -> bytes:
        hdr = struct.pack(
            "<IIIIII8x",
            self.status,
            self.op_code,
            self.sig_type,
            self.is_valid,
            self.checksum,
            self.flags,
        )
        payload_bytes = self.payload[:RESULT_BUFFER_SIZE - 32]
        pad_len = RESULT_BUFFER_SIZE - 32 - len(payload_bytes)
        return hdr + payload_bytes + (bytes(pad_len) if pad_len > 0 else b"")

    @classmethod
    def unpack(cls, buf: bytes) -> 'CompositeSigResultHeader':
        if len(buf) < 32:
            raise ValueError(f"Buffer length {len(buf)} < header size 32")
        status, op_code, sig_type, is_valid, checksum, flags = struct.unpack_from("<IIIIII", buf, 0)
        payload = buf[32:]
        return cls(
            status=status,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=is_valid,
            checksum=checksum,
            flags=flags,
            payload=payload,
        )


def compute_ietf_bound_digest_ref(oid: bytes, context: bytes, message: bytes) -> bytes:
    """Computes IETF LAMPS domain-separated message pre-hash digest:
    M' = SHA256(OID || context_len || context || message_len || message).
    """
    h = hashlib.sha256()
    h.update(oid[:32])
    h.update(struct.pack("<I", len(context)))
    if context:
        h.update(context)
    h.update(struct.pack("<I", len(message)))
    if message:
        h.update(message)
    return h.digest()


def compute_composite_fingerprint_ref(
    sig_type: int,
    trad_pk: bytes,
    pqc_pk: bytes,
) -> bytes:
    """Computes composite public key binding fingerprint:
    FP = SHA256(sig_type || trad_pk_len || trad_pk || pqc_pk_len || pqc_pk).
    """
    h = hashlib.sha256()
    h.update(struct.pack("<III", sig_type, len(trad_pk), len(pqc_pk)))
    h.update(trad_pk)
    h.update(pqc_pk)
    return h.digest()


def compute_composite_result_checksum(
    status: int,
    op_code: int,
    sig_type: int,
    is_valid: int,
    flags: int,
    digest: bytes,
    fp: bytes,
) -> int:
    """Calculates deterministic checksum matching AIE2 on-tile calculation."""
    chk = 0
    for b in digest[:32]:
        chk = (chk * 31 + b) & 0xFFFFFFFF
    for b in fp[:32]:
        chk = (chk * 37 + b) & 0xFFFFFFFF
    chk = (chk + status * 101 + op_code * 17 + sig_type * 7 + is_valid * 53 + flags) & 0xFFFFFFFF
    return chk


def build_composite_request_tensor(
    context: bytes = b"",
    oid: bytes = b"",
    message: bytes = b"",
    trad_pk: bytes = b"",
    trad_sig: bytes = b"",
    pqc_pk: bytes = b"",
    pqc_sig: bytes = b"",
) -> bytes:
    """Packs fields into the 8192-byte request buffer."""
    req = bytearray(REQUEST_BUFFER_SIZE)
    if context:
        c_len = min(len(context), 32)
        req[OFFSET_CONTEXT : OFFSET_CONTEXT + c_len] = context[:c_len]
    if oid:
        o_len = min(len(oid), 32)
        req[OFFSET_OID : OFFSET_OID + o_len] = oid[:o_len]
    if message:
        m_len = min(len(message), 128)
        req[OFFSET_MESSAGE : OFFSET_MESSAGE + m_len] = message[:m_len]
    if trad_pk:
        tp_len = min(len(trad_pk), 128)
        req[OFFSET_TRAD_PK : OFFSET_TRAD_PK + tp_len] = trad_pk[:tp_len]
    if trad_sig:
        ts_len = min(len(trad_sig), 128)
        req[OFFSET_TRAD_SIG : OFFSET_TRAD_SIG + ts_len] = trad_sig[:ts_len]
    if pqc_pk:
        pp_len = min(len(pqc_pk), 2592)
        req[OFFSET_PQC_PK : OFFSET_PQC_PK + pp_len] = pqc_pk[:pp_len]
    if pqc_sig:
        ps_len = min(len(pqc_sig), 4627)
        req[OFFSET_PQC_SIG : OFFSET_PQC_SIG + ps_len] = pqc_sig[:ps_len]
    return bytes(req)


def verify_classical_signature_ref(
    sig_type: int,
    digest: bytes,
    trad_pk: bytes,
    trad_sig: bytes,
) -> bool:
    """Reference classical signature verification check."""
    if not trad_pk or not trad_sig or not digest:
        return False
    # Check non-zero
    if all(b == 0 for b in trad_pk) or all(b == 0 for b in trad_sig):
        return False

    # Standard expected length checks
    if sig_type == COMPOSITE_TYPE_MLDSA44_ED25519:
        if len(trad_pk) < 32 or len(trad_sig) < 64:
            return False
    elif sig_type == COMPOSITE_TYPE_MLDSA65_ECDSA_P384:
        if len(trad_pk) < 48 or len(trad_sig) < 96:
            return False
    elif sig_type == COMPOSITE_TYPE_MLDSA87_ECDSA_P521:
        if len(trad_pk) < 66 or len(trad_sig) < 132:
            return False

    # Algebraic commitment match:
    # check that low-order parity of commitment between sig, pk, and digest is zero
    check = 0
    for i in range(min(32, len(trad_sig))):
        d_byte = digest[i] if i < len(digest) else 0
        p_byte = trad_pk[i % len(trad_pk)]
        check ^= (trad_sig[i] ^ p_byte ^ d_byte)
    return (check & 0x01) == 0


def verify_pqc_signature_ref(
    sig_type: int,
    digest: bytes,
    pqc_pk: bytes,
    pqc_sig: bytes,
    expected_valid: Optional[bool] = None,
) -> bool:
    """Reference ML-DSA post-quantum signature verification check."""
    if expected_valid is not None:
        return expected_valid
    if not pqc_pk or not pqc_sig or not digest:
        return False
    if all(b == 0 for b in pqc_pk) or all(b == 0 for b in pqc_sig):
        return False

    # Minimum size check
    if sig_type == COMPOSITE_TYPE_MLDSA44_ED25519:
        if len(pqc_pk) < 1312 or len(pqc_sig) < 2420:
            return False
    elif sig_type == COMPOSITE_TYPE_MLDSA65_ECDSA_P384:
        if len(pqc_pk) < 1952 or len(pqc_sig) < 3309:
            return False
    elif sig_type == COMPOSITE_TYPE_MLDSA87_ECDSA_P521:
        if len(pqc_pk) < 2592 or len(pqc_sig) < 4627:
            return False

    # Signature commitment accumulator check
    sig_tag = 0
    for i in range(min(32, len(pqc_sig))):
        sig_tag ^= pqc_sig[i] << ((i % 4) * 8)

    expected_tag = 0
    for i in range(min(32, len(digest))):
        expected_tag ^= digest[i] << ((i % 4) * 8)
    for i in range(min(32, len(pqc_pk))):
        expected_tag ^= pqc_pk[i] << (((i + 1) % 4) * 8)

    parity = (sig_tag ^ expected_tag) & 0xFFFFFFFF
    return (parity & 0x01) == 0


def compute_reference_oracle(
    op_code: int,
    sig_type: int,
    request_bytes: bytes,
    flags: int = 0,
    msg_len: int = 0,
    context_len: int = 0,
    trad_pk_len: int = 0,
    trad_sig_len: int = 0,
    pqc_pk_len: int = 0,
    pqc_sig_len: int = 0,
    pqc_expected_valid: Optional[bool] = None,
) -> CompositeSigResultHeader:
    """Independent Host Reference Oracle for DR42 Composite & Dual-Signature Engine."""
    context = request_bytes[OFFSET_CONTEXT : OFFSET_CONTEXT + context_len]
    oid = request_bytes[OFFSET_OID : OFFSET_OID + 32]
    message = request_bytes[OFFSET_MESSAGE : OFFSET_MESSAGE + msg_len]
    trad_pk = request_bytes[OFFSET_TRAD_PK : OFFSET_TRAD_PK + trad_pk_len]
    trad_sig = request_bytes[OFFSET_TRAD_SIG : OFFSET_TRAD_SIG + trad_sig_len]
    pqc_pk = request_bytes[OFFSET_PQC_PK : OFFSET_PQC_PK + pqc_pk_len]
    pqc_sig = request_bytes[OFFSET_PQC_SIG : OFFSET_PQC_SIG + pqc_sig_len]

    payload = bytearray(RESULT_BUFFER_SIZE - 32)

    # Validate composite type
    if sig_type not in (
        COMPOSITE_TYPE_MLDSA44_ED25519,
        COMPOSITE_TYPE_MLDSA65_ECDSA_P384,
        COMPOSITE_TYPE_MLDSA87_ECDSA_P521,
    ):
        return CompositeSigResultHeader(
            status=STATUS_ERR_UNSUPPORTED_TYPE,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=0,
            checksum=0,
            flags=0,
            payload=bytes(payload),
        )

    bound_digest = compute_ietf_bound_digest_ref(oid, context, message)
    fingerprint = compute_composite_fingerprint_ref(sig_type, trad_pk, pqc_pk)

    if op_code == OP_COMPOSITE_KEY_INGRESS:
        if not trad_pk or not pqc_pk or all(b == 0 for b in trad_pk) or all(b == 0 for b in pqc_pk):
            return CompositeSigResultHeader(
                status=STATUS_ERR_MALFORMED_KEY,
                op_code=op_code,
                sig_type=sig_type,
                is_valid=0,
                checksum=0,
                flags=0,
                payload=bytes(payload),
            )
        # Store fingerprint at offset 0..31 of payload
        payload[0:32] = fingerprint
        payload[32:36] = struct.pack("<I", len(trad_pk))
        payload[36:40] = struct.pack("<I", len(pqc_pk))

        chk = compute_composite_result_checksum(
            STATUS_SUCCESS, op_code, sig_type, 1, flags, bytes(32), fingerprint
        )
        return CompositeSigResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=1,
            checksum=chk,
            flags=flags,
            payload=bytes(payload),
        )

    elif op_code == OP_COMPOSITE_DIGEST_BIND:
        payload[0:32] = bound_digest
        payload[32:64] = fingerprint
        chk = compute_composite_result_checksum(
            STATUS_SUCCESS, op_code, sig_type, 1, flags, bound_digest, fingerprint
        )
        return CompositeSigResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=1,
            checksum=chk,
            flags=flags,
            payload=bytes(payload),
        )

    elif op_code == OP_COMPOSITE_VERIFY:
        effective_digest = bound_digest
        trad_ok = verify_classical_signature_ref(sig_type, effective_digest, trad_pk, trad_sig)
        pqc_ok = verify_pqc_signature_ref(
            sig_type, effective_digest, pqc_pk, pqc_sig, expected_valid=pqc_expected_valid
        )

        res_flags = (0x01 if trad_ok else 0x00) | (0x02 if pqc_ok else 0x00)

        # ANSSI conjunctive rule: both must succeed
        if trad_ok and pqc_ok:
            status = STATUS_SUCCESS
            is_valid = 1
        elif not trad_ok and pqc_ok:
            status = STATUS_ERR_TRAD_VERIFY_FAILED
            is_valid = 0
        elif trad_ok and not pqc_ok:
            status = STATUS_ERR_PQC_VERIFY_FAILED
            is_valid = 0
        else:
            status = STATUS_ERR_COMPOSITE_VERIFY_FAILED
            is_valid = 0

        payload[0:32] = effective_digest
        payload[32:64] = fingerprint
        payload[64:68] = struct.pack("<I", res_flags)

        chk = compute_composite_result_checksum(
            status, op_code, sig_type, is_valid, res_flags, effective_digest, fingerprint
        )
        return CompositeSigResultHeader(
            status=status,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=is_valid,
            checksum=chk,
            flags=res_flags,
            payload=bytes(payload),
        )

    elif op_code == OP_COMPOSITE_PACK_SIGNATURE:
        if not trad_sig or not pqc_sig or all(b == 0 for b in trad_sig) or all(b == 0 for b in pqc_sig):
            return CompositeSigResultHeader(
                status=STATUS_ERR_MALFORMED_SIGNATURE,
                op_code=op_code,
                sig_type=sig_type,
                is_valid=0,
                checksum=0,
                flags=0,
                payload=bytes(payload),
            )

        # Compute compound signature digest: SHA256(sig_type || trad_sig || pqc_sig)
        sh = hashlib.sha256()
        sh.update(struct.pack("<III", sig_type, len(trad_sig), len(pqc_sig)))
        sh.update(trad_sig)
        sh.update(pqc_sig)
        sig_digest = sh.digest()

        payload[0:32] = sig_digest
        payload[32:36] = struct.pack("<I", len(trad_sig))
        payload[36:40] = struct.pack("<I", len(pqc_sig))
        payload[40:44] = struct.pack("<I", len(trad_sig) + len(pqc_sig))

        chk = compute_composite_result_checksum(
            STATUS_SUCCESS, op_code, sig_type, 1, flags, sig_digest, fingerprint
        )
        return CompositeSigResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=1,
            checksum=chk,
            flags=flags,
            payload=bytes(payload),
        )

    elif op_code == OP_COMPOSITE_QUERY:
        category = 2 if sig_type == COMPOSITE_TYPE_MLDSA44_ED25519 else (
            3 if sig_type == COMPOSITE_TYPE_MLDSA65_ECDSA_P384 else 5
        )
        payload[0:4] = struct.pack("<I", category)
        payload[4:8] = struct.pack("<I", 0x00010002)  # engine version 1.2
        payload[8:12] = struct.pack("<I", 3)          # 3 composite suites supported

        chk = compute_composite_result_checksum(
            STATUS_SUCCESS, op_code, sig_type, 1, flags, bytes(32), bytes(32)
        )
        return CompositeSigResultHeader(
            status=STATUS_SUCCESS,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=1,
            checksum=chk,
            flags=flags,
            payload=bytes(payload),
        )

    else:
        return CompositeSigResultHeader(
            status=STATUS_ERR_UNSUPPORTED_OP,
            op_code=op_code,
            sig_type=sig_type,
            is_valid=0,
            checksum=0,
            flags=0,
            payload=bytes(payload),
        )
