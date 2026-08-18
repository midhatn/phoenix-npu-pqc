// SPDX-License-Identifier: Apache-2.0
// Retired DR2d monolithic derive translation unit.
//
// It intentionally exports no kernel.  The production graph exclusively uses
// the six independently compiled sources named in
// dr2d_mlkem512_kpke_keygen_graph.py.  Retaining this marker prevents a stale
// source-path reference from silently restoring the program-memory-overflow
// implementation that DR2d replaced.
