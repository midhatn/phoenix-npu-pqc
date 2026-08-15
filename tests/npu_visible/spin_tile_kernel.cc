// Purpose: Keep one AIE2 tile busy so Windows Task Manager can show NPU load.
// Target architecture: AMD Phoenix / Hawk Point NPU1 / XDNA1 / AIE2.
// Workload: SPIN_REPS passes over a 1024-element bfloat16 tile (vector width 64).
// This is a visibility kernel, not a DSP primitive. Do not use it as a numerical test.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include <aie_api/aie.hpp>

#ifndef SPIN_REPS
#define SPIN_REPS 2048
#endif

#ifndef TILE_N
#define TILE_N 1024
#endif

extern "C" {
void spin_tile(bfloat16 *restrict x, bfloat16 *restrict z) {
  event0();
  ::aie::vector<bfloat16, 64> zero_v = ::aie::broadcast<bfloat16, 64>(0.f);
  ::aie::accum<accfloat, 64> acc = ::aie::mul(zero_v, zero_v);
#pragma clang loop min_iteration_count(4)
  for (int rep = 0; rep < SPIN_REPS; ++rep) {
    bfloat16 *xp = x;
    for (int i = 0; i < TILE_N; i += 64) {
      ::aie::vector<bfloat16, 64> v = ::aie::load_v<64>(xp);
      xp += 64;
      acc = ::aie::add(acc, ::aie::mul(v, v));
    }
  }
  ::aie::store_v(z, acc.to_vector<bfloat16>());
  event1();
}
}
