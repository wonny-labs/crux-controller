/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WORKLOAD_OS_H
#define WORKLOAD_OS_H

/*
 * The product-owned port to the operating system for the workload. The application declares it
 * and the adapter zone (app/os) implements it with Zephyr kernel calls, so app/src includes no
 * thread, queue or Zephyr header: the link joins the two, no include does. This header includes
 * only ISO C and the workload header, so it stays inside the rules of app/src.
 *
 * The workload runs two threads, a producer and a consumer, that are joined by one queue of
 * messages. The adapter fixes the depth of the queue and the sizes of the stacks. The port owns one
 * of each; there is no handle. Calls are made from thread context. The order is: start, then any number of the other calls, then both joins,
 * then release. After release the port can be started again.
 */

#include <stdint.h>

#include "workload.h"

typedef enum {
    WORKLOAD_OS_OK = 0,
    WORKLOAD_OS_TIMEOUT, /* the time given ran out */
    WORKLOAD_OS_FULL,    /* the queue has no room (queue_send) */
    WORKLOAD_OS_ERROR,   /* any other failure, or a call out of order */
} workload_os_status_t;

/*
 * Empty the queue and create the consumer thread, then the producer thread. Each thread runs its
 * entry function once and ends when the function returns. Returns WORKLOAD_OS_ERROR, with no
 * thread started, when a previous run was not released or an entry function is NULL.
 */
workload_os_status_t workload_os_start(void (*producer)(void), void (*consumer)(void));

/* Put one message on the queue without waiting. WORKLOAD_OS_FULL when there is no room. */
workload_os_status_t workload_os_queue_send(const workload_message_t *message);

/*
 * Take the oldest message from the queue and wait for one at most timeout_ms, 0 for no wait.
 * WORKLOAD_OS_TIMEOUT when none arrives in that time. A timeout above INT32_MAX counts as
 * INT32_MAX.
 */
workload_os_status_t workload_os_queue_receive(workload_message_t *message, uint32_t timeout_ms);

/* Suspend the calling thread for about ms milliseconds, 0 for none. */
void workload_os_sleep_ms(uint32_t ms);

/*
 * Wait for the producer, or the consumer, thread to end, at most timeout_ms. WORKLOAD_OS_TIMEOUT
 * when it is still running. A call after a successful join returns WORKLOAD_OS_OK at once. A
 * timeout above INT32_MAX counts as INT32_MAX.
 */
workload_os_status_t workload_os_join_producer(uint32_t timeout_ms);
workload_os_status_t workload_os_join_consumer(uint32_t timeout_ms);

/* After both joins succeeded: drop what is left in the queue and allow another start. */
void workload_os_release(void);

#endif
