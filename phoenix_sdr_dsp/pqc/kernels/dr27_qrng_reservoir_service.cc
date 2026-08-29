// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR27: QRNG-OPENAPI Ingress & NPU-Resident Token-Bucket Key/Entropy Reservoir.
 * Target Hardware: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1 Architecture).
 *
 * Standards & Resource Citations:
 * 1. Palo Alto Networks QRNG-OPENAPI Specification (v1.0):
 *    - Standard REST/mTLS interface for hardware entropy appliance ingestion.
 *    - Ingress Opcode OP_INGRESS (0x0001), Drain Opcode OP_DRAIN (0x0002).
 * 2. NIST Special Publication 800-90B (Section 4.4.1 & 4.4.2):
 *    - Preflight Health Cutoffs: Repetition Count Test (RCT cutoff = 10), Adaptive Proportion Test (APT cutoff = 177).
 * 3. Operational Resilience & Hysteresis State Machine:
 *    - Anti-flapping dual-threshold trigger:
 *      * Low-water mark <= 1 slot (<= 6.25% ~= 5%) -> STATE_1_DEGRADED_A.
 *      * High-water mark >= 5 slots (>= 31.25% >= 30%) -> STATE_0_FULL_HYBRID.
 * 4. ETSI GS QKD 014 v1.1.1 (2019-02): Quantum Key Distribution REST-based Key Delivery API.
 * 5. DOI: 10.5281/zenodo.22164124.
 */
#include <stdint.h>
#include <stddef.h>

#define DR27_DESC_MAGIC 0x27527101
#define DR27_RES_MAGIC  0x37325251 // "QR27"

#define OP_INGRESS  0x0001
#define OP_DRAIN    0x0002
#define OP_STATUS   0x0003
#define OP_ZEROIZE  0x0004

#define STATUS_SUCCESS             0x0000
#define STATUS_INVALID_MAGIC       0x0001
#define STATUS_HEALTH_CHECK_FAILED 0x0002
#define STATUS_RESERVOIR_FULL      0x0003
#define STATUS_RESERVOIR_EMPTY     0x0004
#define STATUS_TAMPER_ZEROIZED     0x0005

#define RESERVOIR_CAPACITY 16
#define SLOT_SIZE          32
#define LOW_WATER_MARK     1  // <= 1 slot -> State 1 Degraded
#define HIGH_WATER_MARK    5  // >= 5 slots -> State 0 Full Hybrid

#define STATE_FULL_HYBRID 0
#define STATE_DEGRADED_A  1

// Static AIE2 Tile SRAM Storage
static uint8_t  g_entropy_reservoir[RESERVOIR_CAPACITY][SLOT_SIZE];
static uint16_t g_head_ptr = 0;
static uint16_t g_tail_ptr = 0;
static uint16_t g_fill_count = 0;
static uint16_t g_current_mode = STATE_DEGRADED_A; // Start in degraded until filled past high-water mark

static uint32_t compute_crc32(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
    }
    return ~crc;
}

extern "C" {

void dr27_qrng_reservoir_service(
    const uint8_t *req,
    const uint8_t *desc,
    uint8_t *res
) {
    // Clear response buffer
    for (int i = 0; i < 64; i++) res[i] = 0;

    uint32_t magic       = *(const uint32_t*)(desc + 0);
    uint32_t req_id      = *(const uint32_t*)(desc + 4);
    uint16_t op_code     = *(const uint16_t*)(desc + 8);
    uint16_t flags       = *(const uint16_t*)(desc + 10);
    uint16_t entropy_len = *(const uint16_t*)(desc + 12);
    uint16_t source_id   = *(const uint16_t*)(desc + 14);
    uint32_t rct_val     = *(const uint32_t*)(desc + 16);
    uint32_t apt_val     = *(const uint32_t*)(desc + 20);

    uint32_t status = STATUS_SUCCESS;
    uint8_t payload_out[SLOT_SIZE];
    for (int i = 0; i < SLOT_SIZE; i++) payload_out[i] = 0;

    if (magic != DR27_DESC_MAGIC) {
        status = STATUS_INVALID_MAGIC;
    } else {
        switch (op_code) {
            case OP_INGRESS: {
                // Preflight SP 800-90B validation
                if (rct_val >= 10 || apt_val >= 177) {
                    status = STATUS_HEALTH_CHECK_FAILED;
                    break;
                }
                if (entropy_len < SLOT_SIZE) {
                    status = STATUS_HEALTH_CHECK_FAILED;
                    break;
                }
                if (g_fill_count >= RESERVOIR_CAPACITY) {
                    status = STATUS_RESERVOIR_FULL;
                    break;
                }

                // Store entropy block into ring buffer slot
                for (int i = 0; i < SLOT_SIZE; i++) {
                    g_entropy_reservoir[g_head_ptr][i] = req[i];
                }
                g_head_ptr = (g_head_ptr + 1) % RESERVOIR_CAPACITY;
                g_fill_count++;

                // Hysteresis evaluation: High-water mark triggers State 0 Full Hybrid
                if (g_fill_count >= HIGH_WATER_MARK) {
                    g_current_mode = STATE_FULL_HYBRID;
                }
                break;
            }

            case OP_DRAIN: {
                if (g_fill_count == 0) {
                    status = STATUS_RESERVOIR_EMPTY;
                    break;
                }

                // Extract entropy block from tail
                for (int i = 0; i < SLOT_SIZE; i++) {
                    payload_out[i] = g_entropy_reservoir[g_tail_ptr][i];
                    // Zeroize drained slot in SRAM immediately
                    g_entropy_reservoir[g_tail_ptr][i] = 0;
                }
                g_tail_ptr = (g_tail_ptr + 1) % RESERVOIR_CAPACITY;
                g_fill_count--;

                // Hysteresis evaluation: Low-water mark drops to State 1 Degraded
                if (g_fill_count <= LOW_WATER_MARK) {
                    g_current_mode = STATE_DEGRADED_A;
                }
                break;
            }

            case OP_STATUS: {
                // Read-only status inquiry
                break;
            }

            case OP_ZEROIZE: {
                // Complete synchronous hardware wipe
                for (int s = 0; s < RESERVOIR_CAPACITY; s++) {
                    for (int i = 0; i < SLOT_SIZE; i++) {
                        g_entropy_reservoir[s][i] = 0;
                    }
                }
                g_head_ptr = 0;
                g_tail_ptr = 0;
                g_fill_count = 0;
                g_current_mode = STATE_DEGRADED_A;
                status = STATUS_TAMPER_ZEROIZED;
                break;
            }

            default:
                status = STATUS_INVALID_MAGIC;
                break;
        }
    }

    // Compute checksum over on-chip reservoir state
    uint32_t state_crc = compute_crc32((const uint8_t*)g_entropy_reservoir, sizeof(g_entropy_reservoir));

    // Pack Result Container (64 Bytes)
    *(uint32_t*)(res + 0)  = DR27_RES_MAGIC;
    *(uint32_t*)(res + 4)  = req_id;
    *(uint32_t*)(res + 8)  = status;
    *(uint16_t*)(res + 12) = g_fill_count;
    *(uint16_t*)(res + 14) = RESERVOIR_CAPACITY;
    *(uint16_t*)(res + 16) = g_current_mode;
    *(uint16_t*)(res + 18) = 0; // reserved
    *(uint32_t*)(res + 20) = state_crc;

    for (int i = 0; i < SLOT_SIZE; i++) {
        res[24 + i] = payload_out[i];
    }
    for (int i = 56; i < 64; i++) {
        res[i] = 0;
    }
}

} // extern "C"
