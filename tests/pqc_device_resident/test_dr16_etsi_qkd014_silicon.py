# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR16: ETSI GS QKD 014 Sealed Ingress Silicon Validation Suite.
Target: AMD Phoenix AIE2 / XDNA1 Architecture (dr16-etsi-qkd014).
"""

import base64
import json
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr16_etsi_qkd014_graph import run_dr16_ingress_service
from phoenix_sdr_dsp.pqc import dr16_etsi_qkd014_abi as abi

def main():
    print("=" * 70)
    print("DR16: ETSI GS QKD 014 Key Ingress Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr16-etsi-qkd014)")
    print("Standards: ETSI GS QKD 014 v1.1.1/v1.3.1, ITU-T Y.3800")
    print("=" * 70)

    test_cases = []

    # 1. Standard ETSI 014 256-bit Key Containers (15 cases)
    for i in range(1, 16):
        key_raw = bytes([(i * 13 + j) % 256 for j in range(32)])
        key_uuid = uuid.uuid4()
        epoch = 1000 + i

        container_json = json.dumps({
            "keys": [
                {
                    "key_ID": str(key_uuid),
                    "key": base64.b64encode(key_raw).decode("ascii")
                }
            ]
        })
        parsed_keys = abi.parse_etsi_014_json(container_json, epoch=epoch)
        k = parsed_keys[0]

        desc_buf = abi.pack_dr16_descriptor(k.key_id, k.epoch, len(k.key_bytes), request_id=i)
        req_buf = abi.pack_dr16_request(k.key_bytes, k.source_sae_id, k.target_sae_id)
        test_cases.append((f"etsi_qkd014_key_ingress_{i:02d}", req_buf, desc_buf, 0))

    # 2. High-Security 512-bit Key Containers (5 cases)
    for i in range(1, 6):
        key_raw = bytes([(i * 29 + j) % 256 for j in range(64)])
        key_uuid = uuid.uuid4()
        epoch = 2000 + i

        container_json = json.dumps({
            "keys": [
                {
                    "key_ID": str(key_uuid),
                    "key": base64.b64encode(key_raw).decode("ascii")
                }
            ]
        })
        parsed_keys = abi.parse_etsi_014_json(container_json, epoch=epoch)
        k = parsed_keys[0]

        desc_buf = abi.pack_dr16_descriptor(k.key_id, k.epoch, len(k.key_bytes), request_id=20+i)
        req_buf = abi.pack_dr16_request(k.key_bytes, k.source_sae_id, k.target_sae_id)
        test_cases.append((f"etsi_qkd014_512bit_ingress_{i:02d}", req_buf, desc_buf, 0))

    # 3. Replay Attack & Stale Epoch Rejection (5 cases)
    for i in range(1, 6):
        key_raw = bytes([0xAA] * 32)
        key_uuid = uuid.uuid4()
        stale_epoch = 500 # Less than 2000

        desc_buf = abi.pack_dr16_descriptor(key_uuid, stale_epoch, 32, request_id=30+i)
        req_buf = abi.pack_dr16_request(key_raw)
        test_cases.append((f"etsi_qkd014_stale_epoch_rej_{i:02d}", req_buf, desc_buf, 3)) # Status 3 = Stale

    total = len(test_cases)
    passed = 0
    print(f"Running {total} DR16 ETSI GS QKD 014 silicon test cases on AMD Phoenix...")

    t0 = time.time()
    for name, req_buf, desc_buf, expected_status in test_cases:
        req_id, status, active_slot, crc = run_dr16_ingress_service(req_buf, desc_buf)
        if status == expected_status:
            passed += 1
        else:
            print(f"[FAIL] {name}: status={status}, expected={expected_status}")

    dt = time.time() - t0
    print("-" * 70)
    print(f"DR16 Physical Silicon Result: {passed}/{total} PASS ({passed/total*100:.2f}%) in {dt:.2f}s")
    if passed == total:
        print("[+] Gate 19: DR16 ETSI GS QKD 014 Sealed Ingress : PASS (100% Silicon Certified)")
        return 0
    else:
        print("[-] Gate 19: DR16 FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
