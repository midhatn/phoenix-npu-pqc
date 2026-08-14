//===- fft_stockham_f32.cc --------------------------------*- C++ -*-===//
//
// This file is licensed under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
// Adapted from diacccc/FFT_R4_AIE
//   https://github.com/diacccc/FFT_R4_AIE
//   Copyright (C) 2025-2026, Advanced Micro Devices, Inc.
//
// Adapted for Phoenix-SDR-DSP M17 v3 (N=64 radix-4 Stockham FFT on aie2p).
// Adaptation: attribution header only; algorithm unchanged from upstream.
// Copyright (C) 2026, midhatn.
//
//===----------------------------------------------------------------------===//

#define NOCPP

#include <aie_api/aie.hpp>

#ifndef FFT_SIZE
#define FFT_SIZE 256
#endif

// Radix-4 FFT requires N to be a power of 4

#define PROFILING 1


static volatile unsigned long long g_fft_stockham_cycles = 0;
static volatile unsigned long long g_fft_elemwise_cycles = 0;
static volatile unsigned long long g_fft_butterfly_cycles = 0;

constexpr unsigned kSplitCount = 4;
constexpr unsigned kTwiddlesPerQ = 3;
constexpr unsigned kComplexSplitWidth = 8; // [r0,i0,r1,i1,r2,i2,r3,i3]
constexpr unsigned kTwiddleBlockPerQ = kTwiddlesPerQ * kComplexSplitWidth;

template <typename T_out, unsigned size>
static inline void zero_vectorized(T_out *__restrict c) {
  constexpr unsigned r = 512 / (sizeof(T_out) * 8); // 512 bit store units for AIE2P
  static_assert(size % r == 0);
  const aie::vector<T_out, r> zeros = aie::zeros<T_out, r>();
  const T_out *__restrict c_end = c + size;
  for (; c < c_end; c += r) {
    aie::store_v(c, zeros);
  }
}

// Compute log4 of N at compile time
constexpr unsigned log4_const(unsigned n) {
  return (n <= 1) ? 0 : 1 + log4_const(n / 4);
}


// Radix-4 Stockham FFT Algorithm
// ============================================================================
// Radix-4 DIT Stockham auto-sort FFT: no bit-reversal needed, naturally sorted output
// Each stage processes 4 points at a time using radix-4 butterfly
//
// Radix-4 DIT butterfly:
//   a = x[q + s*(p + 0*m)]
//   b = x[q + s*(p + 1*m)] * W_N^(q*m)
//   c = x[q + s*(p + 2*m)] * W_N^(q*2*m)
//   d = x[q + s*(p + 3*m)] * W_N^(q*3*m)
//
//   y[q + s*(4*p + 0)] = a + b + c + d
//   y[q + s*(4*p + 1)] = a - j*b - c + j*d
//   y[q + s*(4*p + 2)] = a - b + c - d
//   y[q + s*(4*p + 3)] = a + j*b - c - j*d
//
// Stage progression: n -> n/4, s -> 4*s

template <unsigned N>
static inline void fft_stockham_gemm(float *__restrict x,
                                      const bfloat16 *__restrict twiddle,
                                      float *__restrict y) {
  constexpr unsigned LOG4N = log4_const(N);
  unsigned long long elemwise_cycles = 0;
  unsigned long long butterfly_cycles = 0;

  // Stage 0 has s=1 and q=0 only, so no twiddle factors are needed.
  if constexpr (LOG4N > 0) {
    constexpr unsigned Q_TILE = 4;
    constexpr unsigned stage0 = 0;
    const unsigned n = N >> (2 * stage0);  // n = N
    const unsigned s = 1u << (2 * stage0); // s = 1
    const unsigned m = n >> 2;             // m = N / 4

    float butterfly_in[Q_TILE][8];
    float butterfly_out[Q_TILE][8];

    for (unsigned p0 = 0; p0 < m; p0 += Q_TILE) {
      const unsigned p_lim = ((p0 + Q_TILE) < m) ? (p0 + Q_TILE) : m;
      const unsigned rows = p_lim - p0;

      for (unsigned p = p0; p < p_lim; ++p) {
        const unsigned t = p - p0;
        const unsigned idx_a = 0 + s * (p + 0 * m);
        const unsigned idx_b = 0 + s * (p + 1 * m);
        const unsigned idx_c = 0 + s * (p + 2 * m);
        const unsigned idx_d = 0 + s * (p + 3 * m);

        const float a_real = x[2 * idx_a];
        const float a_imag = x[2 * idx_a + 1];
        const float b_real = x[2 * idx_b];
        const float b_imag = x[2 * idx_b + 1];
        const float c_real = x[2 * idx_c];
        const float c_imag = x[2 * idx_c + 1];
        const float d_real = x[2 * idx_d];
        const float d_imag = x[2 * idx_d + 1];

        butterfly_in[t][0] = a_real;
        butterfly_in[t][1] = a_imag;
        butterfly_in[t][2] = b_real;
        butterfly_in[t][3] = b_imag;
        butterfly_in[t][4] = c_real;
        butterfly_in[t][5] = c_imag;
        butterfly_in[t][6] = d_real;
        butterfly_in[t][7] = d_imag;
      }
      unsigned long long butterfly_start = 0;
      if constexpr (PROFILING) {
        butterfly_start = get_cycles();
      }

      alignas(aie::vector_decl_align) static bfloat16 coeff_buf[64] = {
        1,  0,  1,  0,  1,  0,  1,  0,
        0,  1,  0,  1,  0,  1,  0,  1,
        1,  0,  0, -1, -1,  0,  0,  1,
        0,  1,  1,  0,  0, -1, -1,  0,
        1,  0, -1,  0,  1,  0, -1,  0,
        0,  1,  0, -1,  0,  1,  0, -1,
        1,  0,  0,  1, -1,  0,  0, -1,
        0,  1, -1,  0,  0, -1,  1,  0,
      };
      aie::vector<bfloat16, 64> coeff_vecs;
      coeff_vecs = aie::load_v<64>(coeff_buf);
      aie::accum<accfloat, 32> in_vecs;
      in_vecs = aie::load_v<32>(&butterfly_in[0][0]);
      aie::accum<accfloat, 32> tmp_splits;

      using MMUL = aie::mmul<4, 8, 8, bfloat16, bfloat16, accfloat>;
      MMUL OUT;
      aie::vector<bfloat16, 32> in_splits = in_vecs.template to_vector<bfloat16>();
      OUT.mul(in_splits, coeff_vecs);
      for (unsigned k = 1; k < kSplitCount; ++k) {
        tmp_splits.from_vector(in_splits);
        in_vecs = aie::sub(in_vecs, tmp_splits);
        in_splits = in_vecs.template to_vector<bfloat16>();
        OUT.mac(in_splits, coeff_vecs);
      }
      aie::store_v(&butterfly_out[0][0], OUT.template to_vector<float>());

      if constexpr (PROFILING) {
        butterfly_cycles += get_cycles() - butterfly_start;
      }
      
      for (unsigned p = p0; p < p_lim; ++p) {
        const unsigned t = p - p0;
        const unsigned out_idx0 = 0 + s * (4 * p + 0);
        const unsigned out_idx1 = 0 + s * (4 * p + 1);
        const unsigned out_idx2 = 0 + s * (4 * p + 2);
        const unsigned out_idx3 = 0 + s * (4 * p + 3);

        y[2 * out_idx0] = butterfly_out[t][0];
        y[2 * out_idx0 + 1] = butterfly_out[t][1];
        y[2 * out_idx1] = butterfly_out[t][2];
        y[2 * out_idx1 + 1] = butterfly_out[t][3];
        y[2 * out_idx2] = butterfly_out[t][4];
        y[2 * out_idx2 + 1] = butterfly_out[t][5];
        y[2 * out_idx3] = butterfly_out[t][6];
        y[2 * out_idx3 + 1] = butterfly_out[t][7];
      }
    }
  }

  // Preserve twiddle table compatibility by skipping the stage-0 slot.
  unsigned stage_twiddle_base = kTwiddleBlockPerQ;

  for (unsigned stage = 1; stage < LOG4N; ++stage) {
    float *src = (stage % 2 == 0) ? x : y;
    float *dst = (stage % 2 == 0) ? y : x;

    const unsigned n = N >> (2 * stage);  // n = N / 4^stage
    const unsigned s = 1u << (2 * stage); // s = 4^stage
    const unsigned m = n >> 2;             // m = n / 4
    const bfloat16 *stage_twiddle = &twiddle[stage_twiddle_base];

    // Scalar q-unrolled format: process 4 q values together for each p.
    constexpr unsigned Q_TILE = 4;
    float butterfly_in[Q_TILE][8];
    float butterfly_out[Q_TILE][8];
    bfloat16 twiddle_buf[kSplitCount][Q_TILE][8];

    for (unsigned p = 0; p < m; ++p) {
      for (unsigned q0 = 0; q0 < s; q0 += Q_TILE) {
        const unsigned q_lim = ((q0 + Q_TILE) < s) ? (q0 + Q_TILE) : s;
        const unsigned rows = q_lim - q0;

        for (unsigned k = 0; k < kSplitCount; ++k) {
          for (unsigned r = 0; r < Q_TILE; ++r) {
            for (unsigned c = 0; c < 8; ++c) {
              twiddle_buf[k][r][c] = (bfloat16)0;
            }
          }
        }
        
        for (unsigned q = q0; q < q_lim; ++q) {
          const unsigned t = q - q0;
          const unsigned idx_a = q + s * (p + 0 * m);
          const unsigned idx_b = q + s * (p + 1 * m);
          const unsigned idx_c = q + s * (p + 2 * m);
          const unsigned idx_d = q + s * (p + 3 * m);

          const bfloat16 *twq = stage_twiddle + kTwiddleBlockPerQ * q;
          
          for (unsigned k = 0; k < kComplexSplitWidth / 2; ++k) {
            twiddle_buf[k][t][0] = (k == 0) ? (bfloat16)1 : (bfloat16)0;
            twiddle_buf[k][t][1] = (bfloat16)0;
            twiddle_buf[k][t][2] = twq[2 * k];
            twiddle_buf[k][t][3] = twq[2 * k + 1];
            twiddle_buf[k][t][4] = twq[kComplexSplitWidth + 2 * k];
            twiddle_buf[k][t][5] = twq[kComplexSplitWidth + 2 * k + 1];
            twiddle_buf[k][t][6] = twq[2 * kComplexSplitWidth + 2 * k];
            twiddle_buf[k][t][7] = twq[2 * kComplexSplitWidth + 2 * k + 1];
          }

          butterfly_in[t][0] = src[2 * idx_a];
          butterfly_in[t][1] = src[2 * idx_a + 1];
          butterfly_in[t][2] = src[2 * idx_b];
          butterfly_in[t][3] = src[2 * idx_b + 1];
          butterfly_in[t][4] = src[2 * idx_c];
          butterfly_in[t][5] = src[2 * idx_c + 1];
          butterfly_in[t][6] = src[2 * idx_d];
          butterfly_in[t][7] = src[2 * idx_d + 1];
        }
        // Element-wise complex multiplication
        unsigned long long elemwise_start = 0;
        if constexpr (PROFILING) {
          elemwise_start = get_cycles();
        }
        {
        aie::accum<accfloat, 32> in_vecs;
        in_vecs = aie::load_v<32>(&butterfly_in[0][0]);
        aie::vector<bfloat16, 32> tw_vecs[kSplitCount];
        for (unsigned i = 0; i < kSplitCount; ++i) {
          tw_vecs[i] = aie::load_v<32>(&twiddle_buf[i][0][0]);
        }
        aie::vector<bfloat16, 32> in_splits = in_vecs.template to_vector<bfloat16>();
        auto [low, high] = aie::interleave_zip(aie::filter_odd(in_splits, 1), aie::filter_even(in_splits, 1), 1);
        aie::vector<bfloat16, 32> in_splits_inv = aie::concat(low, high);
        aie::accum<accfloat, 32> tmp_splits;
        aie::accum<accfloat, 32> out_vecs_real;
        aie::accum<accfloat, 32> out_vecs_imag;
        aie::vector<float, 32> out_vecs;
        
        out_vecs_real = aie::mul(in_splits, tw_vecs[0]);
        out_vecs_imag = aie::mul(in_splits_inv, tw_vecs[0]);
        for (unsigned i = 1; i < kSplitCount; ++i) {
          out_vecs_real = aie::mac(out_vecs_real, in_splits, tw_vecs[i]);
          out_vecs_imag = aie::mac(out_vecs_imag, in_splits_inv, tw_vecs[i]);
        }
        for (unsigned k = 1; k < kSplitCount; ++k) {
          tmp_splits.from_vector(in_splits);
          in_vecs = aie::sub(in_vecs, tmp_splits);
          in_splits = in_vecs.template to_vector<bfloat16>();
          auto [low, high] = aie::interleave_zip(aie::filter_odd(in_splits, 1), aie::filter_even(in_splits, 1), 1);
          in_splits_inv = aie::concat(low, high);
          for (unsigned i = 0; i < kSplitCount; ++i) {
            out_vecs_real = aie::mac(out_vecs_real, in_splits, tw_vecs[i]);
            out_vecs_imag = aie::mac(out_vecs_imag, in_splits_inv, tw_vecs[i]);
          }
        }
        aie::vector<float, 32> out_vecs_real_flt = out_vecs_real.template to_vector<float>();
        aie::vector<float, 32> out_vecs_imag_flt = out_vecs_imag.template to_vector<float>();
        aie::vector<float, 16> real = aie::sub(aie::filter_even(out_vecs_real_flt, 1), aie::filter_odd(out_vecs_real_flt, 1));
        aie::vector<float, 16> imag = aie::add(aie::filter_even(out_vecs_imag_flt, 1), aie::filter_odd(out_vecs_imag_flt, 1));
        auto [low_tmp, high_tmp] = aie::interleave_zip(real, imag, 1);
        out_vecs = aie::concat(low_tmp, high_tmp);
        aie::store_v(&butterfly_in[0][0], out_vecs);
        }

        if constexpr (PROFILING) {
          elemwise_cycles += get_cycles() - elemwise_start;
        }



        // Butterfly computation using Matrix Multiplication Unit
        unsigned long long butterfly_start = 0;
        if constexpr (PROFILING) {
          butterfly_start = get_cycles();
        }
        {
        alignas(aie::vector_decl_align) static bfloat16 coeff_buf[64] = {
          1,  0,  1,  0,  1,  0,  1,  0,
          0,  1,  0,  1,  0,  1,  0,  1,
          1,  0,  0, -1, -1,  0,  0,  1,
          0,  1,  1,  0,  0, -1, -1,  0,
          1,  0, -1,  0,  1,  0, -1,  0,
          0,  1,  0, -1,  0,  1,  0, -1,
          1,  0,  0,  1, -1,  0,  0, -1,
          0,  1, -1,  0,  0, -1,  1,  0,
        };
        aie::vector<bfloat16, 64> coeff_vecs;
        coeff_vecs = aie::load_v<64>(coeff_buf);
        aie::accum<accfloat, 32> in_vecs;
        in_vecs = aie::load_v<32>(&butterfly_in[0][0]);
        aie::accum<accfloat, 32> tmp_splits;

        using MMUL = aie::mmul<4, 8, 8, bfloat16, bfloat16, accfloat>;
        MMUL OUT;
        aie::vector<bfloat16, 32> in_splits = in_vecs.template to_vector<bfloat16>();
        OUT.mul(in_splits, coeff_vecs);
        for (unsigned k = 1; k < kSplitCount; ++k) {
          tmp_splits.from_vector(in_splits);
          in_vecs = aie::sub(in_vecs, tmp_splits);
          in_splits = in_vecs.template to_vector<bfloat16>();
          OUT.mac(in_splits, coeff_vecs);
        }
        aie::store_v(&butterfly_out[0][0], OUT.template to_vector<float>());
        }

        if constexpr (PROFILING) {
          butterfly_cycles += get_cycles() - butterfly_start;
        }
        for (unsigned q = q0; q < q_lim; ++q) {
          const unsigned t = q - q0;
          const unsigned out_idx0 = q + s * (4 * p + 0);
          const unsigned out_idx1 = q + s * (4 * p + 1);
          const unsigned out_idx2 = q + s * (4 * p + 2);
          const unsigned out_idx3 = q + s * (4 * p + 3);

          dst[2 * out_idx0] = butterfly_out[t][0];
          dst[2 * out_idx0 + 1] = butterfly_out[t][1];
          dst[2 * out_idx1] = butterfly_out[t][2];
          dst[2 * out_idx1 + 1] = butterfly_out[t][3];
          dst[2 * out_idx2] = butterfly_out[t][4];
          dst[2 * out_idx2 + 1] = butterfly_out[t][5];
          dst[2 * out_idx3] = butterfly_out[t][6];
          dst[2 * out_idx3 + 1] = butterfly_out[t][7];
        }
      }
    }

    // Each stage uses 3 twiddle factors per q: W^(q*m), W^(2*q*m), W^(3*q*m)
    // Each complex twiddle is 8 bf16 values (4 real splits + 4 imag splits)
    stage_twiddle_base += kTwiddleBlockPerQ * s;
  }

  // If number of stages is even, final data sits in x; copy to y.
  if ((LOG4N & 1u) == 0) {
    for (unsigned i = 0; i < N * 2; ++i) {
      y[i] = x[i];
    }
  }

  if constexpr (PROFILING) {
    g_fft_elemwise_cycles = elemwise_cycles;
    g_fft_butterfly_cycles = butterfly_cycles;
  }
}

// Wrapper functions
extern "C" {

void fft_stockham_f32(float *input, const bfloat16 *twiddle, 
                      float *output) {
  unsigned long long start = 0;
  unsigned long long end = 0;
  if constexpr (PROFILING) {
    event0();
    start = get_cycles();
  }

  // Perform FFT using Stockham algorithm with GEMM-based complex multiplication
  for (int r = 0; r < 10000; ++r) {
    fft_stockham_gemm<FFT_SIZE>(input, twiddle, output);
  }
  if constexpr (PROFILING) {
    end = get_cycles();
    event1();
    g_fft_stockham_cycles = end - start;
    *((unsigned long long *)output + 0) = g_fft_stockham_cycles;
    *((unsigned long long *)output + 1) = g_fft_elemwise_cycles;
    *((unsigned long long *)output + 2) = g_fft_butterfly_cycles;
  }

}

void zero_f32(float *c) {
  zero_vectorized<float, FFT_SIZE * 2>(c);
}

} // extern "C"
