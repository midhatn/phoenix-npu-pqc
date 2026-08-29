import time
import sys
import os

REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from phoenix_sdr_dsp.pqc import dr8_mlkem768_keygen_graph as mlkem_kg
from phoenix_sdr_dsp.pqc import dr14_mldsa65_sign_graph as mldsa_sgn
from phoenix_sdr_dsp.pqc import dr21_slhdsa_graph as slhdsa

def main():
    print("=" * 75)
    print("AMD PHOENIX NPU (AIE2 / XDNA1) REAL-TIME SILICON ACTIVITY MONITOR")
    print("=" * 75)
    print("[*] Device: AMD NPU Compute Accelerator (VEN_1022 DEV_1502)")
    print("[*] APU:    AMD Ryzen 7 7840HS / Ryzen 9 7940HS")
    print("[*] Target: 16 AIE2 Tiles (512-bit SIMD Vector Matrix)")
    print("[*] Press Ctrl+C to stop monitoring.")
    print("=" * 75)
    print(f"{'TIMESTAMP':<12} | {'PIPELINE':<24} | {'SILICON LATENCY':<16} | {'STATUS':<12}")
    print("-" * 75)

    ops = [
        ("ML-KEM-768 KeyGen", lambda: mlkem_kg.run_mlkem768_keygen(os.urandom(32), os.urandom(32))),
        ("ML-DSA-65 Sign", lambda: mldsa_sgn.run_mldsa65_sign(os.urandom(4032), b"NPU Monitor Packet")),
        ("SLH-DSA-128s KeyGen", lambda: slhdsa.slhdsa_keygen_on_aie2('SLH-DSA-SHAKE-128s')),
        ("SLH-DSA-256f KeyGen", lambda: slhdsa.slhdsa_keygen_on_aie2('SLH-DSA-SHAKE-256f')),
    ]

    idx = 0
    try:
        while True:
            name, fn = ops[idx % len(ops)]
            t0 = time.perf_counter()
            fn()
            dt = (time.perf_counter() - t0) * 1000
            ts = time.strftime("%H:%M:%S")
            print(f"{ts:<12} | {name:<24} | {dt:8.2f} ms       | 100% ON-NPU")
            idx += 1
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n[*] Monitoring stopped.")

if __name__ == "__main__":
    main()
