# Purpose: Twiddle table generator for Milestone 17 v3 (radix-4 Stockham FFT).
# Target: pack complex twiddles as Ozaki-style 4-slice bfloat16 splits, matching
# the layout expected by diacccc/FFT_R4_AIE's kernel/fft_stockham_f32.cc.
#
# Reference: diacccc/FFT_R4_AIE/test.cpp lines 205-256.
# License: this file is Apache-2.0 WITH LLVM-exception (derives layout from AMD's
# reference); Copyright (C) 2026, midhatn.

import numpy as np
from ml_dtypes import bfloat16


def split_to_bf16(x: float) -> tuple:
    remainder = np.float32(x)
    slices = [None] * 4
    for i in range(4):
        bf = bfloat16(remainder)
        slices[i] = bf
        remainder = np.float32(remainder) - np.float32(bf)
    return tuple(slices)


def pack_twiddles_r4_stockham(N: int, over_provision: bool = True) -> np.ndarray:
    if N < 4 or (N & (N - 1)) != 0:
        raise ValueError(f"N must be a power of 2 (and specifically 4^k); got {N}")
    log2n = int(np.log2(N))
    if log2n % 2 != 0:
        raise ValueError(f"N must be a power of 4; got N={N} (log2={log2n} is odd)")

    used_size = 0
    s = 1
    while s < N:
        used_size += 24 * s
        s <<= 2

    buf_size = (N * 8) if over_provision else used_size
    tw = np.zeros(buf_size, dtype=bfloat16)

    stage_twiddle_base = 0
    s = 1
    while s < N:
        n_stage = N // s
        m = n_stage // 4

        for q in range(s):
            for tw_idx in range(3):
                k = q * m * (tw_idx + 1)
                angle = -2.0 * np.pi * k / N
                twr = float(np.cos(angle))
                twi = float(np.sin(angle))

                r_splits = split_to_bf16(twr)
                i_splits = split_to_bf16(twi)

                q_base = stage_twiddle_base + q * 24
                tw_base = q_base + tw_idx * 8

                tw[tw_base + 0] = r_splits[0]
                tw[tw_base + 1] = i_splits[0]
                tw[tw_base + 2] = r_splits[1]
                tw[tw_base + 3] = i_splits[1]
                tw[tw_base + 4] = r_splits[2]
                tw[tw_base + 5] = i_splits[2]
                tw[tw_base + 6] = r_splits[3]
                tw[tw_base + 7] = i_splits[3]

        stage_twiddle_base += 24 * s
        s <<= 2

    return tw


def reconstruct_twiddle(tw: np.ndarray, N: int, stage: int, q: int, tw_idx: int) -> complex:
    stage_base = 0
    s = 1
    for st in range(stage):
        stage_base += 24 * s
        s <<= 2
    q_base = stage_base + q * 24
    tw_base = q_base + tw_idx * 8

    r_sum = np.float32(0.0)
    i_sum = np.float32(0.0)
    for slot in range(4):
        r_sum += np.float32(tw[tw_base + 2 * slot])
        i_sum += np.float32(tw[tw_base + 2 * slot + 1])
    return complex(float(r_sum), float(i_sum))


def _selftest():
    N = 64
    tw = pack_twiddles_r4_stockham(N, over_provision=True)
    print(f"=== Twiddle Table Self-Test: N={N} ===")
    print(f"Buffer size:       {len(tw)} bfloat16 elements ({len(tw)*2} bytes)")
    log4n = 3
    used = sum(24 * (4**i) for i in range(log4n))
    print(f"Used slots:        {used}")
    print(f"Zero-padded slots: {len(tw) - used}")
    print()

    print(f"{'Stage':<6} {'s':<4} {'m':<4} {'q':<4} {'tw':<4} {'expected':<50} {'reconstructed':<50} {'abs_err':<12}")
    print("-" * 140)

    max_err = 0.0
    s = 1
    stage = 0
    while s < N:
        n_stage = N // s
        m = n_stage // 4
        q_samples = sorted({0, s // 2, s - 1}) if s > 1 else [0]
        for q in q_samples:
            for tw_idx in range(3):
                k = q * m * (tw_idx + 1)
                angle = -2.0 * np.pi * k / N
                expected = complex(np.cos(angle), np.sin(angle))
                reconstructed = reconstruct_twiddle(tw, N, stage, q, tw_idx)
                err = abs(expected - reconstructed)
                max_err = max(max_err, err)
                print(f"{stage:<6} {s:<4} {m:<4} {q:<4} {tw_idx:<4} "
                      f"{str(expected):<50} {str(reconstructed):<50} {err:.3e}")
        s <<= 2
        stage += 1

    print()
    print(f"Max abs error across sampled twiddles: {max_err:.3e}")
    TOL = 1e-4
    if max_err < TOL:
        print(f"PASS: max_err < {TOL}")
        return 0
    else:
        print(f"FAIL: max_err >= {TOL}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())