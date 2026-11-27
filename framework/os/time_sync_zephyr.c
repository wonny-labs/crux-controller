/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The adapter zone of the sntp capability: the one place that queries an SNTP server and runs the
 * thread that does it. It implements the port that framework/src declares (time_sync_port.h) with
 * two Zephyr headers of the allow-list of docs/composition-zone.md for this zone, <zephyr/kernel.h>
 * and <zephyr/net/sntp.h>. It includes no socket header, which the zone may not, so it calls the
 * library's string-based one-shot query sntp_simple() and nothing else of it: sntp_init() and
 * sntp_query() need a socket address type. The adapter never sets a clock. The product's glue
 * framework/src/time_sync.c does, through the Crux Time authority, and nothing else in the image
 * does.
 *
 * What the library does, read at Zephyr v4.4.0 (include/zephyr/net/sntp.h and
 * subsys/net/lib/sntp/sntp.c, sntp_simple.c); between v4.4.0 and v4.4.2 the only change under
 * subsys/net/lib/sntp and include/zephyr/net/sntp.h is a fix in sntp_close_async(), which this file
 * does not call. The revision that west.yml pins through Crux is now v4.5.0. Between v4.4.2 and
 * v4.5.0 sntp_simple.c and the functions of sntp.h are unchanged; sntp.c clamps the delay and the
 * uncertainty and checks the precision only for the uncertainty option, which is not selected, so
 * ts and the codes below are as described; CONFIG_SNTP now selects SNTP_LIB, and the new SNTP
 * server (CONFIG_SNTP_SERVER) is not selected:
 *   - sntp_simple(server, timeout, &ts) takes "addr[:port]" (port 123 by default), resolves it
 *     with getaddrinfo (an IPv4 literal needs no DNS), opens one UDP socket, resends the request
 *     with a growing wait (100, 200, 400, 800, then 1600 ms) until the timeout is over, and closes
 *     the socket. The deadline is checked between rounds, so a call can run past it by up to one
 *     round's wait (1600 ms at most), or longer while it skips answers to earlier requests. It
 *     keeps one static hints structure, so only one thread may call it at a time.
 *   - It returns 0 with ts filled, or a negative errno: -ETIMEDOUT when no answer arrived in time;
 *     -EBUSY for a kiss-o'-death answer (stratum 0); -EINVAL for a wrong mode, a zero transmit
 *     time or a transmit time before 1970; -ERANGE for an originate time that is not the request's
 *     (a late answer to an earlier request: from the second round on the library skips such
 *     answers and keeps waiting for the current one, so -ERANGE is returned only when the first
 *     answer is already a stale one); -EMSGSIZE for a short packet; and the errno of a failed
 *     socket, connect or send. Every code other than -ETIMEDOUT and -EBUSY is reported as an
 *     error here.
 *   - ts.seconds counts from 1970-01-01 and ts.fraction in units of 2^-32 s (the uncertainty
 *     option, which would change both, is not selected). The policy converts them.
 *
 * The thread runs at priority 10, after the workload threads (5, see workload_os_zephyr.c) and
 * before the log thread (14). The priority and the stack are starting values and were not measured.
 */

#include "../src/time_sync_policy.h"
#include "../src/time_sync_port.h"
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
#include "../src/fault_injection.h"
#include "../src/supervisor_port.h"
#endif

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/kernel.h>
#include <zephyr/net/sntp.h>

#define TIME_SYNC_THREAD_PRIORITY 10

#define TIME_SYNC_STACK_DEFAULT_BYTES 8192
#ifdef CONFIG_CRUX_CONTROLLER_TIME_STACK
#define TIME_SYNC_STACK_BYTES CONFIG_CRUX_CONTROLLER_TIME_STACK
#else
#define TIME_SYNC_STACK_BYTES TIME_SYNC_STACK_DEFAULT_BYTES
#endif

BUILD_ASSERT(CONFIG_NUM_PREEMPT_PRIORITIES > TIME_SYNC_THREAD_PRIORITY,
             "the thread needs a preemptive priority below the workload threads");

static K_THREAD_STACK_DEFINE(time_sync_stack, TIME_SYNC_STACK_BYTES);
static struct k_thread time_sync_thread;
static void (*thread_entry)(void);
static bool started;

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
/* The thread's task watchdog channel (specification section 4.3): it feeds before and after each
 * query and once per slice of a sleep. A query can run past its timeout by up to one round of the
 * library (1600 ms, see above), so the reload period covers the timeout, that round and one slice,
 * with a margin. */
#define TIME_SYNC_SLICE_MS 1000u
#define TIME_SYNC_RELOAD_MS                                                                        \
    ((uint32_t)CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS + 1600u + 2u * TIME_SYNC_SLICE_MS + 2000u)
static int channel = -1;

static void feed(void)
{
    if (fault_injection_thread_stalls("time")) {
        supervisor_port_stall();
    }
    supervisor_port_channel_feed(channel);
}

#endif

time_sync_sample_result_t time_sync_port_query(const char *server, uint32_t timeout_ms,
                                               time_sync_instant_t *sample)
{
    struct sntp_time answer = {0};

    if (server == NULL || sample == NULL) {
        return TIME_SYNC_SAMPLE_ERROR;
    }
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    feed();
#endif
    const int result = sntp_simple(server, timeout_ms, &answer);
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    feed();
#endif

    if (result == 0) {
        *sample = time_sync_instant_from_sntp(
            (time_sync_sntp_answer_t){.seconds = answer.seconds, .fraction = answer.fraction});
        return TIME_SYNC_SAMPLE_OK;
    }
    if (result == -ETIMEDOUT) {
        return TIME_SYNC_SAMPLE_TIMEOUT;
    }
    if (result == -EBUSY) {
        return TIME_SYNC_SAMPLE_KISS_OF_DEATH;
    }
    return TIME_SYNC_SAMPLE_ERROR;
}

#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
void time_sync_port_sleep_ms(uint32_t ms)
{
    uint32_t left = ms;

    while (left > 0u) {
        const uint32_t slice = left < TIME_SYNC_SLICE_MS ? left : TIME_SYNC_SLICE_MS;

        feed();
        (void)k_sleep(K_MSEC(slice));
        left -= slice;
    }
    feed();
}
#else
void time_sync_port_sleep_ms(uint32_t ms)
{
    (void)k_sleep(K_MSEC(ms));
}
#endif

static void time_sync_thread_run(void *unused0, void *unused1, void *unused2)
{
    (void)unused0;
    (void)unused1;
    (void)unused2;
#ifdef CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION
    channel = supervisor_port_channel_add("time", TIME_SYNC_RELOAD_MS);
#endif
    thread_entry();
}

time_sync_port_status_t time_sync_port_start(void (*entry)(void))
{
    if (started || entry == NULL) {
        return TIME_SYNC_PORT_ERROR;
    }
    thread_entry = entry;
    /* A thread that is created cannot fail to be: k_thread_create returns the thread it was
     * given. */
    (void)k_thread_create(&time_sync_thread, time_sync_stack,
                          K_THREAD_STACK_SIZEOF(time_sync_stack), time_sync_thread_run, NULL, NULL,
                          NULL, TIME_SYNC_THREAD_PRIORITY, 0, K_NO_WAIT);
    (void)k_thread_name_set(&time_sync_thread, "time");
    started = true;
    return TIME_SYNC_PORT_OK;
}
