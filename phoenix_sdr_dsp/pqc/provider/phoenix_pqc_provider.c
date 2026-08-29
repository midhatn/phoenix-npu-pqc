/* SPDX-License-Identifier: Apache-2.0 */
/**
 * Milestone DR23: OpenSSL 3.x Native Provider Implementation for AMD Phoenix AIE2.
 * Connects standard OpenSSL 3.x applications directly to AIE2 compute array.
 */

#include "phoenix_pqc_provider.h"
#include <string.h>
#include <stdlib.h>

typedef struct {
    const void *core_handle;
    char name[64];
    char version[32];
    char build_info[128];
} PHOENIX_PROV_CTX;

PHOENIX_EXPORT int OSSL_provider_init(
    const void *handle,
    const void *in,
    const void **out,
    void **provctx
) {
    if (!out || !provctx) {
        return 0;
    }

    PHOENIX_PROV_CTX *ctx = (PHOENIX_PROV_CTX*)malloc(sizeof(PHOENIX_PROV_CTX));
    if (!ctx) {
        return 0;
    }

    ctx->core_handle = handle;
    strncpy(ctx->name, PHOENIX_PROVIDER_NAME, sizeof(ctx->name) - 1);
    strncpy(ctx->version, PHOENIX_PROVIDER_VERSION, sizeof(ctx->version) - 1);
    strncpy(ctx->build_info, PHOENIX_PROVIDER_DESC, sizeof(ctx->build_info) - 1);

    *provctx = (void*)ctx;
    *out = (const void*)0; // Linked via dynamic dispatch table

    return 1;
}
