// SPDX-License-Identifier: Apache-2.0
// DR1 ML-DSA-44 RejNTT sampler consuming eight fixed SHAKE128 block tokens.
//
// One C entry point is called exactly eight times by the sampler worker with
// one acquired terminal result token.  Calls 0..6 leave that token untouched;
// call 7 writes the terminal record and clears local sampler state.

#include <cstdint>

#if defined(__clang__)
#define DR1_SAMPLER_DISABLE_LOOP_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR1_SAMPLER_DISABLE_LOOP_UNROLL
#endif

namespace {

constexpr uint32_t kN = 256;
constexpr uint32_t kQ = 8380417;
constexpr uint32_t kBlockCap = 8;
constexpr uint32_t kBlockBytes = 180;
constexpr uint32_t kDataOffset = 12;
constexpr uint32_t kResultBytes = 1040;
constexpr uint32_t kResultMagic = 0x44523152;
constexpr uint32_t kOk = 0;
constexpr uint32_t kLimitExceeded = 1;
constexpr uint32_t kBadDescriptor = 2;

struct RejNttStateV1 {
    int32_t coefficient[kN];
    uint16_t accepted;
    uint16_t expected_block;
    uint8_t triple_tail[2];
    uint8_t tail_len;
    uint32_t request_id;
    uint32_t status;
};

static RejNttStateV1 g_sampler;

static void clear_bytes(void *address, uint32_t bytes) {
    volatile uint8_t *out = static_cast<volatile uint8_t *>(address);
    DR1_SAMPLER_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < bytes; ++index) out[index] = 0;
}

static uint16_t load_le16(const uint8_t *input) {
    return static_cast<uint16_t>(input[0]) | (static_cast<uint16_t>(input[1]) << 8);
}

static uint32_t load_le32(const uint8_t *input) {
    return static_cast<uint32_t>(input[0]) |
           (static_cast<uint32_t>(input[1]) << 8) |
           (static_cast<uint32_t>(input[2]) << 16) |
           (static_cast<uint32_t>(input[3]) << 24);
}

static void store_le16(uint8_t *output, uint16_t value) {
    output[0] = static_cast<uint8_t>(value);
    output[1] = static_cast<uint8_t>(value >> 8);
}

static void store_le32(uint8_t *output, uint32_t value) {
    output[0] = static_cast<uint8_t>(value);
    output[1] = static_cast<uint8_t>(value >> 8);
    output[2] = static_cast<uint8_t>(value >> 16);
    output[3] = static_cast<uint8_t>(value >> 24);
}

static void begin_request(const uint8_t block[kBlockBytes]) {
    clear_bytes(&g_sampler, sizeof(g_sampler));
    g_sampler.request_id = load_le32(block);
    g_sampler.status = kOk;
}

static void reject_candidate(uint8_t b0, uint8_t b1, uint8_t b2) {
    const uint32_t z = (static_cast<uint32_t>(b0) |
                        (static_cast<uint32_t>(b1) << 8) |
                        (static_cast<uint32_t>(b2) << 16)) & 0x7fffffU;
    if (z < kQ && g_sampler.accepted < kN) g_sampler.coefficient[g_sampler.accepted++] = static_cast<int32_t>(z);
}

static void consume_data(const uint8_t *data, uint16_t bytes_valid) {
    DR1_SAMPLER_DISABLE_LOOP_UNROLL
    for (uint16_t index = 0; index < bytes_valid; ++index) {
        if (g_sampler.tail_len < 2) {
            g_sampler.triple_tail[g_sampler.tail_len++] = data[index];
        } else {
            reject_candidate(g_sampler.triple_tail[0], g_sampler.triple_tail[1], data[index]);
            g_sampler.tail_len = 0;
        }
    }
}

static void write_result(uint8_t result[kResultBytes]) {
    DR1_SAMPLER_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < kResultBytes; ++index) result[index] = 0;
    if (g_sampler.status == kOk && (g_sampler.accepted != kN || g_sampler.tail_len != 0)) {
        g_sampler.status = kLimitExceeded;
    }
    store_le32(result, kResultMagic);
    store_le32(result + 4, g_sampler.request_id);
    store_le32(result + 8, g_sampler.status);
    store_le16(result + 12, g_sampler.status == kOk ? kN : 0);
    result[14] = kBlockCap;
    result[15] = 0;
    if (g_sampler.status == kOk) {
        DR1_SAMPLER_DISABLE_LOOP_UNROLL
        for (uint32_t index = 0; index < kN; ++index) {
            store_le32(result + 16 + 4 * index, static_cast<uint32_t>(g_sampler.coefficient[index]));
        }
    }
}

// One shared dispatcher carries expected sequence across all eight calls.  If
// a prior run was interrupted, a sequence-zero token with a new request ID
// starts a new request boundary.  A same-ID retry after an interrupted schedule
// is intentionally outside this fixed eight-call graph contract.
__attribute__((noinline)) static void consume_next(const uint8_t block[kBlockBytes],
                                                    uint8_t result[kResultBytes]) {
    const uint32_t request_id = load_le32(block);
    const uint16_t sequence = load_le16(block + 4);
    const uint16_t bytes_valid = load_le16(block + 6);
    const uint32_t producer_status = load_le32(block + 8);

    if (g_sampler.expected_block == 0 ||
        (sequence == 0 && g_sampler.expected_block != 0 && request_id != g_sampler.request_id)) {
        begin_request(block);
    }
    const uint32_t expected = g_sampler.expected_block;
    if (request_id != g_sampler.request_id || sequence != expected) {
        g_sampler.status = kBadDescriptor;
    } else if (producer_status == kBadDescriptor) {
        g_sampler.status = kBadDescriptor;
    } else if (producer_status != kOk || bytes_valid != 168) {
        g_sampler.status = kBadDescriptor;
    } else if (g_sampler.status == kOk) {
        consume_data(block + kDataOffset, bytes_valid);
    }

    ++g_sampler.expected_block;
    if (expected == kBlockCap - 1) {
        write_result(result);
        clear_bytes(&g_sampler, sizeof(g_sampler));
    }
}

}  // namespace

extern "C" {
void dr1_rejntt_consume_next(const uint8_t input[kBlockBytes], uint8_t result[kResultBytes]) {
    consume_next(input, result);
}
}  // extern "C"
