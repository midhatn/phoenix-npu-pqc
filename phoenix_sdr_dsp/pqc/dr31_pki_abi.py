# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR31: On-Device X.509 Post-Quantum PKI & Certificate Engine ABI
-------------------------------------------------------------------------
RFC 5280 / RFC 9618 X.509 v3 post-quantum certificate structures & ASN.1 DER tags.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

MAGIC_DESC_DR31 = b"\x01\x31\x50\x4B"   # DR31 Descriptor Magic ('\x011PK')
MAGIC_RESULT_DR31 = b"PK31"                # DR31 Result Magic

# ASN.1 DER Tag Constants (ITU-T X.690)
TAG_BOOLEAN          = 0x01
TAG_INTEGER          = 0x02
TAG_BIT_STRING       = 0x03
TAG_OCTET_STRING     = 0x04
TAG_NULL             = 0x05
TAG_OID              = 0x06
TAG_UTF8_STRING      = 0x0C
TAG_PRINTABLE_STRING = 0x13
TAG_IA5_STRING       = 0x16
TAG_UTCTIME          = 0x17
TAG_GENERALIZEDTIME  = 0x18
TAG_SEQUENCE         = 0x30
TAG_SET              = 0x31
TAG_CONTEXT_0        = 0xA0  # [0] EXPLICIT Version
TAG_CONTEXT_3        = 0xA3  # [3] EXPLICIT Extensions

# Post-Quantum & Standard Object Identifiers (OIDs)
OID_MLDSA_44              = "2.16.840.1.101.3.4.3.17"
OID_MLDSA_65              = "2.16.840.1.101.3.4.3.18"
OID_MLDSA_87              = "2.16.840.1.101.3.4.3.19"
OID_SLHDSA_SHAKE_128S     = "2.16.840.1.101.3.4.3.22"
OID_LMS_HSS               = "1.2.840.113549.1.9.16.3.17"
OID_COMPOSITE_MLDSA_P256  = "1.3.6.1.4.1.18227.2.1"

# Standard X.509 Extension OIDs (RFC 5280)
OID_BASIC_CONSTRAINTS     = "2.5.29.19"
OID_KEY_USAGE             = "2.5.29.15"
OID_EXT_KEY_USAGE         = "2.5.29.37"
OID_SUBJECT_KEY_ID        = "2.5.29.14"
OID_AUTHORITY_KEY_ID      = "2.5.29.35"

# Key Usage Bits
KEY_USAGE_DIGITAL_SIGNATURE = 0x80
KEY_USAGE_KEY_CERT_SIGN     = 0x04
KEY_USAGE_CRL_SIGN          = 0x02

@dataclass
class SubjectPublicKeyInfo:
    algorithm_oid: str
    public_key_bytes: bytes

@dataclass
class ValidityPeriod:
    not_before: int  # Unix timestamp
    not_after: int   # Unix timestamp

@dataclass
class X509Extension:
    oid: str
    critical: bool
    value_bytes: bytes

@dataclass
class X509Certificate:
    serial_number: int
    signature_algo_oid: str
    issuer_dn: str
    validity: ValidityPeriod
    subject_dn: str
    spki: SubjectPublicKeyInfo
    extensions: List[X509Extension] = field(default_factory=list)
    tbs_raw: bytes = b""
    signature_value: bytes = b""

    @property
    def is_ca(self) -> bool:
        for ext in self.extensions:
            if ext.oid == OID_BASIC_CONSTRAINTS:
                # Parse basic constraints (first byte or boolean)
                return len(ext.value_bytes) > 0 and ext.value_bytes[-1] != 0
        return False

    @property
    def is_self_signed(self) -> bool:
        return self.issuer_dn == self.subject_dn
