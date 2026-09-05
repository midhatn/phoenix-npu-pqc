# SPDX-License-Identifier: Apache-2.0
"""Milestone DR33: Physical Side-Channel Power/EM Trace Acquisition & TVLA Framework ABI.
Defines descriptors, request marshaling, trigger packet unpackers, and ISO/IEC 17825 TVLA statistical engine.
Execution Boundaries:
  - Trigger packet emission on AIE2 hardware: [ON-TILE SILICON]
  - TVLA statistical Welch's t-test processing: [HOST RUNTIME]
"""

import math
import struct
import numpy as np
from typing import Dict, Any, Tuple, Optional, List
from dataclasses import dataclass

# Magic identifier: ASCII 'TVLA' (0x54564C41)
MAGIC_DESC_DR33              = 0x54564C41

# Operation Modes
MODE_TVLA_TRIGGER_EMIT      = 0x01
MODE_TVLA_FIXED_VS_RANDOM   = 0x02
MODE_TVLA_CALIBRATION_PULSE = 0x03
MODE_TVLA_MASKED_PIPELINE   = 0x04

# Target Cryptographic Workloads
TARGET_ML_KEM_NTT           = 0x01
TARGET_ML_DSA_POLY          = 0x02
TARGET_KECCAK_F1600         = 0x03
TARGET_MASKED_MULT          = 0x04

# Trigger Phase Markers
PHASE_IDLE                  = 0x00
PHASE_START_TRIGGER         = 0x01
PHASE_PRE_EXECUTION         = 0x02
PHASE_CORE_COMPUTE          = 0x03
PHASE_POST_EXECUTION        = 0x04
PHASE_STOP_TRIGGER          = 0x05

# Status Codes
STATUS_SUCCESS              = 0x00000000
STATUS_ERR_INVALID_MAGIC    = 0xDEAD0033
STATUS_ERR_UNKNOWN_MODE     = 0xDEAD0034
STATUS_ERR_UNKNOWN_TARGET   = 0xDEAD0035

# Buffer Dimensions (matching AIE2 memory layout)
REQ_TOTAL_BYTES             = 16384
DESC_TOTAL_BYTES            = 64
RESULT_TOTAL_BYTES          = 2048

# TVLA Decision Boundary (NIST SP 800-140F / NIAT threshold)
TVLA_DEFAULT_THRESHOLD      = 4.5

Q_MLKEM = 3329
Q_INV   = 62209


@dataclass
class TriggerPacket:
    """Hardware Trigger & Synchronization Telemetry Packet (64 bytes)."""
    magic: int
    op_mode: int
    status: int
    target_algo: int
    seq_id: int
    trigger_phase: int
    cycle_estimate: int
    workload_accum: int
    canary: bytes


def pack_dr33_descriptor(
    op_mode: int = MODE_TVLA_TRIGGER_EMIT,
    target_algo: int = TARGET_ML_KEM_NTT,
    seq_id: int = 1,
    input_len: int = 512,
    sample_rate_khz: int = 10000,
    flags: int = 0,
    trace_points: int = 16,
) -> bytes:
    """Packs the 64-byte DR33 AIE2 hardware descriptor."""
    desc = bytearray(DESC_TOTAL_BYTES)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR33,
        op_mode,
        target_algo,
        seq_id,
        input_len,
        sample_rate_khz,
        flags,
        trace_points,
    )
    return bytes(desc)


def pack_dr33_request(
    input_coeffs_or_seed: bytes,
    seq_id: int = 1,
    target_algo: int = TARGET_ML_KEM_NTT,
) -> bytes:
    """Packs the 16384-byte request tensor for DR33 side-channel trigger execution."""
    req = bytearray(REQ_TOTAL_BYTES)
    # Header: offset 0..31
    struct.pack_into(
        "<IIII",
        req,
        0,
        MAGIC_DESC_DR33,
        seq_id,
        target_algo,
        len(input_coeffs_or_seed),
    )
    # Payload: offset 32 onwards
    copy_len = min(len(input_coeffs_or_seed), REQ_TOTAL_BYTES - 32)
    req[32 : 32 + copy_len] = input_coeffs_or_seed[:copy_len]
    return bytes(req)


def unpack_dr33_result(result_bytes: bytes) -> Dict[str, Any]:
    """Unpacks the 2048-byte result tensor from DR33 AIE2 hardware."""
    if len(result_bytes) < RESULT_TOTAL_BYTES:
        raise ValueError(
            f"Invalid DR33 result length {len(result_bytes)} < {RESULT_TOTAL_BYTES}"
        )

    magic, op_mode, status, target_algo, seq_id, phase, cycles, accum = (
        struct.unpack_from("<IIIIIIII", result_bytes, 0)
    )
    canary = bytes(result_bytes[32:64])
    output_poly = bytes(result_bytes[64:576])
    trace_samples = list(struct.unpack_from("<16I", result_bytes, 576))

    trigger_pkt = TriggerPacket(
        magic=magic,
        op_mode=op_mode,
        status=status,
        target_algo=target_algo,
        seq_id=seq_id,
        trigger_phase=phase,
        cycle_estimate=cycles,
        workload_accum=accum,
        canary=canary,
    )

    return {
        "magic": magic,
        "op_mode": op_mode,
        "status": status,
        "target_algo": target_algo,
        "seq_id": seq_id,
        "trigger_phase": phase,
        "cycle_estimate": cycles,
        "workload_accum": accum,
        "canary": canary,
        "trigger_packet": trigger_pkt,
        "output_poly_bytes": output_poly,
        "trace_samples": trace_samples,
    }


def compute_welch_ttest(
    fixed_traces: np.ndarray,
    random_traces: np.ndarray,
    threshold: float = TVLA_DEFAULT_THRESHOLD,
) -> Dict[str, Any]:
    """[HOST RUNTIME] Evaluates Welch's two-sample t-test across aligned time-series traces.
    Formula:
        t(k) = (mean_fixed(k) - mean_random(k)) / sqrt(var_fixed(k)/N_fixed + var_random(k)/N_random)
    Rejects null hypothesis of no information leakage when max(|t(k)|) > threshold (typically 4.5).
    """
    n_fixed = fixed_traces.shape[0]
    n_random = random_traces.shape[0]

    if n_fixed < 2 or n_random < 2:
        raise ValueError("TVLA evaluation requires at least 2 traces in each set.")

    # Compute sample means
    mean_fixed = np.mean(fixed_traces, axis=0)
    mean_random = np.mean(random_traces, axis=0)

    # Compute sample variances with ddof=1 (unbiased estimator)
    var_fixed = np.var(fixed_traces, axis=0, ddof=1)
    var_random = np.var(random_traces, axis=0, ddof=1)

    # Standard error of the difference
    se = np.sqrt((var_fixed / n_fixed) + (var_random / n_random))
    # Protect against divide-by-zero on completely invariant baseline points
    se_safe = np.where(se == 0.0, 1e-12, se)

    # Welch t-statistic per sample point
    t_scores = (mean_fixed - mean_random) / se_safe
    max_abs_t = float(np.max(np.abs(t_scores)))
    leakage_point = int(np.argmax(np.abs(t_scores)))
    leak_detected = max_abs_t > threshold

    return {
        "execution_label": "[HOST RUNTIME]",
        "n_fixed": n_fixed,
        "n_random": n_random,
        "trace_points": int(fixed_traces.shape[1]),
        "threshold": threshold,
        "max_abs_t": max_abs_t,
        "leakage_point": leakage_point,
        "leak_detected": leak_detected,
        "t_scores": t_scores.tolist(),
        "status": "LEAKAGE_DETECTED" if leak_detected else "NO_LEAKAGE_DETECTED",
    }


def generate_tvla_synthetic_traces(
    num_traces: int = 500,
    points_per_trace: int = 64,
    inject_leakage: bool = False,
    leak_point: int = 32,
    noise_sigma: float = 1.0,
    leakage_magnitude: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generates synthetic aligned power/EM trace matrices for fixed-vs-random TVLA evaluation.
    Used to validate the statistical evaluation harness with and without injected leakage.
    """
    rng = np.random.default_rng(seed=0x33445566)

    # Base profile for cryptographic operation
    t = np.linspace(0, 4 * np.pi, points_per_trace)
    base_profile = np.sin(t) * 2.0 + np.cos(2 * t) * 1.5

    # Generate fixed traces (constant input + noise)
    fixed_noise = rng.normal(0.0, noise_sigma, size=(num_traces, points_per_trace))
    fixed_traces = base_profile + fixed_noise

    # Generate random traces (varying inputs + noise)
    random_noise = rng.normal(0.0, noise_sigma, size=(num_traces, points_per_trace))
    random_traces = base_profile + random_noise

    if inject_leakage:
        # In fixed traces, add a constant offset representing secret-dependent consumption
        fixed_traces[:, leak_point] += leakage_magnitude

    return fixed_traces, random_traces


# =========================================================================
# Independent Host Reference Oracle for Bit-Exact Output Verification
# =========================================================================

def _montgomery_reduce_py(a: int) -> int:
    t = (a & 0xFFFF) * Q_INV
    t = (t & 0xFFFF)
    if t >= 0x8000:
        t -= 0x10000
    res = (a - t * Q_MLKEM) >> 16
    return res


def _barrett_reduce_py(a: int) -> int:
    t = (a * 20159) >> 26
    return a - t * Q_MLKEM


def reference_dr33_oracle(desc_bytes: bytes, req_bytes: bytes) -> bytes:
    """Independent host reference oracle reproducing exact 2048-byte AIE2 output buffer."""
    magic, op_mode, target_algo, seq_id, in_len, sample_rate, flags, trace_pts = (
        struct.unpack_from("<IIIIIIII", desc_bytes, 0)
    )

    result = bytearray(RESULT_TOTAL_BYTES)

    if magic != MAGIC_DESC_DR33:
        struct.pack_into("<III", result, 0, STATUS_ERR_INVALID_MAGIC, op_mode, 1)
        return bytes(result)

    if in_len == 0 or in_len > 16000:
        in_len = 512

    in_payload = req_bytes[32 : 32 + in_len]
    num_coeffs = 256
    coeffs_in = []
    for i in range(num_coeffs):
        idx = (i * 2) % len(in_payload)
        if idx + 1 < len(in_payload):
            val = in_payload[idx] | (in_payload[idx + 1] << 8)
        else:
            val = in_payload[idx]
        coeffs_in.append(val)

    coeffs_out = []
    accum = 0
    for i in range(num_coeffs):
        coeff = coeffs_in[i] & 0xFFFF

        if target_algo == TARGET_ML_KEM_NTT:
            if coeff >= 0x8000:
                c_signed = coeff - 0x10000
            else:
                c_signed = coeff
            twiddle = (i * 17 + 1) % Q_MLKEM
            prod = c_signed * twiddle
            red = _montgomery_reduce_py(prod)
            fin = _barrett_reduce_py(red) & 0xFFFF
            coeffs_out.append(fin)
            accum = (accum + fin) & 0xFFFFFFFF
        elif target_algo == TARGET_ML_DSA_POLY:
            val = (coeff * 3 + 7) % 8380417
            fin = val & 0xFFFF
            coeffs_out.append(fin)
            accum = (accum ^ fin) & 0xFFFFFFFF
        elif target_algo == TARGET_MASKED_MULT:
            mask = ((i * 0x9E37) ^ 0x55AA) & 0xFFFF
            s0 = (coeff ^ mask) & 0xFFFF
            s1 = mask
            fin = (s0 ^ s1) & 0xFFFF
            coeffs_out.append(fin)
            accum = (accum + fin) & 0xFFFFFFFF
        else:
            rot = (((coeff << 5) & 0xFFFF) | (coeff >> 11)) & 0xFFFF
            fin = (rot ^ 0x96) & 0xFFFF
            coeffs_out.append(fin)
            accum = ((accum << 1) ^ fin) & 0xFFFFFFFF

    cycle_estimate = 120 + 80 + 1450 + 60 + 40  # 1750
    current_phase = PHASE_STOP_TRIGGER

    # Header packet
    struct.pack_into(
        "<IIIIIIII",
        result,
        0,
        MAGIC_DESC_DR33,
        op_mode,
        STATUS_SUCCESS,
        target_algo,
        seq_id,
        current_phase,
        cycle_estimate,
        accum,
    )

    # Canary
    result[32:40] = b"PQC33TVL"
    for k in range(40, 64):
        result[k] = (k ^ target_algo) & 0xFF

    # Polynomial output
    for i in range(num_coeffs):
        struct.pack_into("<H", result, 64 + i * 2, coeffs_out[i])

    # Trace samples
    for p in range(16):
        sample = ((accum >> (p % 16)) ^ (cycle_estimate * (p + 1))) & 0xFFFFFFFF
        struct.pack_into("<I", result, 576 + p * 4, sample)

    return bytes(result)
