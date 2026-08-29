# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR17: ML-DSA Asymmetric QKD Control Plane Authenticator Graph.
Executes NIST FIPS 204 signature verification of QKD session manifests on AIE2 silicon.
"""

import time
import uuid
from typing import Tuple
from . import dr17_mldsa_qkd_auth_abi as abi
from . import dr13_mldsa44_verify_graph as ver44
from . import dr14_mldsa65_verify_graph as ver65
from . import dr15_mldsa87_verify_graph as ver87

BACKEND_LABEL = "dr17-mldsa-qkd-auth:silicon"

def verify_qkd_manifest_on_aie2(
    param_set: str,
    public_key: bytes,
    sae_master: str,
    sae_slave: str,
    key_id: uuid.UUID,
    epoch: int,
    nonce: bytes,
    signature: bytes
) -> Tuple[bool, int, float]:
    """Execute ML-DSA verification of QKD session manifest on physical AIE2 hardware."""
    manifest = abi.pack_dr17_manifest(sae_master, sae_slave, key_id, epoch, nonce)
    t0 = time.time()

    valid = False
    status = abi.STATUS_AUTH_INVALID_SIG

    try:
        if param_set == "ML-DSA-44":
            valid = ver44.run_mldsa44_verify(public_key, manifest, signature)
        elif param_set == "ML-DSA-65":
            valid = ver65.run_mldsa65_verify(public_key, signature, manifest)
        elif param_set == "ML-DSA-87":
            valid = ver87.run_mldsa87_verify(public_key, signature, manifest)
        else:
            status = abi.STATUS_AUTH_UNSUPPORTED_PARAM

        if valid:
            status = abi.STATUS_AUTH_VALID
    except Exception:
        valid = False
        status = abi.STATUS_AUTH_INVALID_SIG

    dt = (time.time() - t0) * 1000
    return valid, status, dt
