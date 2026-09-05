# SPDX-License-Identifier: Apache-2.0
"""Contract and Unit Tests for Milestone DR42:
ANSSI Composite & Dual-Signature Sovereign Standard Engine.
Execution Boundary: [HOST RUNTIME] / [HOST REFERENCE].
"""

import hashlib
import struct
import unittest

from phoenix_sdr_dsp.pqc.dr42_composite_sig_abi import (
    MAGIC_HEADER,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_UNSUPPORTED_TYPE,
    STATUS_ERR_TRAD_VERIFY_FAILED,
    STATUS_ERR_PQC_VERIFY_FAILED,
    STATUS_ERR_COMPOSITE_VERIFY_FAILED,
    STATUS_ERR_MALFORMED_SIGNATURE,
    STATUS_ERR_MALFORMED_KEY,
    STATUS_ERR_UNSUPPORTED_OP,
    OP_COMPOSITE_KEY_INGRESS,
    OP_COMPOSITE_DIGEST_BIND,
    OP_COMPOSITE_VERIFY,
    OP_COMPOSITE_PACK_SIGNATURE,
    OP_COMPOSITE_QUERY,
    COMPOSITE_TYPE_MLDSA44_ED25519,
    COMPOSITE_TYPE_MLDSA65_ECDSA_P384,
    COMPOSITE_TYPE_MLDSA87_ECDSA_P521,
    DESCRIPTOR_SIZE,
    REQUEST_BUFFER_SIZE,
    RESULT_BUFFER_SIZE,
    CompositeSigDescriptor,
    CompositeSigResultHeader,
    build_composite_request_tensor,
    compute_ietf_bound_digest_ref,
    compute_composite_fingerprint_ref,
    compute_composite_result_checksum,
    compute_reference_oracle,
)
from phoenix_sdr_dsp.pqc.dr42_composite_sig_graph import get_kernel_artifact_info


class TestDR42Contract(unittest.TestCase):

    def test_descriptor_pack_unpack_roundtrip(self):
        desc = CompositeSigDescriptor(
            op_code=OP_COMPOSITE_VERIFY,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            flags=0x03,
            msg_len=64,
            context_len=16,
            trad_pk_len=32,
            trad_sig_len=64,
            pqc_pk_len=1312,
            pqc_sig_len=2420,
            seq_id=42,
        )
        packed = desc.pack()
        self.assertEqual(len(packed), DESCRIPTOR_SIZE)
        unpacked = CompositeSigDescriptor.unpack(packed)
        self.assertEqual(unpacked.magic, MAGIC_HEADER)
        self.assertEqual(unpacked.op_code, OP_COMPOSITE_VERIFY)
        self.assertEqual(unpacked.sig_type, COMPOSITE_TYPE_MLDSA44_ED25519)
        self.assertEqual(unpacked.flags, 0x03)
        self.assertEqual(unpacked.msg_len, 64)
        self.assertEqual(unpacked.context_len, 16)
        self.assertEqual(unpacked.trad_pk_len, 32)
        self.assertEqual(unpacked.trad_sig_len, 64)
        self.assertEqual(unpacked.pqc_pk_len, 1312)
        self.assertEqual(unpacked.pqc_sig_len, 2420)
        self.assertEqual(unpacked.seq_id, 42)

    def test_result_header_pack_unpack(self):
        hdr = CompositeSigResultHeader(
            status=STATUS_SUCCESS,
            op_code=OP_COMPOSITE_VERIFY,
            sig_type=COMPOSITE_TYPE_MLDSA65_ECDSA_P384,
            is_valid=1,
            checksum=0xABCDEF01,
            flags=0x03,
            payload=b"\x5A" * 64,
        )
        packed = hdr.pack()
        self.assertEqual(len(packed), RESULT_BUFFER_SIZE)
        unpacked = CompositeSigResultHeader.unpack(packed)
        self.assertEqual(unpacked.status, STATUS_SUCCESS)
        self.assertEqual(unpacked.op_code, OP_COMPOSITE_VERIFY)
        self.assertEqual(unpacked.sig_type, COMPOSITE_TYPE_MLDSA65_ECDSA_P384)
        self.assertEqual(unpacked.is_valid, 1)
        self.assertEqual(unpacked.checksum, 0xABCDEF01)
        self.assertEqual(unpacked.flags, 0x03)
        self.assertEqual(unpacked.payload[:64], b"\x5A" * 64)

    def test_bound_digest_computation(self):
        oid = b"\x2B\x06\x01\x04\x01\x02\x03\x04".ljust(32, b"\x00")
        context = b"ANSSI_TEST_CTX_1"
        message = b"SOVEREIGN_DUAL_SIGNATURE_PAYLOAD_DATA"

        d1 = compute_ietf_bound_digest_ref(oid, context, message)
        d2 = compute_ietf_bound_digest_ref(oid, context, message)
        self.assertEqual(len(d1), 32)
        self.assertEqual(d1, d2)
        # Verify deterministic hash
        self.assertIsInstance(d1, bytes)

    def test_composite_fingerprint_computation(self):
        trad_pk = b"\x11" * 32
        pqc_pk = b"\x22" * 1312
        fp1 = compute_composite_fingerprint_ref(COMPOSITE_TYPE_MLDSA44_ED25519, trad_pk, pqc_pk)
        fp2 = compute_composite_fingerprint_ref(COMPOSITE_TYPE_MLDSA44_ED25519, trad_pk, pqc_pk)
        self.assertEqual(len(fp1), 32)
        self.assertEqual(fp1, fp2)

    def test_oracle_key_ingress_valid(self):
        trad_pk = b"\x33" * 32
        pqc_pk = b"\x44" * 1312
        req = build_composite_request_tensor(trad_pk=trad_pk, pqc_pk=pqc_pk)

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_KEY_INGRESS,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            trad_pk_len=32,
            pqc_pk_len=1312,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.is_valid, 1)
        self.assertNotEqual(res.checksum, 0)
        expected_fp = compute_composite_fingerprint_ref(COMPOSITE_TYPE_MLDSA44_ED25519, trad_pk, pqc_pk)
        self.assertEqual(res.payload[:32], expected_fp)

    def test_oracle_key_ingress_zero_key_rejected(self):
        trad_pk = bytes(32)  # all zero
        pqc_pk = b"\x44" * 1312
        req = build_composite_request_tensor(trad_pk=trad_pk, pqc_pk=pqc_pk)

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_KEY_INGRESS,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            trad_pk_len=32,
            pqc_pk_len=1312,
        )
        self.assertEqual(res.status, STATUS_ERR_MALFORMED_KEY)
        self.assertEqual(res.is_valid, 0)

    def test_oracle_digest_bind(self):
        oid = b"OID_ED25519_MLDSA44".ljust(32, b"\x00")
        context = b"CONTEXT_TEST_01"
        message = b"MESSAGE_PAYLOAD_ANSSI_2022"
        trad_pk = b"\x33" * 32
        pqc_pk = b"\x44" * 1312

        req = build_composite_request_tensor(
            oid=oid,
            context=context,
            message=message,
            trad_pk=trad_pk,
            pqc_pk=pqc_pk,
        )

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_DIGEST_BIND,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            msg_len=len(message),
            context_len=len(context),
            trad_pk_len=32,
            pqc_pk_len=1312,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.is_valid, 1)
        expected_digest = compute_ietf_bound_digest_ref(oid, context, message)
        self.assertEqual(res.payload[:32], expected_digest)

    def _generate_valid_key_and_sig_pair(self, sig_type: int, digest: bytes):
        if sig_type == COMPOSITE_TYPE_MLDSA44_ED25519:
            tpk_len, tsig_len = 32, 64
            ppk_len, psig_len = 1312, 2420
        elif sig_type == COMPOSITE_TYPE_MLDSA65_ECDSA_P384:
            tpk_len, tsig_len = 48, 96
            ppk_len, psig_len = 1952, 3309
        else:
            tpk_len, tsig_len = 66, 132
            ppk_len, psig_len = 2592, 4627

        trad_pk = bytearray(b"\x55" * tpk_len)
        trad_sig = bytearray(b"\x66" * tsig_len)
        pqc_pk = bytearray(b"\x77" * ppk_len)
        pqc_sig = bytearray(b"\x88" * psig_len)

        # Force classical parity zero:
        chk_t = 0
        for i in range(min(32, tsig_len)):
            chk_t ^= (trad_sig[i] ^ trad_pk[i % tpk_len] ^ digest[i % len(digest)])
        if (chk_t & 0x01) != 0:
            trad_sig[0] ^= 0x01

        # Force PQC parity zero:
        sig_tag = 0
        for i in range(min(32, psig_len)):
            sig_tag ^= pqc_sig[i] << ((i % 4) * 8)
        exp_tag = 0
        for i in range(min(32, len(digest))):
            exp_tag ^= digest[i] << ((i % 4) * 8)
        for i in range(min(32, ppk_len)):
            exp_tag ^= pqc_pk[i] << (((i + 1) % 4) * 8)
        if ((sig_tag ^ exp_tag) & 0x01) != 0:
            pqc_sig[0] ^= 0x01

        return bytes(trad_pk), bytes(trad_sig), bytes(pqc_pk), bytes(pqc_sig)

    def test_oracle_verify_both_valid(self):
        oid = b"OID_CAT2".ljust(32, b"\x00")
        context = b"CTX"
        msg = b"VALID_CONJUNCTIVE_MESSAGE"
        d = compute_ietf_bound_digest_ref(oid, context, msg)
        tpk, tsig, ppk, psig = self._generate_valid_key_and_sig_pair(COMPOSITE_TYPE_MLDSA44_ED25519, d)

        req = build_composite_request_tensor(
            oid=oid,
            context=context,
            message=msg,
            trad_pk=tpk,
            trad_sig=tsig,
            pqc_pk=ppk,
            pqc_sig=psig,
        )

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_VERIFY,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            msg_len=len(msg),
            context_len=len(context),
            trad_pk_len=len(tpk),
            trad_sig_len=len(tsig),
            pqc_pk_len=len(ppk),
            pqc_sig_len=len(psig),
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.is_valid, 1)
        self.assertEqual(res.flags, 0x03)  # Both trad (0x01) and pqc (0x02) passed

    def test_oracle_verify_trad_failed(self):
        oid = b"OID_CAT2".ljust(32, b"\x00")
        context = b"CTX"
        msg = b"TRAD_FAIL_MESSAGE"
        d = compute_ietf_bound_digest_ref(oid, context, msg)
        tpk, tsig, ppk, psig = self._generate_valid_key_and_sig_pair(COMPOSITE_TYPE_MLDSA44_ED25519, d)

        # Invert trad signature parity
        bad_tsig = bytearray(tsig)
        bad_tsig[0] ^= 0x01

        req = build_composite_request_tensor(
            oid=oid,
            context=context,
            message=msg,
            trad_pk=tpk,
            trad_sig=bytes(bad_tsig),
            pqc_pk=ppk,
            pqc_sig=psig,
        )

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_VERIFY,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            msg_len=len(msg),
            context_len=len(context),
            trad_pk_len=len(tpk),
            trad_sig_len=len(tsig),
            pqc_pk_len=len(ppk),
            pqc_sig_len=len(psig),
        )
        self.assertEqual(res.status, STATUS_ERR_TRAD_VERIFY_FAILED)
        self.assertEqual(res.is_valid, 0)
        self.assertEqual(res.flags, 0x02)  # PQC passed, trad failed

    def test_oracle_verify_pqc_failed(self):
        oid = b"OID_CAT2".ljust(32, b"\x00")
        context = b"CTX"
        msg = b"PQC_FAIL_MESSAGE"
        d = compute_ietf_bound_digest_ref(oid, context, msg)
        tpk, tsig, ppk, psig = self._generate_valid_key_and_sig_pair(COMPOSITE_TYPE_MLDSA44_ED25519, d)

        # Invert PQC signature parity
        bad_psig = bytearray(psig)
        bad_psig[0] ^= 0x01

        req = build_composite_request_tensor(
            oid=oid,
            context=context,
            message=msg,
            trad_pk=tpk,
            trad_sig=tsig,
            pqc_pk=ppk,
            pqc_sig=bytes(bad_psig),
        )

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_VERIFY,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            msg_len=len(msg),
            context_len=len(context),
            trad_pk_len=len(tpk),
            trad_sig_len=len(tsig),
            pqc_pk_len=len(ppk),
            pqc_sig_len=len(psig),
        )
        self.assertEqual(res.status, STATUS_ERR_PQC_VERIFY_FAILED)
        self.assertEqual(res.is_valid, 0)
        self.assertEqual(res.flags, 0x01)  # Trad passed, PQC failed

    def test_oracle_pack_signature(self):
        trad_sig = b"\xAA" * 64
        pqc_sig = b"\xBB" * 2420
        req = build_composite_request_tensor(trad_sig=trad_sig, pqc_sig=pqc_sig)

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_PACK_SIGNATURE,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            trad_sig_len=64,
            pqc_sig_len=2420,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.is_valid, 1)
        # Check payload lengths
        t_len = struct.unpack_from("<I", res.payload, 32)[0]
        p_len = struct.unpack_from("<I", res.payload, 36)[0]
        tot_len = struct.unpack_from("<I", res.payload, 40)[0]
        self.assertEqual(t_len, 64)
        self.assertEqual(p_len, 2420)
        self.assertEqual(tot_len, 2484)

    def test_oracle_pack_signature_malformed(self):
        trad_sig = bytes(64)  # all zeros
        pqc_sig = b"\xBB" * 2420
        req = build_composite_request_tensor(trad_sig=trad_sig, pqc_sig=pqc_sig)

        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_PACK_SIGNATURE,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
            request_bytes=req,
            trad_sig_len=64,
            pqc_sig_len=2420,
        )
        self.assertEqual(res.status, STATUS_ERR_MALFORMED_SIGNATURE)
        self.assertEqual(res.is_valid, 0)

    def test_oracle_query(self):
        req = build_composite_request_tensor()
        res = compute_reference_oracle(
            op_code=OP_COMPOSITE_QUERY,
            sig_type=COMPOSITE_TYPE_MLDSA65_ECDSA_P384,
            request_bytes=req,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.is_valid, 1)
        cat = struct.unpack_from("<I", res.payload, 0)[0]
        ver = struct.unpack_from("<I", res.payload, 4)[0]
        suites = struct.unpack_from("<I", res.payload, 8)[0]
        self.assertEqual(cat, 3)
        self.assertEqual(ver, 0x00010002)
        self.assertEqual(suites, 3)

    def test_kernel_artifact_hash_integrity(self):
        info = get_kernel_artifact_info()
        self.assertEqual(info["path"], "phoenix_sdr_dsp/pqc/kernels/dr42_composite_sig_service.cc")
        self.assertGreater(info["size_bytes"], 0)
        self.assertEqual(len(info["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
