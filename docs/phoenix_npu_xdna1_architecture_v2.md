# Silicon Architecture: AMD XDNA 1 (AIE2) on Phoenix (v2)

The acceleration backend of `phoenix-npu-pqc` targets the integrated Neural Processing Unit (NPU) of the **AMD Ryzen 9 7940HS / Ryzen 7 7840HS** ("Phoenix" silicon). Rather than executing post-quantum algorithms on standard CPU SIMD loops or high-latency SIMT GPU blocks, cryptographic primitives (FIPS 202 Keccak/SHAKE, FIPS 203 ML-KEM, FIPS 204 ML-DSA, and ETSI GS QKD 014 Ingress) are mapped directly onto AMD’s **XDNA 1** architecture. 

XDNA 1 is a **Coarse-Grained Reconfigurable Architecture (CGRA)** derived from Xilinx Versal AIE-ML (AIE2) technology—combining the clock frequency and compute density of an ASIC/GPU with the spatial streaming and distributed scratchpad memory model of an FPGA.

```
              System Fabric / Host PCIe / DDR5-5600 Interface
══════════════════════════════════════════════════════════════════════════════════
Row 0:     [ Shim DMA 0 ][ Shim DMA 1 ][ Shim DMA 2 ][ Shim DMA 3 ][ Shim DMA 4 ]
──────────────────────────────────────────────────────────────────────────────────
Row 1:     [ MemTile 0  ][ MemTile 1  ][ MemTile 2  ][ MemTile 3  ][ MemTile 4  ]
└──────── 5 Columns × 512 KiB Shared L2 SRAM = 2.5 MiB Total ────────┘
──────────────────────────────────────────────────────────────────────────────────
Row 2:     [ Tile (0,0) ][ Tile (0,1) ][ Tile (0,2) ][ Tile (0,3) ][ Tile (0,4) ]
Row 3:     [ Tile (1,0) ][ Tile (1,1) ][ Tile (1,2) ][ Tile (1,3) ][ Tile (1,4) ]
Row 4:     [ Tile (2,0) ][ Tile (2,1) ][ Tile (2,2) ][ Tile (2,3) ][ Tile (2,4) ]
Row 5:     [ Tile (3,0) ][ Tile (3,1) ][ Tile (3,2) ][ Tile (3,3) ][ Tile (3,4) ]
└────── 20 Compute Tiles (16 KiB Prog + 64 KiB Data SRAM each) ──────┘
══════════════════════════════════════════════════════════════════════════════════
```

---

### 1. Physical Topology & Compute Microarchitecture

The Phoenix NPU operates as a memory-mapped spatial co-processor controlled via AMD XRT (Xilinx Runtime), the native Windows/Linux NPU driver, and MLIR-AIE (IRON) compilers:

* **Physical Grid:** 5 columns × 4 rows of active compute tiles (**20 independent VLIW tiles**), backed by 5 memory tiles (Row 1) and 5 interface shim DMA blocks (Row 0).
* **7-Way VLIW Core:** Each compute tile features a 7-way Very Long Instruction Word architecture capable of issuing:
  * 1 Vector arithmetic operation (MAC / ALU)
  * 1 Scalar RISC pointer/loop operation
  * 2 Vector memory loads (256-bit each = 512 bits/cycle)
  * 1 Vector memory store (256-bit = 32 bytes/cycle)
  * Hardware lock acquisitions and stream transfer handshakes simultaneously in a single clock cycle.
* **Vector Processing Unit (VPU):** A native 512-bit wide SIMD vector datapath supporting packed integer and floating-point types:
  * **Native 16-bit MAC:** $64 \times (16\text{b} \times 16\text{b} \rightarrow 32\text{b})$ multiply-accumulates per cycle per tile.
  * **Emulated 32-bit MAC:** $16 \times (32\text{b} \times 32\text{b} \rightarrow 64\text{b})$ multiply-accumulates per cycle per tile.
* **Accumulator & Cascade Width:** 512-bit wide accumulator registers linked to vertically adjacent tiles via dedicated point-to-point **cascade streaming buses**.
* **Operating Frequency & Power Envelope:** Clocks between **1.0 GHz and 1.25 GHz** ($T_{clk} = 0.8\text{ ns}$), delivering **10 TOPS (INT8)** of compute at an average draw of only **3–6 Watts**.

#### The Hardware Carry-Flag Reality & Multi-Precision Arithmetic
As analyzed in hardware cryptography benchmarks (e.g., *Ingonyama*), AI Engine vector processors do not feature a hardware carry flag. For arbitrary big-integer arithmetic and lattice modular reductions:
* Software cannot rely on hardware carry chains (`ADC`).
* To prevent overflow during multi-operand accumulation without carry flags, operands are structured into bounded limbs (e.g., 30-bit limbs inside 64-bit accumulators, allowing up to 16 accumulations before reduction, or centered 16/32-bit coefficients for Montgomery/Barrett reduction).
* This eliminates carry-propagation stalls and sustains full vector saturation across Kyber ($q=3329$) and Dilithium ($q=8380417$) rings.

---

### 2. The Non-Von Neumann Memory Fabric

Traditional Von Neumann architectures (CPUs and GPUs) route all data through rigid, centralized cache hierarchies (L1/L2/L3 caches and VRAM). XDNA 1 replaces hardware cache controllers with an **explicit, distributed, software-scheduled memory fabric**:

| Memory Component | Allocation & Geometry | Peak Bandwidth (@ 1.25 GHz) | Architectural Role |
| :--- | :--- | :--- | :--- |
| **Tile Program Memory** | **16 KiB** per tile (single-port SRAM) | 1 VLIW bundle / cycle | Dedicated instruction storage; read-only during execution. |
| **Local Data SRAM** | **64 KiB** per tile (8 banks × 128-bit) | **120 GB/s per tile** ($2 \times 32\text{B}$ load + $1 \times 32\text{B}$ store) | Ultra-low latency ping-pong scratchpads for active polynomials. |
| **Neighbor-Shared SRAM** | **Up to 320 KiB** per tile (N, S, E, W) | Single-cycle access | Direct crossbar access to adjacent tile SRAMs without routing network traffic. |
| **Array-Wide Local SRAM** | **1.28 MiB aggregate** across 20 compute tiles | **2.40 TB/s sustained scratchpad bandwidth** | Multi-banked working memory delivering ~27× host DDR5 bandwidth. |
| **Shared Memory Tiles (Row 1)** | **2.5 MiB total** (5 columns × 512 KiB) | Multi-channel Tile DMA lines | **Software-managed L2:** Zero automatic caching logic; all staging is explicit via DMAs. |
| **Host DDR5-5600** | System memory (off-die) | ~89.6 GB/s theoretical peak | Initial message ingestion and final ciphertext/signature exchange. |

Because each compute tile accesses its own 64 KiB data SRAM plus the SRAM of its four cardinal neighbors with **single-cycle latency**, adjacent tiles can pass intermediate polynomial coefficients horizontally across memory boundaries without incurring stream-switch arbitration or DRAM roundtrips.

---

### 3. Spatial Dataflow: A Hybrid Between FPGA and GPU

XDNA 1 is often described as a cross between an FPGA and a GPU:

* **High Clock Frequency of an ASIC/GPU:** Unlike traditional FPGAs whose fine-grained bit-level logic fabrics struggle to exceed 250–400 MHz, XDNA’s hardened VLIW tiles operate at **1.25 GHz**.
* **Spatial Dataflow of an FPGA:** Rather than using time-sliced thread execution managed by dynamic warp schedulers, XDNA allows data to flow spatially through dedicated point-to-point routes, cascade buses, and AXI-Stream switches.
* **Elimination of the Cache Bottleneck:** Traditional GPUs allocate massive die area to hardware cache tag arrays, snooping logic, and miss-handling state machines. XDNA eliminates all automatic caching logic: the programmer and compiler explicitly schedule every byte movement via DMA ObjectFIFOs.

```
Tile (0,0) [NTT Stage 1-2]
│ (512-bit Cascade Bus: 0-cycle intermediate accumulation)
▼
Tile (1,0) [NTT Stage 3-4]
│ (Local SRAM Bank Handshake: 1-cycle latency)
▼
Tile (2,0) [Modular Barrett Reduction]
│ (AXI-Stream Switch: Deterministic FIFO token)
▼
Tile (3,0) [Serialization / Output Stage]
```

#### Beating Amdahl's Law via Full On-Chip Residency
In cryptographic acceleration, offloading individual subroutines (e.g., dispatching only NTT to an accelerator while keeping Keccak on the host CPU) quickly falls victim to **Amdahl’s Law**: PCIe transfer overhead and driver launch latency dominate total execution time. 

XDNA 1 solves this by hosting the entire cryptographic lifecycle on-chip (**Device Residency**):

$$
\text{Host Seed} \xrightarrow{\text{DMA}} \text{Tile (SHAKE256)} \xrightarrow{\text{Stream}} \text{Tile (Sampler)} \xrightarrow{\text{SRAM}} \text{Tile (NTT)} \xrightarrow{\text{Cascade}} \text{Tile (BaseMul)} \xrightarrow{\text{INTT}} \text{Output}
$$

Intermediate secret keys and polynomials never leave the on-die SRAM until the final operation is complete.

---

### 4. Architectural Comparison: XDNA 1 vs. Cerebras WSE vs. GPU vs. TPU

```
[Temporal SIMT / GPU]               [Systolic Arrays]             [Spatial Dataflow / CGRA]
NVIDIA Tensor Cores                   Google TPU                   AMD XDNA 1       Cerebras WSE
(Dynamic Warps / Caches)            (Rigid 2D Grid)              (20 VLIW Tiles)   (900k Core Wafer)
───────────────────────────────────────────────────────────────────────────────────────────────────────►
◄── Architectural Siblings ──►
```

| Architecture | Architectural Family | Memory Hierarchy & Scheduling | Primary Strength | Weakness for Lattice PQC / ZK |
| :--- | :--- | :--- | :--- | :--- |
| **AMD XDNA 1 (Phoenix)** | **Client CGRA / Spatial Dataflow** | Explicit 2D SRAM mesh (64 KiB/tile) + 2.5 MiB MemTiles; statically compiled VLIW. | High integer multiply density, zero cache jitter, deterministic latency at **3–6W**. | 20 tiles (compact client grid). |
| **Cerebras WSE-2/3** | **Wafer-Scale Spatial Dataflow** | 100% on-wafer SRAM (44 GB, >20 PB/s); asynchronous packet-triggered dataflow. | **Macro-scale sibling:** Eliminates external DRAM; massive spatial mapping across 900k PEs. | Datacenter scale (23 kW power budget); inaccessible for local edge endpoints. |
| **Google TPU (v2–v5)** | **2D Systolic Array (ASIC)** | Fixed 2D MAC grid; synchronous wavefront stepping. | Peak silicon efficiency for dense square matrix GEMM. | Rigid: Inefficient on irregular NTT address strides, rejection sampling, and non-matrix bitwise math. |
| **NVIDIA Tensor Cores** | **SIMT Execution Pipelines** | Dynamic warp schedulers, hardware-managed L1/L2 caches, registers $\rightarrow$ VRAM. | Immense raw floating-point throughput for batched AI models. | Non-deterministic latency; dynamic cache sharing exposes timing side-channel vulnerabilities. |

---

### 5. Why Spatial AIE2 Acceleration Suits Lattice Cryptography

Lattice-based PQC (FIPS 203 ML-KEM and FIPS 204 ML-DSA) places specific arithmetic demands on hardware that traditional matrix multipliers cannot effectively service:

1. **Vectorized NTT Butterfly Networks (Cooley-Tukey / Gentleman-Sande):**
   * NTT requires processing pairs of coefficients with varying twiddle-factor strides modulo $q$.
   * With 512-bit SIMD registers, a single AIE2 tile processes **16 parallel 32-bit polynomial coefficients** or **32 parallel 16-bit coefficients** in one instruction.
   * Neighbor-shared memory banks allow multi-stage butterfly passes to stream horizontally across adjacent tiles without saturating internal AXI crossbars.
2. **Deterministic Arithmetic Pipeline Execution (Branchless Design):**
   * Cryptographic implementations on CPUs and GPUs face constant timing side-channel risks from branch predictors, speculative execution, and cache line evictions.
   * On XDNA 1, execution is statically scheduled by the VLIW compiler. Every instruction, load, and store occupies a deterministic clock cycle slot with zero runtime cache jitter, providing architectural immunity against timing attacks.
3. **Tight Stream Coupling of Keccak and Samplers:**
   * FIPS 203/204 algorithms spend significant execution time expanding public seeds via SHAKE128/SHAKE256 and sampling polynomials (`SampleNTT`, `SamplePolyCBD`).
   * AIE2 tiles communicate over streaming FIFOs, allowing a Keccak absorption tile to continuously stream pseudo-random bytes directly into an adjacent tile running rejection sampling without intermediate roundtrips to system memory.
4. **Desktop-Class Cryptographic Throughput at Mobile Power:**
   * While datacenter accelerator cards (like the AMD Alveo V70 with 304 AIE-ML tiles) demonstrate the power of XDNA in the 75W envelope, the Phoenix NPU delivers that same microarchitectural efficiency in a 15–45W laptop APU, sipping only **3–6W** during active cryptographic execution.
