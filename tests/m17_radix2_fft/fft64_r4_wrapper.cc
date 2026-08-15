//===- fft64_r4_wrapper.cc --------------------------------*- C++ -*-===//
//
// This file is licensed under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
// Copyright (C) 2026, midhatn.
//
//===----------------------------------------------------------------------===//
//
// Thin wrapper that instantiates the radix-4 Stockham FFT kernel at N=64.
//
// The underlying kernel (kernels/fft_stockham_f32.cc, adapted from
// diacccc/FFT_R4_AIE) is parameterized on the FFT_SIZE preprocessor macro,
// defaulting to 256. iron.jit's ExternalFunction (as of mlir-aie 1.4.1) does
// not expose a first-class way to inject preprocessor defines into a kernel
// source file. This wrapper defines FFT_SIZE before textually including the
// kernel, giving us per-variant N configurability without forking the kernel.
//
//===----------------------------------------------------------------------===//

#define FFT_SIZE 64
#include "../../kernels/fft_stockham_f32.cc"