# SPDX-License-Identifier: Apache-2.0
"""Contract and Unit Tests for Milestone DR41:
Quantum Key Management System (Q-KMS) Integration & Key Lifecycle Engine.
Execution Boundary: [HOST RUNTIME] / [HOST REFERENCE].
"""

import hashlib
import struct
import unittest

from phoenix_sdr_dsp.pqc.dr41_qkms_abi import (
    MAGIC_HEADER,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_INVALID_SLOT,
    STATUS_ERR_ILLEGAL_TRANSITION,
    STATUS_ERR_SLOT_EXPIRED,
    STATUS_ERR_UNSUPPORTED_OP,
    STATUS_ERR_KEY_COMPROMISED,
    OP_VAULT_STORE,
    OP_VAULT_DERIVE,
    OP_VAULT_TRANSITION,
    OP_VAULT_ZEROIZE,
    OP_VAULT_QUERY,
    STATE_EMPTY,
    STATE_PRE_ACTIVE,
    STATE_ACTIVE,
    STATE_DEACTIVATED,
    STATE_COMPROMISED,
    STATE_DESTROYED,
    KEY_TYPE_QKD,
    KEY_TYPE_PQC_SHARED_SECRET,
    KEY_TYPE_DERIVED_SESSION,
    DESCRIPTOR_SIZE,
    REQUEST_BUFFER_SIZE,
    RESULT_BUFFER_SIZE,
    NUM_VAULT_SLOTS,
    QkmsDescriptor,
    QkmsResultHeader,
    VaultSlot,
    pack_vault_bank,
    unpack_vault_bank,
    build_request_tensor,
    is_valid_state_transition,
    sp800_56c_dual_kdf_ref,
    compute_reference_oracle,
)
from phoenix_sdr_dsp.pqc.dr41_qkms_graph import get_kernel_artifact_info


class TestDR41Contract(unittest.TestCase):

    def test_descriptor_pack_unpack_roundtrip(self):
        desc = QkmsDescriptor(
            op_code=OP_VAULT_STORE,
            slot_id=3,
            target_state=STATE_ACTIVE,
            param_0=10,
            param_1=20,
            key_type=KEY_TYPE_QKD,
            epoch=5,
            seq_id=99,
        )
        packed = desc.pack()
        self.assertEqual(len(packed), DESCRIPTOR_SIZE)
        unpacked = QkmsDescriptor.unpack(packed)
        self.assertEqual(unpacked.magic, MAGIC_HEADER)
        self.assertEqual(unpacked.op_code, OP_VAULT_STORE)
        self.assertEqual(unpacked.slot_id, 3)
        self.assertEqual(unpacked.target_state, STATE_ACTIVE)
        self.assertEqual(unpacked.param_0, 10)
        self.assertEqual(unpacked.param_1, 20)
        self.assertEqual(unpacked.key_type, KEY_TYPE_QKD)
        self.assertEqual(unpacked.epoch, 5)
        self.assertEqual(unpacked.seq_id, 99)

    def test_result_header_pack_unpack(self):
        hdr = QkmsResultHeader(
            status=STATUS_SUCCESS,
            op_code=OP_VAULT_DERIVE,
            slot_id=2,
            current_state=STATE_ACTIVE,
            checksum=0x12345678,
            payload=b"\xAA" * 48,
        )
        packed = hdr.pack()
        self.assertEqual(len(packed), RESULT_BUFFER_SIZE)
        unpacked = QkmsResultHeader.unpack(packed)
        self.assertEqual(unpacked.status, STATUS_SUCCESS)
        self.assertEqual(unpacked.op_code, OP_VAULT_DERIVE)
        self.assertEqual(unpacked.slot_id, 2)
        self.assertEqual(unpacked.current_state, STATE_ACTIVE)
        self.assertEqual(unpacked.checksum, 0x12345678)
        self.assertEqual(unpacked.payload[:48], b"\xAA" * 48)

    def test_vault_bank_pack_unpack_roundtrip(self):
        bank = [VaultSlot() for _ in range(NUM_VAULT_SLOTS)]
        bank[0] = VaultSlot(
            state=STATE_ACTIVE,
            key_type=KEY_TYPE_QKD,
            key_id=b"KEY_ID_SLOT_0001",
            key_material=b"\x42" * 32,
            epoch=1,
        )
        bank[1] = VaultSlot(
            state=STATE_PRE_ACTIVE,
            key_type=KEY_TYPE_PQC_SHARED_SECRET,
            key_id=b"KEY_ID_SLOT_0002",
            key_material=b"\x99" * 32,
            epoch=2,
        )
        packed = pack_vault_bank(bank)
        self.assertEqual(len(packed), NUM_VAULT_SLOTS * 64)
        unpacked = unpack_vault_bank(packed)
        self.assertEqual(len(unpacked), NUM_VAULT_SLOTS)
        self.assertEqual(unpacked[0].state, STATE_ACTIVE)
        self.assertEqual(unpacked[0].key_type, KEY_TYPE_QKD)
        self.assertEqual(unpacked[0].key_id, b"KEY_ID_SLOT_0001")
        self.assertEqual(unpacked[0].key_material, b"\x42" * 32)
        self.assertEqual(unpacked[0].epoch, 1)
        self.assertEqual(unpacked[1].state, STATE_PRE_ACTIVE)
        self.assertEqual(unpacked[1].key_material, b"\x99" * 32)

    def test_state_transitions_compliance(self):
        # NIST SP 800-57 / KMIP allowed transitions
        self.assertTrue(is_valid_state_transition(STATE_EMPTY, STATE_PRE_ACTIVE))
        self.assertTrue(is_valid_state_transition(STATE_EMPTY, STATE_ACTIVE))
        self.assertTrue(is_valid_state_transition(STATE_PRE_ACTIVE, STATE_ACTIVE))
        self.assertTrue(is_valid_state_transition(STATE_PRE_ACTIVE, STATE_DESTROYED))
        self.assertTrue(is_valid_state_transition(STATE_ACTIVE, STATE_DEACTIVATED))
        self.assertTrue(is_valid_state_transition(STATE_ACTIVE, STATE_COMPROMISED))
        self.assertTrue(is_valid_state_transition(STATE_ACTIVE, STATE_DESTROYED))
        self.assertTrue(is_valid_state_transition(STATE_DEACTIVATED, STATE_COMPROMISED))
        self.assertTrue(is_valid_state_transition(STATE_DEACTIVATED, STATE_DESTROYED))
        self.assertTrue(is_valid_state_transition(STATE_COMPROMISED, STATE_DESTROYED))

        # Forbidden transitions
        self.assertFalse(is_valid_state_transition(STATE_DESTROYED, STATE_ACTIVE))
        self.assertFalse(is_valid_state_transition(STATE_DESTROYED, STATE_PRE_ACTIVE))
        self.assertFalse(is_valid_state_transition(STATE_COMPROMISED, STATE_ACTIVE))
        self.assertFalse(is_valid_state_transition(STATE_DEACTIVATED, STATE_ACTIVE))
        self.assertFalse(is_valid_state_transition(STATE_EMPTY, STATE_DESTROYED))

    def test_sp800_56c_dual_kdf_ref_vectors(self):
        pqc = bytes((i * 3 + 1) % 256 for i in range(32))
        qkd = bytes((i * 5 + 7) % 256 for i in range(32))
        salt = bytes((i * 11 + 13) % 256 for i in range(32))

        kdf1 = sp800_56c_dual_kdf_ref(pqc, qkd, salt)
        kdf2 = sp800_56c_dual_kdf_ref(pqc, qkd, salt)
        self.assertEqual(len(kdf1), 32)
        self.assertEqual(kdf1, kdf2)
        # Expected golden output matching verified C++ kernel
        self.assertEqual(kdf1.hex(), "6d19acc88832c58298b1c5d8105d3898593684e41676a790b1871bde4af520e7")

    def test_oracle_vault_store(self):
        raw_key = b"\x01\x02\x03\x04" * 8
        raw_id = b"ID_STORE_TEST_01"
        payload = raw_key + raw_id
        req = build_request_tensor(payload=payload)

        res, vault = compute_reference_oracle(
            op_code=OP_VAULT_STORE,
            slot_id=0,
            request_bytes=req,
            target_state=STATE_ACTIVE,
            key_type=KEY_TYPE_QKD,
            epoch=1,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.op_code, OP_VAULT_STORE)
        self.assertEqual(res.slot_id, 0)
        self.assertEqual(res.current_state, STATE_ACTIVE)
        self.assertNotEqual(res.checksum, 0)
        self.assertEqual(res.payload[:32], raw_key)
        self.assertEqual(res.payload[32:48], raw_id)
        self.assertEqual(vault[0].key_material, raw_key)

    def test_oracle_vault_derive(self):
        # Setup vault with slot 0 (PQC) and slot 1 (QKD)
        vault_in = [VaultSlot() for _ in range(NUM_VAULT_SLOTS)]
        vault_in[0] = VaultSlot(
            state=STATE_ACTIVE,
            key_type=KEY_TYPE_PQC_SHARED_SECRET,
            key_id=b"PQC_SECRET_SLOT0",
            key_material=bytes((i * 3 + 1) % 256 for i in range(32)),
            epoch=1,
        )
        vault_in[1] = VaultSlot(
            state=STATE_ACTIVE,
            key_type=KEY_TYPE_QKD,
            key_id=b"QKD_OPTICAL_SLT1",
            key_material=bytes((i * 5 + 7) % 256 for i in range(32)),
            epoch=1,
        )

        salt = bytes((i * 11 + 13) % 256 for i in range(32))
        req = build_request_tensor(payload=salt, vault=vault_in)

        res, vault_out = compute_reference_oracle(
            op_code=OP_VAULT_DERIVE,
            slot_id=2,
            request_bytes=req,
            param_0=0,
            param_1=1,
            epoch=2,
            initial_vault=vault_in,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.op_code, OP_VAULT_DERIVE)
        self.assertEqual(res.slot_id, 2)
        self.assertEqual(res.current_state, STATE_ACTIVE)
        self.assertEqual(res.payload[:32].hex(), "6d19acc88832c58298b1c5d8105d3898593684e41676a790b1871bde4af520e7")
        self.assertEqual(vault_out[2].state, STATE_ACTIVE)
        self.assertEqual(vault_out[2].key_type, KEY_TYPE_DERIVED_SESSION)

    def test_oracle_vault_transition(self):
        vault_in = [VaultSlot() for _ in range(NUM_VAULT_SLOTS)]
        vault_in[0] = VaultSlot(
            state=STATE_ACTIVE,
            key_type=KEY_TYPE_QKD,
            key_id=b"TRANSITION_TEST1",
            key_material=b"\x55" * 32,
            epoch=1,
        )
        req = build_request_tensor(vault=vault_in)

        # Transition ACTIVE -> DEACTIVATED (Valid)
        res_valid, vault_mid = compute_reference_oracle(
            op_code=OP_VAULT_TRANSITION,
            slot_id=0,
            request_bytes=req,
            target_state=STATE_DEACTIVATED,
            initial_vault=vault_in,
        )
        self.assertEqual(res_valid.status, STATUS_SUCCESS)
        self.assertEqual(res_valid.current_state, STATE_DEACTIVATED)

        # Transition DEACTIVATED -> ACTIVE (Illegal)
        res_illegal, _ = compute_reference_oracle(
            op_code=OP_VAULT_TRANSITION,
            slot_id=0,
            request_bytes=req,
            target_state=STATE_ACTIVE,
            initial_vault=vault_mid,
        )
        self.assertEqual(res_illegal.status, STATUS_ERR_ILLEGAL_TRANSITION)

    def test_oracle_vault_zeroize(self):
        vault_in = [VaultSlot(state=STATE_ACTIVE, key_material=b"\xFF" * 32) for _ in range(NUM_VAULT_SLOTS)]
        req = build_request_tensor(vault=vault_in)

        # Zeroize all slots (0xFF)
        res, vault_out = compute_reference_oracle(
            op_code=OP_VAULT_ZEROIZE,
            slot_id=0xFF,
            request_bytes=req,
            initial_vault=vault_in,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.current_state, STATE_DESTROYED)
        for s in vault_out:
            self.assertEqual(s.state, STATE_DESTROYED)

    def test_oracle_vault_query(self):
        vault_in = [VaultSlot() for _ in range(NUM_VAULT_SLOTS)]
        vault_in[4] = VaultSlot(
            state=STATE_ACTIVE,
            key_type=KEY_TYPE_QKD,
            key_id=b"QUERY_SLOT_04_ID",
            key_material=b"\x77" * 32,
            epoch=7,
        )
        req = build_request_tensor(vault=vault_in)

        res, _ = compute_reference_oracle(
            op_code=OP_VAULT_QUERY,
            slot_id=4,
            request_bytes=req,
            initial_vault=vault_in,
        )
        self.assertEqual(res.status, STATUS_SUCCESS)
        self.assertEqual(res.payload[:32], b"\x77" * 32)
        self.assertEqual(res.payload[32:48], b"QUERY_SLOT_04_ID")
        state, ktype, ep = struct.unpack_from("<III", res.payload, 48)
        self.assertEqual(state, STATE_ACTIVE)
        self.assertEqual(ktype, KEY_TYPE_QKD)
        self.assertEqual(ep, 7)

    def test_oracle_error_paths(self):
        req = bytes(REQUEST_BUFFER_SIZE)

        # Invalid slot
        res_slot, _ = compute_reference_oracle(OP_VAULT_STORE, 99, req)
        self.assertEqual(res_slot.status, STATUS_ERR_INVALID_SLOT)

        # Unsupported operation
        res_unsupp, _ = compute_reference_oracle(0x8888, 0, req)
        self.assertEqual(res_unsupp.status, STATUS_ERR_UNSUPPORTED_OP)

    def test_kernel_source_artifact(self):
        info = get_kernel_artifact_info()
        self.assertTrue(info["path"].endswith("dr41_qkms_service.cc"))
        self.assertGreater(info["size_bytes"], 0)
        self.assertEqual(len(info["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
