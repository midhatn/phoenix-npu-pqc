// M27 - OFDM Loopback (TX + On-Tile Channel + RX) Kernel
//
// Single-tile AIE2 kernel that runs an 802.11a-style OFDM burst end-to-end on
// one core:
//   1. Pilot / data multiplex into a 64-point complex frequency vector X[k]
//      per OFDM symbol, N_SYM = 8 symbols per burst.
//   2. IFFT via the conjugate trick:  x = conj(FFT(conj(X))) / N.
//      The FFT is the M17 radix-4 Stockham kernel, textually included with
//      FFT_SIZE = 64 (the same wrapper pattern as tests/m17_radix2_fft/
//      fft64_r4_wrapper.cc).
//   3. Cyclic-prefix add (last 16 samples prepended to each 64-sample block).
//   4. 4-tap complex FIR channel with taps supplied at runtime via a DMA
//      buffer -- 4 <= N_CP + 1 = 17, so linear -> circular conversion holds.
//   5. Cyclic-prefix strip (drop first 16 samples of each 80-sample block).
//   6. Forward FFT per OFDM symbol -> Y[k].
//   7. Pilot LS estimate  H_hat_p[k_p] = Y[k_p] * X_p[k_p]  (BPSK pilots).
//   8. Linear interpolation of H_hat across the 48 data subcarriers, with
//      edge extrapolation using the nearest interior pilot pair.
//   9. Per-subcarrier zero-forcing equalization
//         X_hat[k] = Y[k] * conj(H_hat[k]) / (H_hat[k].re^2 + H_hat[k].im^2)
//      Complex divide is written this way because Peano NOCPP does not
//      vector-lower a complex divide primitive.
//  10. Emit 48 equalized complex bf16 slots per OFDM symbol.
//
// I/O contract (bf16 buffers, little-endian):
// DMA topology: AIE2 compute tiles have 2 input + 2 output DMA channels.
// The natural 4-buffer layout (in_data / in_channel / in_twiddle / out_data)
// needs 3 inputs and fails placement. We fuse the tiny in_channel buffer
// (8 bf16 = 4 complex taps) onto the tail of the twiddle buffer so we go
// back to 2 in-fifos + 1 out-fifo. See docs/M27_DESIGN.md sec 4.4.
//
//   in_data     : 2 * N_DATA_TOTAL bf16     (768 slots) -- 48 data * 8 sym
//                 Layout: [I0 Q0 I1 Q1 ...] with subcarrier order matching
//                 IEEE 802.11-2020 Table 17-8 (see test_ofdm_m27.py).
//   in_twiddle  : 8 * N_FFT + 2 * N_TAPS bf16 (520 slots) -- fused buffer.
//                 Slots [0..512): M17 radix-4 Stockham twiddle table,
//                 Ozaki-split, from
//                 tests/m17_radix2_fft/twiddles_r4_stockham.py.
//                 Slots [512..520): 4 complex FIR channel taps
//                 [h0.re h0.im h1.re h1.im h2.re h2.im h3.re h3.im].
//   out_data    : 2 * N_DATA_TOTAL bf16     (768 slots) -- 384 equalized
//                 complex data subcarriers.
//
// State discipline (M22/M24/M25/M26 rule): no persistent state across the
// outer OFDM-symbol loop. The FFT scratch buffer is a stack float32[128];
// twiddles are read-only bf16 from DMA. Every OFDM symbol is independent.
//
// Peano NOCPP rules inherited from M25/M26:
//   - No libc <math.h>. All scalar math is open-coded here.
//   - -O2 folds union-based sign-of into llvm.copysign which AIE2 rejects;
//     we do not use sign-of in this kernel (equalization is unsigned),
//     which avoids the copysign incident entirely.
//   - The @iron.jit decorator is REQUIRED on the driver function or
//     Program.resolve_program() returns raw MLIR and no compile happens
//     (M24 incident).
//   - I/O is bfloat16, internal math is float32.
//
// Citations:
//   - Chang, Bell Syst. Tech. J. 45(10), 1966. Original OFDM concept.
//   - Weinstein & Ebert, IEEE TCOM 19(5), 1971. DFT-based OFDM.
//     https://doi.org/10.1109/TCOM.1971.1090705
//   - Peled & Ruiz, IEEE ICASSP 1980. Cyclic prefix.
//     https://doi.org/10.1109/ICASSP.1980.1171076
//   - van de Beek et al, IEEE TSP 45(7), 1997.
//     https://doi.org/10.1109/78.611176
//   - Coleri et al, IEEE Trans. Broadcasting 48(3), 2002. Comb-type pilots.
//     https://ieeexplore.ieee.org/document/1035788
//   - IEEE Std 802.11-2020, section 17.3.5 (subcarrier map) and 17.3.9.7.3
//     (EVM). https://standards.ieee.org/ieee/802.11/7028/
//   - Proakis & Salehi 5e, section 13.5.
//     https://www.mheducation.com/highered/product/digital-communications-proakis-salehi/M9780072957167.html
//   - Rice 2e, Ch. 8.
//     https://www.pearson.com/en-us/subject-catalog/p/digital-communications-a-discrete-time-approach/P200000003544

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

// Pull in the M17 radix-4 Stockham FFT at N = 64, providing an inline
// extern "C" fft_stockham_f32(float*, const bfloat16*, float*).
// This is the same textual-include pattern documented in
// tests/m17_radix2_fft/fft64_r4_wrapper.cc.
#define FFT_SIZE 64
#include "../../kernels/fft_stockham_f32.cc"

// -------- Compile-time constants (must match test_ofdm_m27.py exactly) --------

constexpr int N_FFT         = 64;   // OFDM subcarrier count
constexpr int N_CP          = 16;   // cyclic prefix length
constexpr int N_OSYM        = N_FFT + N_CP;   // 80 samples per OFDM symbol
constexpr int N_SYM         = 8;    // OFDM symbols per burst
constexpr int N_DATA        = 48;   // data subcarriers per OFDM symbol
constexpr int N_PILOT       = 4;    // pilot subcarriers per OFDM symbol
constexpr int N_TAPS        = 4;    // channel FIR taps
constexpr int N_DATA_TOTAL  = N_DATA * N_SYM;  // 384
constexpr int TWIDDLE_ELEMS = N_FFT * 8;       // 512 bf16, M17-packed

// IEEE 802.11a data-subcarrier indices in natural FFT order [0..63].
// See test_ofdm_m27.py::_data_bins_natural(). Literal-encoded here.
// 48 data subcarriers = k in {+/-1..+/-6, +/-8..+/-20 (skip +/-7 pilots),
// +/-22..+/-26 (skip +/-21 pilots)} = 24 positive + 24 negative.
static const int DATA_BINS[N_DATA] = {
     1,  2,  3,  4,  5,  6,           // k = +1..+6
     8,  9, 10, 11, 12, 13, 14,       // k = +8..+14 (skip +7)
    15, 16, 17, 18, 19, 20,           // k = +15..+20
    22, 23, 24, 25, 26,               // k = +22..+26 (skip +21)
    38, 39, 40, 41, 42,               // k = -26..-22 (natural bins)
    44, 45, 46, 47, 48, 49, 50,       // k = -20..-14
    51, 52, 53, 54, 55, 56,           // k = -13..-8
    58, 59, 60, 61, 62, 63            // k = -6..-1
};

// Pilot subcarriers in natural FFT order.  k = {+7, +21, -21, -7}.
static const int PILOT_BINS[N_PILOT] = { 7, 21, 43, 57 };

// Pilot polarities: IEEE 802.11-2020 section 17.3.5.10 symbol-0 pattern
// P = (+1, +1, +1, -1) at k = (-21, -7, +7, +21). Reordered to match
// PILOT_BINS = { +7=+1, +21=-1, -21=+1, -7=+1 }.
static const float PILOT_POL[N_PILOT] = { +1.0f, -1.0f, +1.0f, +1.0f };

// Pilot subcarrier indices in centered form (k_centered in [-32, +31]),
// used only for linear interpolation slope computation.
static const int PILOT_KC[N_PILOT] = { +7, +21, -21, -7 };

// Data subcarrier indices in centered form.  Mirror of DATA_BINS.
static const int DATA_KC[N_DATA] = {
     1,  2,  3,  4,  5,  6,
     8,  9, 10, 11, 12, 13, 14,
    15, 16, 17, 18, 19, 20,
    22, 23, 24, 25, 26,
   -26,-25,-24,-23,-22,
   -20,-19,-18,-17,-16,-15,-14,
   -13,-12,-11,-10, -9, -8,
    -6, -5, -4, -3, -2, -1
};

// Inverse-FFT-size scale for the conjugate-trick IDFT.
constexpr float INV_N_FFT = 1.0f / (float)N_FFT;

// -------- Helpers --------

// Return the pair of pilots (in PILOT_KC index space, 0..3) that brackets the
// data subcarrier at centered index kc.  For kc outside the outermost pilots
// (-32..-21 or +21..+31), use the nearest interior pilot pair for
// extrapolation.
static inline void pilot_bracket(int kc, int *pa, int *pb) {
    // PILOT_KC sorted ascending: {-21, -7, +7, +21} -> indices {2, 3, 0, 1}
    // We inline the sort as literal switches to keep this branch-lean.
    if (kc <= -21) {
        // extrapolate below -21 using pilots at -21 and -7
        *pa = 2;  // -21
        *pb = 3;  //  -7
    } else if (kc <= -7) {
        *pa = 2;  // -21
        *pb = 3;  //  -7
    } else if (kc <= 7) {
        *pa = 3;  //  -7
        *pb = 0;  //  +7
    } else if (kc <= 21) {
        *pa = 0;  //  +7
        *pb = 1;  // +21
    } else {
        // extrapolate above +21 using pilots at +7 and +21
        *pa = 0;  //  +7
        *pb = 1;  // +21
    }
}

// Complex FIR: length-4 convolution of s[] with taps h[].
// Emits y[n] = sum_{i=0..3} h[i] * s[n-i]. Zero-initial-state.
// s_len is the number of input samples;  y[] has the same length.
// Because N_TAPS = 4 << N_CP = 16, the linear FIR does not exceed the
// CP guard interval and linear-to-circular OFDM conversion still holds.
__attribute__((noinline))
static void channel_fir_c(const float *__restrict s_re,
                          const float *__restrict s_im,
                          int s_len,
                          const float h_re[N_TAPS],
                          const float h_im[N_TAPS],
                          float *__restrict y_re,
                          float *__restrict y_im) {
    #pragma clang loop unroll(disable)
    for (int n = 0; n < s_len; ++n) {
        float acc_re = 0.0f;
        float acc_im = 0.0f;
        // Literal-index unrolled 4-tap MAC (M22 discipline: no runtime index
        // into the tap array; Peano lowers this to 4 register-copy MACs).
        int idx0 = n - 0;
        int idx1 = n - 1;
        int idx2 = n - 2;
        int idx3 = n - 3;
        float x0_re = (idx0 >= 0) ? s_re[idx0] : 0.0f;
        float x0_im = (idx0 >= 0) ? s_im[idx0] : 0.0f;
        float x1_re = (idx1 >= 0) ? s_re[idx1] : 0.0f;
        float x1_im = (idx1 >= 0) ? s_im[idx1] : 0.0f;
        float x2_re = (idx2 >= 0) ? s_re[idx2] : 0.0f;
        float x2_im = (idx2 >= 0) ? s_im[idx2] : 0.0f;
        float x3_re = (idx3 >= 0) ? s_re[idx3] : 0.0f;
        float x3_im = (idx3 >= 0) ? s_im[idx3] : 0.0f;

        // Complex MAC: (a+jb)*(c+jd) = (ac-bd) + j(ad+bc)
        acc_re += h_re[0] * x0_re - h_im[0] * x0_im;
        acc_im += h_re[0] * x0_im + h_im[0] * x0_re;
        acc_re += h_re[1] * x1_re - h_im[1] * x1_im;
        acc_im += h_re[1] * x1_im + h_im[1] * x1_re;
        acc_re += h_re[2] * x2_re - h_im[2] * x2_im;
        acc_im += h_re[2] * x2_im + h_im[2] * x2_re;
        acc_re += h_re[3] * x3_re - h_im[3] * x3_im;
        acc_im += h_re[3] * x3_im + h_im[3] * x3_re;

        y_re[n] = acc_re;
        y_im[n] = acc_im;
    }
}

// -------- Fused OFDM loopback body --------

// Channel taps live at the tail of the twiddle buffer.
#define CHAN_OFFSET  (8 * FFT_SIZE)   // 512

static void ofdm_loopback_body(bfloat16 *__restrict in_data,
                               bfloat16 *__restrict in_twiddle,
                               bfloat16 *__restrict out_data) {
    // Channel taps aliased inside the twiddle buffer.
    bfloat16 *__restrict in_channel = in_twiddle + CHAN_OFFSET;
    event0();

    // Load channel taps once (they are constant across the 8-symbol burst).
    float h_re[N_TAPS], h_im[N_TAPS];
    h_re[0] = (float)in_channel[0]; h_im[0] = (float)in_channel[1];
    h_re[1] = (float)in_channel[2]; h_im[1] = (float)in_channel[3];
    h_re[2] = (float)in_channel[4]; h_im[2] = (float)in_channel[5];
    h_re[3] = (float)in_channel[6]; h_im[3] = (float)in_channel[7];

    // Per-symbol scratch buffers.  Kept on stack per symbol; sum of sizes is
    // well under the 16 KB stack budget we set in the driver.
    float X_buf[2 * N_FFT];       // 128 f32  -- IFFT input (conjugated X[k])
    float x_buf[2 * N_FFT];       // 128 f32  -- IFFT output (time-domain)
    float s_re[N_OSYM];           //  80 f32  -- TX time with CP prepend
    float s_im[N_OSYM];
    float y_re[N_OSYM];           //  80 f32  -- Post-channel time
    float y_im[N_OSYM];
    float Y_in[2 * N_FFT];        // 128 f32  -- Forward-FFT input (post-CP)
    float Y_buf[2 * N_FFT];       // 128 f32  -- Forward-FFT output
    float Hp_re[N_PILOT];         //   4 f32
    float Hp_im[N_PILOT];

    // Outer OFDM-symbol loop. Explicitly disable unrolling: unrolling by 8
    // duplicates the entire per-symbol pipeline (IFFT, CP, FIR, FFT, LS,
    // interp, ZF) and blows the 16 KiB AIE2 program-memory budget.
    #pragma clang loop unroll(disable)
    for (int sym = 0; sym < N_SYM; ++sym) {

        // ---------------- (1) Pilot / data multiplex ----------------
        // Zero-initialize X_buf so guard tones and DC stay zero without
        // an explicit index list.
        for (int i = 0; i < 2 * N_FFT; ++i) X_buf[i] = 0.0f;

        // Insert 48 data subcarriers.
        #pragma clang loop unroll(disable)
        for (int d = 0; d < N_DATA; ++d) {
            int k = DATA_BINS[d];
            int base_in = 2 * (sym * N_DATA + d);
            float dI = (float)in_data[base_in];
            float dQ = (float)in_data[base_in + 1];
            X_buf[2 * k    ] = dI;
            X_buf[2 * k + 1] = dQ;
        }
        // Insert 4 BPSK pilots.
        for (int p = 0; p < N_PILOT; ++p) {
            int k = PILOT_BINS[p];
            X_buf[2 * k    ] = PILOT_POL[p];
            X_buf[2 * k + 1] = 0.0f;
        }

        // ---------------- (2) IFFT via conjugate trick ----------------
        // Conjugate X[k] in place.
        for (int i = 0; i < N_FFT; ++i) {
            X_buf[2 * i + 1] = -X_buf[2 * i + 1];
        }
        // Forward FFT of conj(X). Uses M17 radix-4 Stockham with FFT_SIZE=64.
        fft_stockham_f32(X_buf, in_twiddle, x_buf);
        // Conjugate again and divide by N to complete the IDFT.
        for (int i = 0; i < N_FFT; ++i) {
            x_buf[2 * i    ] =  x_buf[2 * i    ] * INV_N_FFT;
            x_buf[2 * i + 1] = -x_buf[2 * i + 1] * INV_N_FFT;
        }

        // ---------------- (3) CP-add ----------------
        // s = [x[N-CP..N-1], x[0..N-1]]
        for (int i = 0; i < N_CP; ++i) {
            s_re[i] = x_buf[2 * (N_FFT - N_CP + i)    ];
            s_im[i] = x_buf[2 * (N_FFT - N_CP + i) + 1];
        }
        for (int i = 0; i < N_FFT; ++i) {
            s_re[N_CP + i] = x_buf[2 * i    ];
            s_im[N_CP + i] = x_buf[2 * i + 1];
        }

        // ---------------- (4) Channel FIR ----------------
        channel_fir_c(s_re, s_im, N_OSYM, h_re, h_im, y_re, y_im);

        // ---------------- (5) CP-strip ----------------
        for (int i = 0; i < N_FFT; ++i) {
            Y_in[2 * i    ] = y_re[N_CP + i];
            Y_in[2 * i + 1] = y_im[N_CP + i];
        }

        // ---------------- (6) Forward FFT ----------------
        fft_stockham_f32(Y_in, in_twiddle, Y_buf);

        // ---------------- (7) Pilot LS ----------------
        // Pilots are BPSK so LS reduces to a sign-multiply of Y[k_p].
        for (int p = 0; p < N_PILOT; ++p) {
            int k = PILOT_BINS[p];
            float pol = PILOT_POL[p];
            Hp_re[p] = Y_buf[2 * k    ] * pol;
            Hp_im[p] = Y_buf[2 * k + 1] * pol;
        }

        // ---------------- (8) + (9) Linear-interp channel est + ZF eq ----
        #pragma clang loop unroll(disable)
        for (int d = 0; d < N_DATA; ++d) {
            int k  = DATA_BINS[d];
            int kc = DATA_KC[d];

            int pa, pb;
            pilot_bracket(kc, &pa, &pb);

            // Linear interpolation in centered subcarrier index kc.
            //   H_hat[k] = H_p[pa] + (kc - kc_pa) * (H_p[pb] - H_p[pa]) /
            //              (kc_pb - kc_pa)
            float kc_pa = (float)PILOT_KC[pa];
            float kc_pb = (float)PILOT_KC[pb];
            float span  = kc_pb - kc_pa;  // != 0 by construction
            float t     = ((float)kc - kc_pa) / span;

            float Hd_re = Hp_re[pa] + t * (Hp_re[pb] - Hp_re[pa]);
            float Hd_im = Hp_im[pa] + t * (Hp_im[pb] - Hp_im[pa]);

            // Zero-forcing:  X_hat = Y * conj(H_hat) / |H_hat|^2
            float y_re_k = Y_buf[2 * k    ];
            float y_im_k = Y_buf[2 * k + 1];
            float mag2   = Hd_re * Hd_re + Hd_im * Hd_im;

            // Guard against divide-by-zero.  With interpolated pilot LS on a
            // physical channel this branch should never trip; on the pilot-
            // only sanity test where data slots are zero it also never
            // trips because H_hat is derived from pilots, not data.
            float inv;
            if (mag2 > 1.0e-12f) {
                inv = 1.0f / mag2;
            } else {
                inv = 0.0f;
            }

            float x_re = ( y_re_k * Hd_re + y_im_k * Hd_im) * inv;
            float x_im = (-y_re_k * Hd_im + y_im_k * Hd_re) * inv;

            int base_out = 2 * (sym * N_DATA + d);
            out_data[base_out    ] = (bfloat16)x_re;
            out_data[base_out + 1] = (bfloat16)x_im;
        }
    }
}

extern "C" {

void ofdm_loopback(bfloat16 *__restrict in_data,
                   bfloat16 *__restrict in_twiddle,
                   bfloat16 *__restrict out_data) {
    ofdm_loopback_body(in_data, in_twiddle, out_data);
}

}  // extern "C"
