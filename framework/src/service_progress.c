/* SPDX-License-Identifier: Apache-2.0 */

/* Supervision of the Crux service threads by their progress (service_progress.h). */

#include "service_progress.h"

#include <stdatomic.h>
#include <stddef.h>

/* The handle of each thread's channel, or -1 while it has none. Written once, on the start
 * function's thread; read on the service threads. */
static atomic_int handles[SERVICE_THREAD_COUNT] = {-1, -1, -1, -1};
_Static_assert(SERVICE_THREAD_COUNT == 4, "handles lists every thread");

static const service_progress_port_t *progress_port;
static uint32_t progress_reload_ms;

static const char *const names[SERVICE_THREAD_COUNT] = {
    "event drain",
    "web session",
    "web management",
    "console",
};

static bool known(service_thread_t thread)
{
    return (int)thread >= 0 && (int)thread < (int)SERVICE_THREAD_COUNT;
}

void service_progress_init(const service_progress_port_t *port, uint32_t reload_ms)
{
    progress_port = port;
    progress_reload_ms = reload_ms;
    for (size_t index = 0; index < (size_t)SERVICE_THREAD_COUNT; index++) {
        atomic_store(&handles[index], -1);
    }
}

int service_progress_activate(service_thread_t thread)
{
    if (!known(thread) || progress_port == NULL || progress_port->channel_add == NULL ||
        progress_port->channel_feed == NULL || progress_reload_ms == 0u) {
        return SERVICE_PROGRESS_ERR_ARGUMENT;
    }
    if (atomic_load(&handles[thread]) >= 0) {
        return SERVICE_PROGRESS_ERR_ACTIVE;
    }
    const int handle = progress_port->channel_add(names[thread], progress_reload_ms);

    if (handle < 0) {
        return SERVICE_PROGRESS_ERR_FULL;
    }
    atomic_store(&handles[thread], handle);
    return handle;
}

void service_progress_report(service_thread_t thread)
{
    if (!known(thread)) {
        return;
    }
    const int handle = atomic_load(&handles[thread]);

    if (handle < 0) {
        return;
    }
    /* The port was set before the activation that published the handle. */
    if (progress_port->silenced != NULL && progress_port->silenced(names[thread])) {
        return;
    }
    progress_port->channel_feed(handle);
}

bool service_progress_active(service_thread_t thread)
{
    return known(thread) && atomic_load(&handles[thread]) >= 0;
}

const char *service_progress_name(service_thread_t thread)
{
    return known(thread) ? names[thread] : NULL;
}
