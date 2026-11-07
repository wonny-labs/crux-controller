/* SPDX-License-Identifier: Apache-2.0 */

#include "workload_thread.h"

#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include <crux/logging.h>
#include <crux/queue.h>
#include <crux/status.h>
#include <crux/thread.h>
#include <crux/time.h>

#ifdef CONFIG_CRUX_CONTROLLER_WORKER_STACK
#define WORKER_STACK_BYTES CONFIG_CRUX_CONTROLLER_WORKER_STACK
#else
#define WORKER_STACK_BYTES 4096
#endif

enum {
    QUEUE_CAPACITY = 8,
    STACK_BYTES = WORKER_STACK_BYTES,
    JOIN_TIMEOUT_MS = 2000,
    RECEIVE_TIMEOUT_MS = 50,
    /* The producer sleeps in slices, so that a stop request is seen within this time. */
    MAX_SLEEP_MS = 50,
};

static struct {
    workload_config_t config;
    crux_queue_t queue;
    crux_thread_t producer;
    crux_thread_t consumer;
    atomic_bool stop;
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

static void producer_main(void *argument)
{
    (void)argument;
    crux_monotonic_time_t start;
    workload_cycle_t cycle;

    if (crux_monotonic_now(&start) != CRUX_OK ||
        workload_cycle_init(&cycle, &state.config, 0) != WORKLOAD_OK) {
        (void)crux_log_write(CRUX_LOG_ERROR, "workload", "producer could not start");
        return;
    }
    while (!atomic_load(&state.stop)) {
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
            (void)crux_thread_sleep_for(crux_duration_from_ms((int32_t)wait_ms));
            continue;
        }
        for (uint32_t i = 0; i < due; i++) {
            const uint32_t number = cycle.cycle - due + 1u + i;

            if (number % state.config.message_every != 0u) {
                continue;
            }
            const workload_message_t message = {.cycle = number, .value = WORKLOAD_VALUE_OF(number)};

            if (crux_queue_send(state.queue, &message, sizeof message, 0) != CRUX_OK) {
                (void)crux_log_write(CRUX_LOG_WARN, "workload", "queue full, message dropped");
            }
        }
    }
}

static void consumer_main(void *argument)
{
    (void)argument;
    for (;;) {
        workload_message_t message;
        const crux_status_t status =
            crux_queue_receive(state.queue, &message, sizeof message, RECEIVE_TIMEOUT_MS);

        if (status == CRUX_OK) {
            char text[64];

            (void)snprintf(text, sizeof text, "cycle=%u value=%u", (unsigned)message.cycle,
                           (unsigned)message.value);
            (void)crux_log_write(CRUX_LOG_INFO, "workload", text);
            if (state.sink != NULL) {
                state.sink(&message);
            }
            continue;
        }
        /* A timeout with a stop request means the queue is drained. Any other result ends the thread. */
        if (status != CRUX_ERR_TIMEOUT || atomic_load(&state.stop)) {
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
    const crux_thread_options_t options = {
        .stack_size_bytes = STACK_BYTES, .priority = CRUX_THREAD_PRIORITY_NORMAL};
    crux_status_t status;

    if (state.running) {
        return CRUX_ERR_INVALID_STATE;
    }
    if (workload_config_validate(config) != WORKLOAD_OK) {
        return CRUX_ERR_INVALID_ARGUMENT;
    }
    state.config = *config;
    atomic_store(&state.stop, false);

    status = crux_queue_create(QUEUE_CAPACITY, sizeof(workload_message_t), &state.queue);
    if (status != CRUX_OK) {
        return status;
    }
    status = crux_thread_create(&options, consumer_main, NULL, &state.consumer);
    if (status != CRUX_OK) {
        (void)crux_queue_destroy(&state.queue);
        return status;
    }
    status = crux_thread_create(&options, producer_main, NULL, &state.producer);
    if (status != CRUX_OK) {
        atomic_store(&state.stop, true);
        (void)crux_thread_join(&state.consumer, JOIN_TIMEOUT_MS);
        (void)crux_queue_destroy(&state.queue);
        return status;
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
    atomic_store(&state.stop, true);
    status = crux_thread_join(&state.producer, JOIN_TIMEOUT_MS);
    if (status != CRUX_OK) {
        return status;
    }
    status = crux_thread_join(&state.consumer, JOIN_TIMEOUT_MS);
    if (status != CRUX_OK) {
        return status;
    }
    status = crux_queue_destroy(&state.queue);
    if (status != CRUX_OK) {
        return status;
    }
    state.running = false;
    return 0;
}
