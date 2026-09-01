# SPDX-License-Identifier: Apache-2.0
"""
PKCS #11 Token Interface Prototype.
High-level Python wrapper emulating Cryptoki token interface dispatching to AIE2 graphs.
"""

import os
import time
import uuid
from typing import Dict, Any, Tuple, Optional, List

from .dr23_openssl_provider import get_phoenix_pqc_provider, PhoenixPqcKey
from . import dr10_sealed_lifecycle_graph as zeroize_core

# PKCS#11 Return Codes (CK_RV)
CKR_OK                              = 0x00000000
CKR_CANCEL                          = 0x00000001
CKR_SLOT_ID_INVALID                 = 0x00000003
CKR_GENERAL_ERROR                   = 0x00000005
CKR_FUNCTION_FAILED                 = 0x00000006
CKR_ARGUMENTS_BAD                   = 0x00000007
CKR_PIN_INCORRECT                   = 0x000000A0
CKR_PIN_LOCKED                      = 0x000000A4
CKR_SESSION_HANDLE_INVALID          = 0x000000B3
CKR_SESSION_PARALLEL_NOT_SUPPORTED  = 0x000000B4
CKR_SESSION_READ_ONLY               = 0x000000B5
CKR_SESSION_EXISTS                  = 0x000000B6
CKR_SESSION_READ_ONLY_EXISTS        = 0x000000B7
CKR_SESSION_READ_WRITE_SO_EXISTS    = 0x000000B8
CKR_SIGNATURE_INVALID               = 0x000000C0
CKR_SIGNATURE_LEN_RANGE             = 0x000000C1
CKR_KEY_HANDLE_INVALID              = 0x00000060
CKR_KEY_SIZE_RANGE                  = 0x00000062
CKR_KEY_TYPE_INCONSISTENT           = 0x00000063
CKR_MECHANISM_INVALID               = 0x00000070
CKR_MECHANISM_PARAM_INVALID         = 0x00000071
CKR_CRYPTOKI_NOT_INITIALIZED        = 0x00000190
CKR_CRYPTOKI_ALREADY_INITIALIZED    = 0x00000191
CKR_USER_NOT_LOGGED_IN              = 0x00000101
CKR_USER_ALREADY_LOGGED_IN          = 0x00000100

# PKCS#11 Mechanisms
CKM_ML_KEM_KEY_PAIR_GEN = 0x00004001
CKM_ML_KEM_ENCAPSULATE  = 0x00004002
CKM_ML_KEM_DECAPSULATE  = 0x00004003
CKM_ML_DSA_KEY_PAIR_GEN = 0x00004011
CKM_ML_DSA              = 0x00004012
CKM_HYBRID_QKD_ML_KEM   = 0x00004021

# PKCS#11 User Types
CKU_SO   = 0
CKU_USER = 1

# PKCS#11 Session Flags
CKF_RW_SESSION = 0x00000002
CKF_SERIAL_SESSION = 0x00000004

class PhoenixPkcs11Token:
    """Represents a virtual PKCS#11 slot/token on AMD Phoenix AIE2."""
    def __init__(self, slot_id: int = 0):
        self.slot_id = slot_id
        self.label = "Phoenix AIE2 PQC/QKD HSM Token"
        self.manufacturer = "AMD Phoenix AIE2 (XDNA1 Architecture)"
        self.model = "Phoenix PQC/QKD Silicon HSM"
        self.serial_number = "AIE2-PHOENIX-HSM-0001"
        self.hardware_version = (1, 1)
        self.firmware_version = (1, 3)
        self.user_pin = "123456"
        self.so_pin = "87654321"
        self.logged_in = False
        self.user_type: Optional[int] = None
        self.objects: Dict[int, PhoenixPqcKey] = {}
        self.active_sign_ctx: Dict[int, Any] = {}
        self.active_verify_ctx: Dict[int, Any] = {}
        self.next_handle = 1000

    def zeroize(self):
        """Zeroizes all resident key handles and resets session state."""
        for obj in self.objects.values():
            obj.zeroize()
        self.objects.clear()
        self.active_sign_ctx.clear()
        self.active_verify_ctx.clear()
        self.logged_in = False
        self.user_type = None
        try:
            zeroize_core.execute_dr10_zeroize_on_silicon()
        except Exception:
            pass

class PhoenixPkcs11Hsm:
    """
    OASIS PKCS#11 v3.0 Cryptoki Module Interface for AMD Phoenix AIE2 Silicon.
    """
    def __init__(self):
        self.initialized = False
        self.tokens: Dict[int, PhoenixPkcs11Token] = {}
        self.sessions: Dict[int, int] = {} # session_id -> slot_id
        self.provider = get_phoenix_pqc_provider()

    def C_Initialize(self, pInitArgs=None) -> int:
        if self.initialized:
            return CKR_CRYPTOKI_ALREADY_INITIALIZED
        self.initialized = True
        self.tokens[0] = PhoenixPkcs11Token(slot_id=0)
        return CKR_OK

    def C_Finalize(self, pReserved=None) -> int:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED
        for token in self.tokens.values():
            token.zeroize()
        self.tokens.clear()
        self.sessions.clear()
        self.initialized = False
        return CKR_OK

    def C_GetInfo(self) -> Tuple[int, Dict[str, Any]]:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED, {}
        return CKR_OK, {
            "cryptokiVersion": (3, 0),
            "manufacturerID": "AMD Phoenix Compute Accelerator",
            "flags": 0,
            "libraryDescription": "AMD Phoenix NPU PQC & QKD Cryptoki HSM Library",
            "libraryVersion": (1, 2),
        }

    def C_GetSlotList(self, tokenPresent: bool = True) -> Tuple[int, List[int]]:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED, []
        return CKR_OK, list(self.tokens.keys())

    def C_GetTokenInfo(self, slot_id: int) -> Tuple[int, Dict[str, Any]]:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED, {}
        if slot_id not in self.tokens:
            return CKR_SLOT_ID_INVALID, {}
        token = self.tokens[slot_id]
        return CKR_OK, {
            "label": token.label,
            "manufacturerID": token.manufacturer,
            "model": token.model,
            "serialNumber": token.serial_number,
            "hardwareVersion": token.hardware_version,
            "firmwareVersion": token.firmware_version,
            "flags": 0x0000040D, # CKF_RNG | CKF_LOGIN_REQUIRED | CKF_USER_PIN_INITIALIZED | CKF_TOKEN_INITIALIZED
            "ulTotalPublicMemory": 65536,
            "ulFreePublicMemory": 32768,
            "ulTotalPrivateMemory": 65536,
            "ulFreePrivateMemory": 32768,
        }

    def C_OpenSession(self, slot_id: int, flags: int = CKF_SERIAL_SESSION | CKF_RW_SESSION) -> Tuple[int, int]:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED, 0
        if slot_id not in self.tokens:
            return CKR_SLOT_ID_INVALID, 0
        session_id = int(uuid.uuid4().int & 0x7FFFFFFF)
        self.sessions[session_id] = slot_id
        return CKR_OK, session_id

    def C_CloseSession(self, session_id: int) -> int:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID
        slot_id = self.sessions.pop(session_id)
        if slot_id in self.tokens:
            self.tokens[slot_id].zeroize()
        return CKR_OK

    def C_Login(self, session_id: int, user_type: int, pin: str) -> int:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID
        token = self.tokens[self.sessions[session_id]]
        if token.logged_in:
            return CKR_USER_ALREADY_LOGGED_IN
        if user_type == CKU_USER and pin == token.user_pin:
            token.logged_in = True
            token.user_type = CKU_USER
            return CKR_OK
        elif user_type == CKU_SO and pin == token.so_pin:
            token.logged_in = True
            token.user_type = CKU_SO
            return CKR_OK
        return CKR_PIN_INCORRECT

    def C_Logout(self, session_id: int) -> int:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID
        token = self.tokens[self.sessions[session_id]]
        token.zeroize()
        return CKR_OK

    def C_GenerateKeyPair(
        self,
        session_id: int,
        mechanism: int,
        algorithm: str
    ) -> Tuple[int, int, int]:
        """
        Executes on-device Keypair Generation inside AIE2 tile cluster.
        Returns: (rv, pubkey_handle, privkey_handle)
        """
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED, 0, 0
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID, 0, 0

        token = self.tokens[self.sessions[session_id]]
        if not token.logged_in:
            return CKR_USER_NOT_LOGGED_IN, 0, 0

        if isinstance(algorithm, dict):
            algo_name = algorithm.get("param", algorithm.get("algorithm", algorithm.get("name", "ML-DSA-44")))
        else:
            algo_name = str(algorithm)
        algo = algo_name.upper().replace("_", "-")
        if mechanism in (CKM_ML_KEM_KEY_PAIR_GEN, CKM_HYBRID_QKD_ML_KEM):
            key = self.provider.kem_keygen(algo)
        elif mechanism == CKM_ML_DSA_KEY_PAIR_GEN:
            key = self.provider.signature_keygen(algo)
        else:
            return CKR_MECHANISM_INVALID, 0, 0

        pub_handle = token.next_handle
        priv_handle = token.next_handle + 1
        token.next_handle += 2

        token.objects[pub_handle] = PhoenixPqcKey(algo, key.pubkey, None)
        token.objects[priv_handle] = PhoenixPqcKey(algo, key.pubkey, key.privkey)

        return CKR_OK, pub_handle, priv_handle

    def C_SignInit(self, session_id: int, mechanism: int, privkey_handle: int) -> int:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID
        token = self.tokens[self.sessions[session_id]]
        if privkey_handle not in token.objects:
            return CKR_KEY_HANDLE_INVALID
        if mechanism != CKM_ML_DSA:
            return CKR_MECHANISM_INVALID
        token.active_sign_ctx[session_id] = token.objects[privkey_handle]
        return CKR_OK

    def C_Sign(self, session_id: int, message: bytes) -> Tuple[int, bytes]:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED, b""
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID, b""
        token = self.tokens[self.sessions[session_id]]
        if session_id not in token.active_sign_ctx:
            return CKR_FUNCTION_FAILED, b""
        key = token.active_sign_ctx.pop(session_id)
        sig = self.provider.signature_sign(key, message)
        return CKR_OK, sig

    def C_VerifyInit(self, session_id: int, mechanism: int, pubkey_handle: int) -> int:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID
        token = self.tokens[self.sessions[session_id]]
        if pubkey_handle not in token.objects:
            return CKR_KEY_HANDLE_INVALID
        if mechanism != CKM_ML_DSA:
            return CKR_MECHANISM_INVALID
        token.active_verify_ctx[session_id] = token.objects[pubkey_handle]
        return CKR_OK

    def C_Verify(self, session_id: int, message: bytes, signature: bytes) -> int:
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID
        token = self.tokens[self.sessions[session_id]]
        if session_id not in token.active_verify_ctx:
            return CKR_FUNCTION_FAILED
        key = token.active_verify_ctx.pop(session_id)
        valid = self.provider.signature_verify(key, message, signature)
        return CKR_OK if valid else CKR_SIGNATURE_INVALID

    def C_DeriveKey(
        self,
        session_id: int,
        mechanism: int,
        key_handle: int,
        ciphertext_in: Optional[bytes] = None
    ) -> Tuple[int, bytes, bytes]:
        """
        Executes on-device KEM Encapsulation (if ciphertext_in is None) or Decapsulation.
        Returns: (rv, ciphertext, shared_secret)
        """
        if not self.initialized:
            return CKR_CRYPTOKI_NOT_INITIALIZED, b"", b""
        if session_id not in self.sessions:
            return CKR_SESSION_HANDLE_INVALID, b"", b""
        token = self.tokens[self.sessions[session_id]]
        if key_handle not in token.objects:
            return CKR_KEY_HANDLE_INVALID, b"", b""

        key = token.objects[key_handle]
        if mechanism == CKM_ML_KEM_ENCAPSULATE:
            ct, ss = self.provider.kem_encapsulate(key)
            return CKR_OK, ct, ss
        elif mechanism == CKM_ML_KEM_DECAPSULATE:
            if not ciphertext_in:
                return CKR_ARGUMENTS_BAD, b"", b""
            ss = self.provider.kem_decapsulate(key, ciphertext_in)
            return CKR_OK, ciphertext_in, ss
        else:
            return CKR_MECHANISM_INVALID, b"", b""

# Global PKCS11 HSM Singleton
_GLOBAL_PKCS11_HSM: Optional[PhoenixPkcs11Hsm] = None

def get_phoenix_pkcs11_hsm() -> PhoenixPkcs11Hsm:
    global _GLOBAL_PKCS11_HSM
    if _GLOBAL_PKCS11_HSM is None:
        _GLOBAL_PKCS11_HSM = PhoenixPkcs11Hsm()
    return _GLOBAL_PKCS11_HSM
