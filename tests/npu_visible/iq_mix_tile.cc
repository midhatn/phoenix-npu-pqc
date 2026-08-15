// Purpose: Per-tile complex I/Q mixer for the 4-column throughput test.
// Target architecture: AMD Phoenix / Hawk Point NPU1 / XDNA1 / AIE2.
// Input: 1024 bfloat16 = 512 interleaved I/Q pairs + matching LO.
// Output: mixed I/Q, same layout as tests/m6_mixer/mixer_kernel.cc.
// Tile SRAM holds one token (~2 KB x 3). Streaming many tokens is the host's job.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include <aie_api/aie.hpp>

#ifndef TILE_N
#define TILE_N 1024
#endif

extern "C" {
void iq_mix_tile(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict lo_carrier,
    bfloat16 *__restrict out_iq
) {
  event0();
#pragma clang loop unroll_count(8)
  for (int i = 0; i < TILE_N; i += 2) {
    float i_in = (float)in_iq[i];
    float q_in = (float)in_iq[i + 1];
    float c_lo = (float)lo_carrier[i];
    float s_lo = (float)lo_carrier[i + 1];
    out_iq[i] = (bfloat16)((i_in * c_lo) - (q_in * s_lo));
    out_iq[i + 1] = (bfloat16)((i_in * s_lo) + (q_in * c_lo));
  }
  event1();
}
}
