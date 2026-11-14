/* SPDX-License-Identifier: Apache-2.0 */

#include "workload_thread.h"

#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include <crux/logging.h>
#include <crux/status.h>
#include <crux/time.h>

#include "workload_os.h"

enum {
    JOIN_TIMEOUT_MS = 2000,
    RECEIVE_TIMEOUT_MS = 50,
    /* The consumer may be inside a sink that takes up to its own deadline for each of the
     * queued messages, so it is given longer than the producer to finish. */
    CONSUMER_JOIN_TIMEOUT_MS = 30000,
    /* The producer sleeps in slices, so that a stop request is seen within this time. */
    MAX_SLEEP_MS = 50,
};

static struct {
    workload_config_t config;
    atomic_bool stop_producer;
    atomic_bool stop_consumer;
    bool running;
    workload_sink_t sink;
} state;

static crux_status_t elapsed_ms(crux_monotonic_time_t start, uint64_t *out)
{
    crux_monotonic_time_t now;
    const crux_status_t status = crux_monotonic_now(&now);

    if (status != CRUX_OK) {
        return status;
    }
    const int64_t ms = crux_duration_to_ms_floor(crux_monotonic_diff(now, start));
    *out = ms < 0 ? 0u : (uint64_t)ms;
    return CRUX_OK;
}

/* A join that did not succeed: a timeout is CRUX_ERR_TIMEOUT, anything else CRUX_ERR_IO. */
static crux_status_t join_status(workload_os_status_t result)
{
    if (result == WORKLOAD_OS_OK) {
        return CRUX_OK;
    }
    return result == WORKLOAD_OS_TIMEOUT ? CRUX_ERR_TIMEOUT : CRUX_ERR_IO;
}

static void producer_main(void)
{
    crux_monotonic_time_t start;
    workload_cycle_t cycle;

    if (crux_monotonic_now(&start) != CRUX_OK ||
        workload_cycle_init(&cycle, &state.config, 0) != WORKLOAD_OK) {
        (void)crux_log_write(CRUX_LOG_ERROR, "workload", "producer could not start");
        return;
    }
    while (!atomic_load(&state.stop_producer)) {
        uint64_t now_ms;
        uint32_t due = 0;

        if (elapsed_ms(start, &now_ms) != CRUX_OK ||
            workload_cycle_due(&cycle, &state.config, now_ms, &due) != WORKLOAD_OK) {
            (void)crux_log_write(CRUX_LOG_ERROR, "workload", "producer stopped on a clock error");
            return;
        }
        if (due == 0) {
            uint64_t wait_ms = cycle.next_ms - now_ms;

            if (wait_ms > MAX_SLEEP_MS) {
                wait_ms = MAX_SLEEP_MS;
            }
            workload_os_sleep_ms((uint32_t)wait_ms);
            continue;
        }
        for (uint32_t i = 0; i < due; i++) {
            const uint32_t number = cycle.cycle - due + 1u + i;

            if (number % state.config.message_every != 0u) {
                continue;
            }
            const workload_message_t message = {.cycle = number, .value = WORKLOAD_VALUE_OF(number)};

            if (workload_os_queue_send(&message) != WORKLOAD_OS_OK) {
                (void)crux_log_write(CRUX_LOG_WARN, "workload", "queue full, message dropped");
            }
        }
    }
}

static void consumer_main(void)
{
    for (;;) {
        workload_message_t message;
        const workload_os_status_t status = workload_os_queue_receive(&message, RECEIVE_TIMEOUT_MS);

        if (status == WORKLOAD_OS_OK) {
            char text[64];

            (void)snprintf(text, sizeof text, "cycle=%u value=%u", (unsigned)message.cycle,
                           (unsigned)message.value);
            (void)crux_log_write(CRUX_LOG_INFO, "workload", text);
            if (state.sink != NULL) {
                state.sink(&message);
            }
            continue;
        }
        /* The consumer is asked to stop only after the producer was joined, so a timeout with
         * that request means the queue is drained. Any other result ends the thread. */
        if (status != WORKLOAD_OS_TIMEOUT || atomic_load(&state.stop_consumer)) {
            return;
        }
    }
}

void workload_thread_set_sink(workload_sink_t sink)
{
    state.sink = sink;
}

int workload_thread_start(const workload_config_t *config)
{
    if (state.running) {
        return CRUX_ERR_INVALID_STATE;
    }
    if (workload_config_validate(config) != WORKLOAD_OK) {
        return CRUX_ERR_INVALID_ARGUMENT;
    }
    state.config = *config;
    atomic_store(&state.stop_producer, false);
    atomic_store(&state.stop_consumer, false);

    /* The adapter creates the consumer first and the producer second, and creates neither when it
     * returns an error. The kernel does not fail to create a thread, so there is no half-started
     * state to unwind here. */
    if (workload_os_start(producer_main, consumer_main) != WORKLOAD_OS_OK) {
        return CRUX_ERR_NO_RESOURCES;
    }
    state.running = true;
    return 0;
}

int workload_thread_stop(void)
{
    crux_status_t status;

    if (!state.running) {
        return CRUX_ERR_INVALID_STATE;
    }
    /* Producer first, so that nothing is queued after the consumer is told to finish. */
    atomic_store(&state.stop_producer, true);
    status = join_status(workload_os_join_producer(JOIN_TIMEOUT_MS));
    if (status != CRUX_OK) {
        return status;
    }
    atomic_store(&state.stop_consumer, true);
    status = join_status(workload_os_join_consumer(CONSUMER_JOIN_TIMEOUT_MS));
    if (status != CRUX_OK) {
        return status;
    }
    workload_os_release();
    state.running = false;
    return 0;
}
