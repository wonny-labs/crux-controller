/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The adapter zone of the workload: the one place that creates threads, queues messages and
 * sleeps. It implements the port that app/src declares (workload_os.h) with Zephyr kernel calls,
 * where the workload used the Crux Thread and Queue contracts before. The one Zephyr header is
 * <zephyr/kernel.h>, the single entry on the allow-list of docs/composition-zone.md for this zone.
 *
 * The numbers below are the ones that the Crux providers gave this workload, read at crux-pilot
 * revision 37c92b18b44b7dfb95c2109f036f23d00f05cb4c (the revision that west.yml pins when this
 * file was written). This file may not include <crux/thread.h> or <crux/queue.h>, so it cannot
 * compare against them: each BUILD_ASSERT below compares a name to the literal copied from the
 * provider, so that a change of either side is a visible edit. The provider paths are relative to
 * the crux-pilot repository.
 *
 *   thread priority  components/thread/ports/zephyr/thread_native.c:99
 *                    native_priority = 6 - options->priority, and CRUX_THREAD_PRIORITY_NORMAL is 1
 *                    (components/thread/include/crux/thread.h:28), so Zephyr priority 5.
 *                    thread_native.c:5 asserts CONFIG_NUM_PREEMPT_PRIORITIES > 6.
 *   stack bytes      thread_native.c:7 declares the stacks with CRUX_THREAD_STACK_BYTES, whose
 *                    default is 4096 (components/thread/src/thread_internal.h:14). This workload
 *                    takes its size from CONFIG_CRUX_CONTROLLER_WORKER_STACK, default 4096, and
 *                    the S2 image sets both options to 8192. One stack per thread.
 *   queue depth      8 messages and an item of sizeof(workload_message_t), 8 bytes: what
 *   and item size    workload_thread.c passed to crux_queue_create before this adapter. The
 *                    provider accepts up to 16 and 64 (components/queue/src/queue.c:8-9).
 *   timeouts         thread_native.c:48-66 and components/queue/ports/zephyr/queue_port.c:26-40:
 *                    zero is K_NO_WAIT, otherwise an absolute deadline
 *                    K_TIMEOUT_ABS_TICKS(k_uptime_ticks() + k_ms_to_ticks_ceil64(ms) + 1)
 *                    (thread_native.c:64, queue_port.c:38). That is not K_MSEC(ms), which is
 *                    relative and has no extra tick. deadline_from_ms() builds the same value.
 *   join             thread_native.c:114: k_thread_join with that deadline. A timeout is
 *                    WORKLOAD_OS_TIMEOUT, as the provider's -EAGAIN is CRUX_ERR_TIMEOUT.
 *
 * The queue is not the same implementation. The Crux Queue provider is a ring behind one mutex and
 * a condition variable (queue_port.c). This adapter uses k_msgq. Depth, item size, the timeouts and
 * the first-in first-out order match; the internal locking does not.
 */

#include "../src/workload_os.h"

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>

#include <zephyr/kernel.h>

/* The Crux provider's priority mapping and the level this workload asked for (see above). */
#define WORKLOAD_OS_PROVIDER_PRIORITY_BASE 6
#define WORKLOAD_OS_PROVIDER_PRIORITY_NORMAL 1
#define WORKLOAD_OS_THREAD_PRIORITY \
    (WORKLOAD_OS_PROVIDER_PRIORITY_BASE - WORKLOAD_OS_PROVIDER_PRIORITY_NORMAL)

#define WORKLOAD_OS_STACK_DEFAULT_BYTES 4096
#ifdef CONFIG_CRUX_CONTROLLER_WORKER_STACK
#define WORKLOAD_OS_STACK_BYTES CONFIG_CRUX_CONTROLLER_WORKER_STACK
#else
#define WORKLOAD_OS_STACK_BYTES WORKLOAD_OS_STACK_DEFAULT_BYTES
#endif

#define WORKLOAD_OS_QUEUE_DEPTH 8
#define WORKLOAD_OS_ITEM_BYTES sizeof(workload_message_t)

BUILD_ASSERT(CONFIG_NUM_PREEMPT_PRIORITIES > 6, "the provider needs preemptive priorities 4..6");
BUILD_ASSERT(WORKLOAD_OS_THREAD_PRIORITY == 5, "Crux normal priority is Zephyr priority 5");
BUILD_ASSERT(WORKLOAD_OS_STACK_DEFAULT_BYTES == 4096, "the provider's default stack is 4096 bytes");
BUILD_ASSERT(WORKLOAD_OS_QUEUE_DEPTH == 8, "the queue holds 8 messages");
BUILD_ASSERT(WORKLOAD_OS_ITEM_BYTES == 8, "a queue item is a workload_message_t of 8 bytes");
BUILD_ASSERT(WORKLOAD_OS_ITEM_BYTES % sizeof(uint32_t) == 0, "k_msgq items are 4-byte aligned");

static K_THREAD_STACK_DEFINE(producer_stack, WORKLOAD_OS_STACK_BYTES);
static K_THREAD_STACK_DEFINE(consumer_stack, WORKLOAD_OS_STACK_BYTES);
static struct k_thread producer_thread;
static struct k_thread consumer_thread;

static struct k_msgq queue;
static char __aligned(sizeof(uint32_t))
    queue_buffer[WORKLOAD_OS_QUEUE_DEPTH * sizeof(workload_message_t)];

static void (*producer_entry)(void);
static void (*consumer_entry)(void);
static bool started;

/* The deadline that the Crux providers build for a timeout in milliseconds. */
static k_timeout_t deadline_from_ms(uint32_t ms)
{
    if (ms == 0u) {
        return K_NO_WAIT;
    }
    if (ms > (uint32_t)INT32_MAX) {
        ms = (uint32_t)INT32_MAX;
    }
    const int64_t now = k_uptime_ticks();
    const int64_t duration = k_ms_to_ticks_ceil64(ms);

    /* One extra tick covers the unobserved fraction of the current tick. */
    return K_TIMEOUT_ABS_TICKS(now + duration + 1);
}

static void producer_run(void *unused0, void *unused1, void *unused2)
{
    (void)unused0;
    (void)unused1;
    (void)unused2;
    producer_entry();
}

static void consumer_run(void *unused0, void *unused1, void *unused2)
{
    (void)unused0;
    (void)unused1;
    (void)unused2;
    consumer_entry();
}

workload_os_status_t workload_os_start(void (*producer)(void), void (*consumer)(void))
{
    if (started || producer == NULL || consumer == NULL) {
        return WORKLOAD_OS_ERROR;
    }
    producer_entry = producer;
    consumer_entry = consumer;
    k_msgq_init(&queue, queue_buffer, WORKLOAD_OS_ITEM_BYTES, WORKLOAD_OS_QUEUE_DEPTH);
    /* The consumer first, so that it waits on the queue before the producer fills it. A thread
     * that is created cannot fail to be: k_thread_create returns the thread it was given. */
    (void)k_thread_create(&consumer_thread, consumer_stack, K_THREAD_STACK_SIZEOF(consumer_stack),
                          consumer_run, NULL, NULL, NULL, WORKLOAD_OS_THREAD_PRIORITY, 0,
                          K_NO_WAIT);
    (void)k_thread_create(&producer_thread, producer_stack, K_THREAD_STACK_SIZEOF(producer_stack),
                          producer_run, NULL, NULL, NULL, WORKLOAD_OS_THREAD_PRIORITY, 0,
                          K_NO_WAIT);
    started = true;
    return WORKLOAD_OS_OK;
}

workload_os_status_t workload_os_queue_send(const workload_message_t *message)
{
    if (message == NULL) {
        return WORKLOAD_OS_ERROR;
    }
    const int result = k_msgq_put(&queue, message, K_NO_WAIT);

    if (result == 0) {
        return WORKLOAD_OS_OK;
    }
    return result == -ENOMSG || result == -EAGAIN ? WORKLOAD_OS_FULL : WORKLOAD_OS_ERROR;
}

workload_os_status_t workload_os_queue_receive(workload_message_t *message, uint32_t timeout_ms)
{
    if (message == NULL) {
        return WORKLOAD_OS_ERROR;
    }
    const int result = k_msgq_get(&queue, message, deadline_from_ms(timeout_ms));

    if (result == 0) {
        return WORKLOAD_OS_OK;
    }
    return result == -ENOMSG || result == -EAGAIN ? WORKLOAD_OS_TIMEOUT : WORKLOAD_OS_ERROR;
}

void workload_os_sleep_ms(uint32_t ms)
{
    (void)k_sleep(deadline_from_ms(ms));
}

static workload_os_status_t join(struct k_thread *thread, uint32_t timeout_ms)
{
    if (!started) {
        return WORKLOAD_OS_ERROR;
    }
    const int result = k_thread_join(thread, deadline_from_ms(timeout_ms));

    if (result == 0) {
        return WORKLOAD_OS_OK;
    }
    return result == -EBUSY || result == -EAGAIN ? WORKLOAD_OS_TIMEOUT : WORKLOAD_OS_ERROR;
}

workload_os_status_t workload_os_join_producer(uint32_t timeout_ms)
{
    return join(&producer_thread, timeout_ms);
}

workload_os_status_t workload_os_join_consumer(uint32_t timeout_ms)
{
    return join(&consumer_thread, timeout_ms);
}

void workload_os_release(void)
{
    k_msgq_purge(&queue);
    started = false;
}
