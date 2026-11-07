/* SPDX-License-Identifier: Apache-2.0 */

#include "composition.h"

#include <crux/status.h>
#include <crux/time.h>

#ifdef CONFIG_CRUX_THREAD
#include "workload.h"
#include "workload_thread.h"
#endif

#ifdef CONFIG_CRUX_CONTROLLER_S2
#include <stdio.h>

#include <crux/logging.h>

#include "net_client.h"

/* S2: every logged message also goes to the peer. */
static void exchange_with_peer(const workload_message_t *message)
{
    char text[64];
    const int result = net_client_exchange(message);

    if (result == NET_CLIENT_OK) {
        (void)snprintf(text, sizeof text, "exchange ok cycle=%u", (unsigned)message->cycle);
        (void)crux_log_write(CRUX_LOG_INFO, "net", text);
    } else {
        (void)snprintf(text, sizeof text, "exchange failed cycle=%u result=%d",
                       (unsigned)message->cycle, result);
        (void)crux_log_write(CRUX_LOG_WARN, "net", text);
    }
}
#endif

int composition_start(void)
{
    crux_monotonic_time_t now;

    /* S0: the clock answers. */
    const crux_status_t clock = crux_monotonic_now(&now);
    if (clock != CRUX_OK) {
        return clock;
    }
#ifdef CONFIG_CRUX_THREAD
    /* S1: the workload runs on Crux threads and reports through Crux Logging. */
    workload_config_t config;

    if (workload_config_default(&config) != WORKLOAD_OK) {
        return CRUX_ERR_INVALID_ARGUMENT;
    }
#ifdef CONFIG_CRUX_CONTROLLER_S2
    workload_thread_set_sink(exchange_with_peer);
#endif
    return workload_thread_start(&config);
#else
    return 0;
#endif
}
