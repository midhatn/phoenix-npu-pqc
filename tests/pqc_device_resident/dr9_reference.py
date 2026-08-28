# SPDX-License-Identifier: Apache-2.0
"""Reference oracle and NIST FIPS 202 test vector generator for DR9."""
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List

def compute_fips202_reference(func_name: str, msg: bytes, out_len: int) -> bytes:
    """Compute bit-exact FIPS 202 reference output."""
    func_upper = func_name.upper()
    if func_upper == "SHA3-224":
        return hashlib.sha3_224(msg).digest()
    elif func_upper == "SHA3-256":
        return hashlib.sha3_256(msg).digest()
    elif func_upper == "SHA3-384":
        return hashlib.sha3_384(msg).digest()
    elif func_upper == "SHA3-512":
        return hashlib.sha3_512(msg).digest()
    elif func_upper == "SHAKE128":
        return hashlib.shake_128(msg).digest(out_len)
    elif func_upper == "SHAKE256":
        return hashlib.shake_256(msg).digest(out_len)
    else:
        raise ValueError(f"Unknown FIPS 202 function: {func_name}")

def generate_dr9_test_vectors() -> Dict:
    """Generate comprehensive NIST FIPS 202 test vectors across all 6 functions."""
    test_cases = []
    
    # 1. Standard test messages: empty, 1-byte, rate-1, rate, rate+1, multi-block (up to 1024 bytes)
    msg_patterns = [
        (b"", "empty_msg"),
        (b"a", "single_byte_a"),
        (b"abc", "standard_abc"),
        (b"The quick brown fox jumps over the lazy dog", "pangram"),
        (b"The quick brown fox jumps over the lazy dog.", "pangram_dot"),
        (bytes(range(100)), "100_byte_seq"),
        (bytes([0x5A] * 135), "135_byte_pattern"),
        (bytes([0xA5] * 136), "136_byte_rate256"),
        (bytes([0x3C] * 137), "137_byte_rate256_plus1"),
        (bytes([0x7E] * 168), "168_byte_rate128"),
        (bytes([0xE7] * 200), "200_byte_pattern"),
        (bytes([i % 256 for i in range(500)]), "500_byte_multiblock"),
        (bytes([0xFF] * 1024), "1024_byte_large"),
    ]
    
    tc_counter = 1
    
    # Test SHA3-224 (28 bytes output)
    for msg, label in msg_patterns:
        digest = compute_fips202_reference("SHA3-224", msg, 28)
        test_cases.append({
            "tcId": f"dr9_sha3_224_{tc_counter:03d}_{label}",
            "function": "SHA3-224",
            "func_id": 1,
            "msg": msg.hex(),
            "msg_len": len(msg),
            "out_len": 28,
            "expected_digest": digest.hex(),
        })
        tc_counter += 1

    # Test SHA3-256 (32 bytes output)
    for msg, label in msg_patterns:
        digest = compute_fips202_reference("SHA3-256", msg, 32)
        test_cases.append({
            "tcId": f"dr9_sha3_256_{tc_counter:03d}_{label}",
            "function": "SHA3-256",
            "func_id": 2,
            "msg": msg.hex(),
            "msg_len": len(msg),
            "out_len": 32,
            "expected_digest": digest.hex(),
        })
        tc_counter += 1

    # Test SHA3-384 (48 bytes output)
    for msg, label in msg_patterns:
        digest = compute_fips202_reference("SHA3-384", msg, 48)
        test_cases.append({
            "tcId": f"dr9_sha3_384_{tc_counter:03d}_{label}",
            "function": "SHA3-384",
            "func_id": 3,
            "msg": msg.hex(),
            "msg_len": len(msg),
            "out_len": 48,
            "expected_digest": digest.hex(),
        })
        tc_counter += 1

    # Test SHA3-512 (64 bytes output)
    for msg, label in msg_patterns:
        digest = compute_fips202_reference("SHA3-512", msg, 64)
        test_cases.append({
            "tcId": f"dr9_sha3_512_{tc_counter:03d}_{label}",
            "function": "SHA3-512",
            "func_id": 4,
            "msg": msg.hex(),
            "msg_len": len(msg),
            "out_len": 64,
            "expected_digest": digest.hex(),
        })
        tc_counter += 1

    # Test SHAKE128 with varying squeeze lengths (16, 32, 64, 168, 256, 512, 1024 bytes)
    shake128_squeezes = [16, 32, 64, 168, 256, 512, 1024]
    for sq_len in shake128_squeezes:
        for msg, label in msg_patterns[:5]:
            digest = compute_fips202_reference("SHAKE128", msg, sq_len)
            test_cases.append({
                "tcId": f"dr9_shake128_{tc_counter:03d}_{label}_sq{sq_len}",
                "function": "SHAKE128",
                "func_id": 5,
                "msg": msg.hex(),
                "msg_len": len(msg),
                "out_len": sq_len,
                "expected_digest": digest.hex(),
            })
            tc_counter += 1

    # Test SHAKE256 with varying squeeze lengths (16, 32, 64, 136, 256, 512, 1024 bytes)
    shake256_squeezes = [16, 32, 64, 136, 256, 512, 1024]
    for sq_len in shake256_squeezes:
        for msg, label in msg_patterns[:5]:
            digest = compute_fips202_reference("SHAKE256", msg, sq_len)
            test_cases.append({
                "tcId": f"dr9_shake256_{tc_counter:03d}_{label}_sq{sq_len}",
                "function": "SHAKE256",
                "func_id": 6,
                "msg": msg.hex(),
                "msg_len": len(msg),
                "out_len": sq_len,
                "expected_digest": digest.hex(),
            })
            tc_counter += 1

    return {
        "metadata": {
            "standard": "NIST FIPS 202",
            "milestone": "DR9",
            "total_cases": len(test_cases),
            "functions": ["SHA3-224", "SHA3-256", "SHA3-384", "SHA3-512", "SHAKE128", "SHAKE256"]
        },
        "cases": test_cases
    }

if __name__ == "__main__":
    ds = generate_dr9_test_vectors()
    out_path = Path("tests/pqc_device_resident/data/dr9_nist_fips202_vectors.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ds, indent=2))
    print(f"Generated {len(ds['cases'])} DR9 NIST FIPS 202 test vectors at {out_path}")
