# SPDX-License-Identifier: Apache-2.0
"""Unified DR8 ML-KEM service dispatcher on AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2).

Dispatches NIST FIPS 203 KeyGen, Encaps, and Decaps operations across all 3 parameter sets:
- ML-KEM-512  (k=2, eta1=3, eta2=2, du=10, dv=4)
- ML-KEM-768  (k=3, eta1=2, eta2=2, du=10, dv=4)
- ML-KEM-1024 (k=4, eta1=2, eta2=2, du=11, dv=5)
"""
from typing import Tuple

from phoenix_sdr_dsp.pqc.dr5_mlkem512_keygen_graph import run_mlkem512_keygen as kg512
from phoenix_sdr_dsp.pqc.dr6_mlkem512_encaps_graph import run_mlkem512_encaps as enc512
from phoenix_sdr_dsp.pqc.dr7_mlkem512_decaps_graph import run_mlkem512_decaps as dec512
from phoenix_sdr_dsp.pqc.dr8_mlkem768_keygen_graph import run_mlkem768_keygen as kg768
from phoenix_sdr_dsp.pqc.dr8_mlkem768_encaps_graph import run_mlkem768_encaps as enc768
from phoenix_sdr_dsp.pqc.dr8_mlkem768_decaps_graph import run_mlkem768_decaps as dec768
from phoenix_sdr_dsp.pqc.dr8_mlkem1024_keygen_graph import run_mlkem1024_keygen as kg1024
from phoenix_sdr_dsp.pqc.dr8_mlkem1024_encaps_graph import run_mlkem1024_encaps as enc1024
from phoenix_sdr_dsp.pqc.dr8_mlkem1024_decaps_graph import run_mlkem1024_decaps as dec1024

def mlkem_keygen(d: bytes, z: bytes, param_set: str = "ML-KEM-768", req_id: int = 1) -> Tuple[bytes, bytes]:
    """Execute NIST FIPS 203 ML-KEM.KeyGen 100% on-device on Phoenix NPU."""
    if param_set in ("ML-KEM-512", "512", 2):
        return kg512(d, z, req_id)
    elif param_set in ("ML-KEM-768", "768", 3):
        return kg768(d, z, req_id)
    elif param_set in ("ML-KEM-1024", "1024", 4):
        return kg1024(d, z, req_id)
    else:
        raise ValueError(f"Unsupported ML-KEM parameter set: {param_set}")

def mlkem_encaps(ek: bytes, m: bytes, param_set: str = "ML-KEM-768", req_id: int = 1) -> Tuple[bytes, bytes]:
    """Execute NIST FIPS 203 ML-KEM.Encaps 100% on-device on Phoenix NPU."""
    if param_set in ("ML-KEM-512", "512", 2):
        return enc512(ek, m, req_id)
    elif param_set in ("ML-KEM-768", "768", 3):
        return enc768(ek, m, req_id)
    elif param_set in ("ML-KEM-1024", "1024", 4):
        return enc1024(ek, m, req_id)
    else:
        raise ValueError(f"Unsupported ML-KEM parameter set: {param_set}")

def mlkem_decaps(dk: bytes, c: bytes, param_set: str = "ML-KEM-768", req_id: int = 1) -> bytes:
    """Execute NIST FIPS 203 ML-KEM.Decaps 100% on-device on Phoenix NPU."""
    if param_set in ("ML-KEM-512", "512", 2):
        return dec512(dk, c, req_id)
    elif param_set in ("ML-KEM-768", "768", 3):
        return dec768(dk, c, req_id)
    elif param_set in ("ML-KEM-1024", "1024", 4):
        return dec1024(dk, c, req_id)
    else:
        raise ValueError(f"Unsupported ML-KEM parameter set: {param_set}")
