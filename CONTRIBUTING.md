# Contributing to Phoenix SDR-DSP

Contributions from the Software Defined Radio, AI Engine, and finite-field cryptography communities are welcome.

---

## 1. Development Workflow

1. **Fork the Repository:** Create your own branch (`git checkout -b feature/MyAwesomeDSPKernel`).
2. **Setup Toolchain:** Ensure you have the AMD IRON environment and LLVM Peano compiler configured under Windows 11 / WSL2.
3. **Verify Bit-Exactness:** Every deterministic DSP and NTT kernel MUST include an independent CPU reference test that verifies $0$ numerical error or documented fixed-point error bounds.
4. **Run Master Regression:** Run `python run_all_silicon_tests.py` and ensure 100% of tests pass on silicon before opening a PR.
5. **Open a Pull Request:** Describe your kernel implementation, tile allocation, and hardware benchmark metrics.

---

## 2. Coding Standards

- **Header Files:** Place all reusable C++ headers under `include/sdr_dsp/`.
- **Naming Conventions:** Kernels should follow snake_case naming; constants should use uppercase prefixes (`MOD_Q`, `BARRETT_FACTOR`).
- **Memory Safety:** Tile local memory per AIE2 core is strictly capped at 64 KB (divided into four 16 KB banks). Avoid allocating buffers $> 16\text{ KB}$ per ObjectFIFO to prevent bank overflow.
