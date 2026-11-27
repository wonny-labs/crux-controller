/* SPDX-License-Identifier: Apache-2.0 */

/* Runs the application's own time_sync.c, time_sync_policy.c and time_sync_zephyr.c on the real
 * Crux Time provider and Zephyr's real SNTP library, over the loopback interface of native_sim,
 * against a UDP responder of this test. The responder answers on port 123 of 127.0.0.1 with a real
 * SNTP packet whose time, delay and kind each case chooses. The test reads the Crux Time snapshot
 * and the log, and never sets a clock itself: only the glue does. One case per image, chosen by
 * SNTP_CASE, because Crux Time keeps its state for the whole run.
 *
 * What this scenario shows is the glue, the adapter and the library working together on one
 * simulated clock: a first answer, a kiss-o'-death, a late answer, an answer outside the supported
 * range, a refused step and the re-synchronisation after it, a correction and a difference below
 * the threshold, and a clock that nothing confirms. What it does not show is the real world: a real
 * server, a real network path and a board are not shown here, and the limits are test values (a 600
 * ms timeout, a stale age of two seconds), not the defaults of the image. It also cannot show a
 * failed native write, because the simulator's clock accepts every value in range. */

#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>

#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/net/socket.h>
#include <zephyr/ztest.h>

#include <crux/status.h>
#include <crux/time.h>

#include "time_sync.h"

#define LOG_UART DEVICE_DT_GET(DT_NODELABEL(logging_test))

#define NTP_PACKET_BYTES 48
#define NTP_OFFSET_1970 INT64_C(2208988800) /* seconds from 1900-01-01 to 1970-01-01 */
#define NTP_FRACTION_HALF 0x80000000u       /* 0.5 s in units of 2^-32 s */
#define NTP_FRACTION_50_MS 214748365u       /* 0.05 s */

/* 2030-01-01T00:00:00Z */
#define T0 INT64_C(1893456000)
#define NS_PER_SECOND INT64_C(1000000000)

typedef struct {
    int64_t unix_seconds;
    uint32_t fraction;
    bool kiss_of_death;
    uint32_t delay_ms; /* before the answer is sent */
} answer_t;

#define MAX_ANSWERS 4

static struct k_thread responder_thread;
K_THREAD_STACK_DEFINE(responder_stack, 4096);
static int responder_socket = -1;
static answer_t answers[MAX_ANSWERS];
static int answer_count;
static volatile bool responder_stop;
static volatile int requests_seen;
static char captured[4096];

static void put32(uint8_t *at, uint32_t value)
{
    at[0] = (uint8_t)(value >> 24);
    at[1] = (uint8_t)(value >> 16);
    at[2] = (uint8_t)(value >> 8);
    at[3] = (uint8_t)value;
}

/* A server packet: version 3, mode 4, stratum 2 (0 for a kiss-o'-death), the originate time copied
 * from the request's transmit time, and the chosen time as receive and transmit time. */
static void build_reply(uint8_t *reply, const uint8_t *request, const answer_t *answer)
{
    const uint32_t ntp_seconds = (uint32_t)(answer->unix_seconds + NTP_OFFSET_1970);

    memset(reply, 0, NTP_PACKET_BYTES);
    reply[0] = (0u << 6) | (3u << 3) | 4u;
    reply[1] = answer->kiss_of_death ? 0u : 2u;
    memcpy(reply + 24, request + 40, 8);
    put32(reply + 32, ntp_seconds);
    put32(reply + 36, answer->fraction);
    put32(reply + 40, ntp_seconds);
    put32(reply + 44, answer->fraction);
}

static void responder_entry(void *a, void *b, void *c)
{
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    int next = 0;

    while (!responder_stop) {
        struct pollfd wait = {.fd = responder_socket, .events = POLLIN};
        uint8_t request[NTP_PACKET_BYTES];
        struct sockaddr_in from;
        socklen_t from_length = sizeof from;

        if (poll(&wait, 1, 20) <= 0) {
            continue;
        }
        const ssize_t got = recvfrom(responder_socket, request, sizeof request, 0,
                                     (struct sockaddr *)&from, &from_length);

        if (got != NTP_PACKET_BYTES) {
            continue;
        }
        requests_seen++;
        if (next >= answer_count) {
            continue; /* no answer is left: this request goes unanswered */
        }
        const answer_t *answer = &answers[next++];
        uint8_t reply[NTP_PACKET_BYTES];

        for (uint32_t waited = 0; waited < answer->delay_ms && !responder_stop; waited += 10) {
            k_msleep(10);
        }
        build_reply(reply, request, answer);
        (void)sendto(responder_socket, reply, sizeof reply, 0, (struct sockaddr *)&from,
                     from_length);
    }
}

static void start_responder(const answer_t *list, int count)
{
    struct sockaddr_in address;
    const int one = 1;

    zassert_true(count <= MAX_ANSWERS);
    memcpy(answers, list, (size_t)count * sizeof answers[0]);
    answer_count = count;
    responder_stop = false;
    requests_seen = 0;
    memset(&address, 0, sizeof address);
    address.sin_family = AF_INET;
    address.sin_port = htons(123);
    zassert_equal(1, inet_pton(AF_INET, "127.0.0.1", &address.sin_addr));
    responder_socket = socket(AF_INET, SOCK_DGRAM, 0);
    zassert_true(responder_socket >= 0);
    zassert_equal(0, setsockopt(responder_socket, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one));
    zassert_equal(0, bind(responder_socket, (struct sockaddr *)&address, sizeof address));
    k_thread_create(&responder_thread, responder_stack, K_THREAD_STACK_SIZEOF(responder_stack),
                    responder_entry, NULL, NULL, NULL, 5, 0, K_NO_WAIT);
}

static void stop_responder(void)
{
    responder_stop = true;
    zassert_equal(0, k_thread_join(&responder_thread, K_SECONDS(5)));
    /* Zephyr's own call: the POSIX close() is declared in <unistd.h>, which this file does not
     * include, and zsock_close() closes a socket descriptor without it. */
    zassert_equal(0, zsock_close(responder_socket));
    responder_socket = -1;
}

/* Everything that Crux Logging wrote to the emulated UART so far. The log thread has the lowest
 * priority and runs when its sleep period is over (CONFIG_LOG_PROCESS_THREAD_SLEEP_MS, 1000 ms by
 * default) or when enough messages are buffered (CONFIG_LOG_PROCESS_TRIGGER_THRESHOLD, 10 by
 * default). A fixed sleep is therefore not enough: a message that was logged less than a second ago
 * may still be queued. log_flush() wakes the thread and returns when every message is written. */
static const char *log_text(void)
{
    log_flush();
    const size_t length = uart_emul_get_tx_data(LOG_UART, (uint8_t *)captured, sizeof captured - 1);

    captured[length] = '\0';
    return captured;
}

static unsigned int occurrences(const char *text, const char *needle)
{
    unsigned int count = 0;

    for (const char *at = strstr(text, needle); at != NULL; at = strstr(at + 1, needle)) {
        count++;
    }
    return count;
}

static crux_realtime_snapshot_t snapshot(void)
{
    crux_realtime_snapshot_t now = {0};

    zassert_equal(CRUX_OK, crux_realtime_get_snapshot(&now));
    return now;
}

static __maybe_unused int64_t total_ns(crux_realtime_t time)
{
    return time.seconds * NS_PER_SECOND + (int64_t)time.nanoseconds;
}

static void begin(const answer_t *list, int count)
{
    zassert_true(device_is_ready(LOG_UART));
    zassert_equal(0, time_sync_init());
    start_responder(list, count);
    /* Crux Time is ready and unset: nothing has written a time yet. */
    const crux_realtime_snapshot_t before = snapshot();

    zassert_false(before.is_valid);
    zassert_false(before.is_synchronized);
    zassert_equal(CRUX_REALTIME_SOURCE_NONE, before.last_source);
}

ZTEST_SUITE(sntp, NULL, NULL, NULL, NULL, NULL);

#if defined(SNTP_CASE_first_sync)

/* The first answer sets the clock, marks it synchronised and names the source as external. */
ZTEST(sntp, test_the_first_answer_sets_the_clock_synchronised_from_an_external_source)
{
    const answer_t list[] = {{.unix_seconds = T0, .fraction = NTP_FRACTION_HALF}};

    begin(list, 1);
    time_sync_poll();
    const crux_realtime_snapshot_t now = snapshot();

    zassert_true(now.is_valid);
    zassert_true(now.is_synchronized);
    zassert_equal(CRUX_REALTIME_SOURCE_EXTERNAL, now.last_source);
    zassert_true(total_ns(now.timestamp) >= T0 * NS_PER_SECOND + 500000000,
                 "the clock is behind the answer");
    zassert_true(total_ns(now.timestamp) < T0 * NS_PER_SECOND + 600000000,
                 "the clock is far ahead of the answer");
    stop_responder();
    const char *log = log_text();

    zassert_equal(1u, occurrences(log, "time: sync action=apply-set reason=first-sync"), "in: %s",
                  log);
    zassert_equal(1, requests_seen, "the library sent more than one request");
}

#elif defined(SNTP_CASE_kiss_of_death)

/* A kiss-o'-death sets nothing: the clock stays unset and the reason is reported. */
ZTEST(sntp, test_a_kiss_of_death_never_sets_the_clock)
{
    const answer_t list[] = {{.unix_seconds = T0, .fraction = 0u, .kiss_of_death = true}};

    begin(list, 1);
    time_sync_poll();
    const crux_realtime_snapshot_t now = snapshot();

    zassert_false(now.is_valid);
    zassert_false(now.is_synchronized);
    zassert_equal(CRUX_REALTIME_SOURCE_NONE, now.last_source);
    stop_responder();
    const char *log = log_text();

    zassert_equal(1u, occurrences(log, "time: sync action=no-action reason=kiss-of-death"),
                  "in: %s", log);
    zassert_is_null(strstr(log, "apply-set"), "a set was reported in: %s", log);
}

#elif defined(SNTP_CASE_late_answer)

/* An answer that arrives after the timeout sets nothing. The library has closed its socket by
 * then. */
ZTEST(sntp, test_an_answer_after_the_timeout_never_sets_the_clock)
{
    const answer_t list[] = {{.unix_seconds = T0, .fraction = 0u, .delay_ms = 2000}};

    begin(list, 1);
    const int64_t started = k_uptime_get();

    time_sync_poll();
    const int64_t took = k_uptime_get() - started;

    zassert_true(took >= 500 && took < 1900, "the query took %lld ms", (long long)took);
    k_msleep(3000); /* the late answer is sent into the closed socket */
    const crux_realtime_snapshot_t now = snapshot();

    zassert_false(now.is_valid);
    zassert_false(now.is_synchronized);
    stop_responder();
    const char *log = log_text();

    zassert_equal(1u, occurrences(log, "time: sync action=no-action reason=timeout"), "in: %s",
                  log);
    zassert_is_null(strstr(log, "apply-set"), "a set was reported in: %s", log);
}

#elif defined(SNTP_CASE_out_of_range)

/* An answer before 2000-01-01 and one at 2100-01-01 are both refused, and neither sets the
 * clock. */
ZTEST(sntp, test_an_answer_outside_the_supported_range_never_sets_the_clock)
{
    const answer_t list[] = {
        {.unix_seconds = INT64_C(946684799), .fraction = 0u},  /* 1999-12-31T23:59:59Z */
        {.unix_seconds = INT64_C(4102444800), .fraction = 0u}, /* 2100-01-01T00:00:00Z */
    };

    begin(list, 2);
    time_sync_poll();
    zassert_false(snapshot().is_valid);
    time_sync_poll();
    const crux_realtime_snapshot_t now = snapshot();

    zassert_false(now.is_valid);
    zassert_false(now.is_synchronized);
    zassert_equal(CRUX_REALTIME_SOURCE_NONE, now.last_source);
    stop_responder();
    const char *log = log_text();

    zassert_equal(2u, occurrences(log, "time: sync action=refuse-range reason=out-of-range"),
                  "in: %s", log);
    zassert_is_null(strstr(log, "apply-set"), "a set was reported in: %s", log);
}

#elif defined(SNTP_CASE_step_refused_then_resync)

/* A synchronised clock refuses an answer an hour away and loses its synchronisation; the next
 * in-range answer then sets the clock again whatever it says. */
ZTEST(sntp, test_a_large_step_is_refused_once_and_the_next_answer_synchronises_again)
{
    const answer_t list[] = {
        {.unix_seconds = T0, .fraction = 0u},
        {.unix_seconds = T0 + 3600, .fraction = 0u},
        {.unix_seconds = T0 + 3600, .fraction = 0u},
    };

    begin(list, 3);
    time_sync_poll();
    zassert_true(snapshot().is_synchronized);

    time_sync_poll();
    crux_realtime_snapshot_t now = snapshot();

    zassert_true(now.is_valid, "a refused step must not invalidate the time");
    zassert_false(now.is_synchronized, "a refused step must mark synchronisation lost");
    zassert_true(now.timestamp.seconds >= T0 && now.timestamp.seconds < T0 + 5,
                 "the clock moved to %lld", (long long)now.timestamp.seconds);
    zassert_equal(CRUX_REALTIME_SOURCE_EXTERNAL, now.last_source);

    time_sync_poll();
    now = snapshot();
    zassert_true(now.is_valid);
    zassert_true(now.is_synchronized);
    zassert_true(now.timestamp.seconds >= T0 + 3600 && now.timestamp.seconds < T0 + 3600 + 5,
                 "the clock reads %lld", (long long)now.timestamp.seconds);
    stop_responder();
    const char *log = log_text();

    zassert_equal(1u, occurrences(log, "time: sync action=apply-set reason=first-sync"), "in: %s",
                  log);
    zassert_equal(1u, occurrences(log, "time: sync action=refuse-step reason=step-too-large"),
                  "in: %s", log);
    zassert_equal(1u, occurrences(log, "time: sync action=apply-set reason=resync"), "in: %s", log);
}

#elif defined(SNTP_CASE_correction_and_threshold)

/* A difference of about 50 ms from a synchronised clock is left alone; one of about 500 ms is
 * set. */
ZTEST(sntp, test_a_small_difference_is_left_alone_and_a_medium_one_is_corrected)
{
    const answer_t list[] = {
        {.unix_seconds = T0, .fraction = 0u},
        {.unix_seconds = T0, .fraction = NTP_FRACTION_50_MS},
        {.unix_seconds = T0, .fraction = NTP_FRACTION_HALF},
    };

    begin(list, 3);
    time_sync_poll();
    const int64_t first = total_ns(snapshot().timestamp);

    time_sync_poll();
    crux_realtime_snapshot_t now = snapshot();

    zassert_true(now.is_synchronized);
    /* Left alone: the clock only moved on by the little time that passed, not by 50 ms. */
    zassert_true(total_ns(now.timestamp) - first < 40000000,
                 "the clock was set by the small answer");

    time_sync_poll();
    now = snapshot();
    zassert_true(now.is_synchronized);
    zassert_true(total_ns(now.timestamp) >= T0 * NS_PER_SECOND + 500000000, "not corrected");
    zassert_true(total_ns(now.timestamp) < T0 * NS_PER_SECOND + 600000000, "far past the answer");
    stop_responder();
    const char *log = log_text();

    zassert_equal(1u, occurrences(log, "time: sync action=no-action reason=within-threshold"),
                  "in: %s", log);
    zassert_equal(1u, occurrences(log, "time: sync action=apply-set reason=correction"), "in: %s",
                  log);
    zassert_equal(2u, occurrences(log, "action=apply-set"), "in: %s", log);
}

#elif defined(SNTP_CASE_stale_after_silence)

/* A clock that no answer confirms for longer than the stale age is marked not synchronised, once,
 * and stays valid. */
ZTEST(sntp, test_a_synchronised_clock_goes_stale_once_when_no_answer_confirms_it)
{
    const answer_t list[] = {{.unix_seconds = T0, .fraction = 0u}};

    begin(list, 1);
    time_sync_poll();
    zassert_true(snapshot().is_synchronized);

    k_sleep(K_SECONDS(3)); /* the stale age is two seconds in this scenario */
    time_sync_poll();      /* no answer is left: a timeout */
    crux_realtime_snapshot_t now = snapshot();

    zassert_true(now.is_valid, "going stale must not invalidate the time");
    zassert_false(now.is_synchronized);
    zassert_equal(CRUX_REALTIME_SOURCE_EXTERNAL, now.last_source);
    time_sync_poll(); /* another timeout: nothing more to clear */
    now = snapshot();
    zassert_true(now.is_valid);
    zassert_false(now.is_synchronized);
    stop_responder();
    const char *log = log_text();

    zassert_equal(1u, occurrences(log, "time: sync action=mark-stale reason=timeout"), "in: %s",
                  log);
    zassert_equal(1u, occurrences(log, "time: sync action=no-action reason=timeout"), "in: %s",
                  log);
}

#else
#error "SNTP_CASE names no case of this test"
#endif
