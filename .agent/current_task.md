# Current Task

## Task

`DR24-IPSEC-WIREGUARD-KEM`: Implement AIE2 tile kernel offload and session handshake orchestration for IPsec/IKEv2 (RFC 9370) and WireGuard Post-Quantum Multi-KEM tunnels.

## Status

`IN_PROGRESS` (Milestone DR24).
- Prior Milestones:
  1. `DR2d` (ML-KEM-512 K-PKE KeyGen): `COMPLETED` (25/25 vectors PASS, PR #10, protected archive at `C:\Projects\phoenix-validation-evidence\dr2d-a0405851-20260901`).
  2. `DR14` (ML-DSA-65 KeyGen, Sign, Verify): `COMPLETED` (85/85 vectors PASS, PR #13).
  3. `DR15` (ML-DSA-87 KeyGen, Sign, Verify): `COMPLETED` (85/85 vectors PASS, PR #15).
  4. `DR16-DR19, DR27` (Extension Gates Framed Evidence Migration): `COMPLETED` (121/121 cases PASS, PR #16).
  5. `DR21` (NIST FIPS 205 SLH-DSA KeyGen, Sign, Verify): `COMPLETED` (30/30 cases PASS, PR #17).
  6. `DR22` (NIST FIPS 206 FN-DSA KeyGen, Sign, Verify): `COMPLETED` (30/30 cases PASS, PR #18).
  7. `DR23` (OpenSSL 3.x Provider & OASIS PKCS#11 HSM): `COMPLETED` (25/25 cases PASS, PR #19).
  8. Native Silicon Validation Baseline: 27 native gates reporting structured framed evidence on AMD Phoenix NPU silicon.

## Next Action
Design and implement AIE2 hardware-accelerated Multi-KEM combiner and packet encapsulation/decapsulation for IPsec/IKEv2 and WireGuard PQC tunnels in `phoenix_sdr_dsp/pqc/dr24_ipsec_wireguard.py`.
