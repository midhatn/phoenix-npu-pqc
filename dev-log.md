# Phoenix SDR-DSP Development Log

Local-development milestones and workflow-verification events.

- 2026-08-14 23:48 +03:00 — Local dev workflow verified on ASUS TUF A15 (Ryzen 9 7940HS, Win11 26200).
- 2026-08-15 03:20 +03:00 — Release v0.4.0 shipped: M17 64-point NPU radix-4 Stockham FFT and IFFT via conjugation, forward SNR 138.79 dB, round-trip SNR 135.11 dB.
- 2026-08-15 04:10 +03:00 — Full silicon sweep 15/16 PASS on Phoenix NPU1 in 96.32 s wall time; M15b remains failing pending iron.Runtime port. Committed as `1ec80c8`.
- 2026-08-15 04:30 +03:00 — Migrated 12 iron-based tests to the mlir-aie v1.4.1 iron.Runtime API (pinned at commit `3ca0193`; `Runtime(seq_fn, fn_args=[...])`, `Program(workers=[...])`, in-sequence `TaskGroup()`).
- 2026-08-15 04:45 +03:00 — Documentation refresh (`README.md`, `docs/MILESTONES_AND_MATHEMATICS.md`, `docs/ROADMAP.md`, `toolchain.yaml`, `docs/SETUP_WINDOWS.md`, `docs/M2_TOOLCHAIN_PIN.md`) to reflect v0.4.0 and the new 15/16 pass total.
