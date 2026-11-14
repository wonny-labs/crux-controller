/* SPDX-License-Identifier: Apache-2.0 */

#include "composition.h"

#include <crux/status.h>
#include <crux/time.h>

#ifdef CONFIG_CRUX_CONTROLLER_S1
#include "workload.h"
#include "workload_thread.h"
#endif

#ifdef CONFIG_CRUX_CONTROLLER_S3
#include "config_store.h"
#include "storage_port.h"
#endif

#ifdef CONFIG_CRUX_CONTROLLER_S4
#include "health.h"
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

#ifdef CONFIG_CRUX_CONTROLLER_S3
/* S3: the saved record replaces the default, and a first start saves the default. A volume that
 * does not mount or bind leaves the default in use, and the volume is never formatted. */
static void configure_from_storage(workload_config_t *config)
{
    workload_config_t saved;

    if (storage_port_mount(STORAGE_PORT_KEEP_VOLUME) != STORAGE_PORT_OK ||
        storage_port_bind() != STORAGE_PORT_OK) {
        return;
    }
    switch (config_store_load(&saved)) {
    case CONFIG_STORE_OK:
        *config = saved;
        break;
    case CONFIG_STORE_ERR_NOT_FOUND:
        (void)config_store_save(config);
        break;
    default:
        break;
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
#ifdef CONFIG_CRUX_CONTROLLER_S1
    /* S1: the workload runs on Zephyr threads behind the product-owned port (the Zephyr calls are in
     * app/os) and reports through Crux Logging. */
    workload_config_t config;

    if (workload_config_default(&config) != WORKLOAD_OK) {
        return CRUX_ERR_INVALID_ARGUMENT;
    }
#ifdef CONFIG_CRUX_CONTROLLER_S3
    configure_from_storage(&config);
#endif
#ifdef CONFIG_CRUX_CONTROLLER_S4
    /* S4: say why the last run ended, then arm the watchdog for the configured cycle, after the
     * storage so that a slow mount cannot cost a reset. The producer feeds it once for each pass
     * that has cycles due. No watchdog runs only when the policy or Crux refuses the interval, or
     * there is no device; on any other error the native start may have been attempted, the
     * state is unknown, nothing feeds it and the watchdog may still reset the board. Either way
     * health.c reports it and the workload starts. */
    (void)health_report_reset_cause();
    (void)health_watchdog_start(config.period_ms);
    workload_thread_set_cycle_hook(health_cycle);
#endif
#ifdef CONFIG_CRUX_CONTROLLER_S2
    workload_thread_set_sink(exchange_with_peer);
#endif
    return workload_thread_start(&config);
#else
    return 0;
#endif
}
