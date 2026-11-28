/* SPDX-License-Identifier: Apache-2.0 */

/* Supervision of the Crux service threads by their progress reports (specification sections 4.3
 * and 4.4, gap C8; criterion 33, host part), against a fake channel port. Plain C, no Crux or
 * Zephyr include. Also run with several reporting threads at once, because Crux calls the progress
 * function on each service thread, possibly at the same time.
 */

#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "service_progress.h"

static int failures;
static int checks;

#define CHECK(condition)                                                                           \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(condition)) {                                                                        \
            failures++;                                                                            \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                            \
        }                                                                                          \
    } while (0)

#define HANDLES 8

/* --- the fake channel port --- */

static struct {
    int next_handle;
    bool refuse;
    int adds;
    const char *names[HANDLES];
    uint32_t reloads[HANDLES];
    atomic_int feeds[HANDLES];
} fake;

static int fake_add(const char *name, uint32_t reload_ms)
{
    fake.adds++;
    if (fake.refuse || fake.next_handle >= HANDLES) {
        return -1;
    }
    const int handle = fake.next_handle++;

    fake.names[handle] = name;
    fake.reloads[handle] = reload_ms;
    return handle;
}

static void fake_feed(int handle)
{
    if (handle >= 0 && handle < HANDLES) {
        (void)atomic_fetch_add(&fake.feeds[handle], 1);
    }
}

static const char *silenced;

static bool fake_silenced(const char *name)
{
    return silenced != NULL && name != NULL && strcmp(name, silenced) == 0;
}

static const service_progress_port_t port = {fake_add, fake_feed, fake_silenced};

static void reset(void)
{
    memset(&fake, 0, sizeof fake);
    for (int handle = 0; handle < HANDLES; handle++) {
        atomic_init(&fake.feeds[handle], 0);
    }
    silenced = NULL;
    service_progress_init(&port, 20000u);
}

static int total_feeds(void)
{
    int total = 0;

    for (int handle = 0; handle < HANDLES; handle++) {
        total += atomic_load(&fake.feeds[handle]);
    }
    return total;
}

/* A thread that is not started has no active channel, and its reports feed nothing. */
static void test_a_thread_that_is_not_started_has_no_channel(void)
{
    reset();
    for (int thread = 0; thread < SERVICE_THREAD_COUNT; thread++) {
        CHECK(!service_progress_active((service_thread_t)thread));
        service_progress_report((service_thread_t)thread);
    }
    CHECK(fake.adds == 0);
    CHECK(total_feeds() == 0);
}

/* Activation adds one channel with the thread's name and the reload period; reports of that thread
 * feed it, and reports of other threads do not. */
static void test_activation_adds_one_channel_and_reports_feed_it(void)
{
    reset();
    CHECK(service_progress_activate(SERVICE_THREAD_WEB_SESSION) == 0);
    CHECK(service_progress_active(SERVICE_THREAD_WEB_SESSION));
    CHECK(!service_progress_active(SERVICE_THREAD_CONSOLE));
    CHECK(fake.adds == 1);
    CHECK(strcmp(fake.names[0], "web session") == 0);
    CHECK(fake.reloads[0] == 20000u);
    service_progress_report(SERVICE_THREAD_WEB_SESSION);
    service_progress_report(SERVICE_THREAD_WEB_SESSION);
    service_progress_report(SERVICE_THREAD_CONSOLE);
    CHECK(atomic_load(&fake.feeds[0]) == 2);
    CHECK(total_feeds() == 2);
}

/* A second activation of the same thread adds no second channel. */
static void test_a_second_activation_changes_nothing(void)
{
    reset();
    CHECK(service_progress_activate(SERVICE_THREAD_CONSOLE) == 0);
    CHECK(service_progress_activate(SERVICE_THREAD_CONSOLE) == SERVICE_PROGRESS_ERR_ACTIVE);
    CHECK(fake.adds == 1);
}

/* A refused channel leaves the thread without a channel, and its reports feed nothing. */
static void test_a_refused_channel_leaves_the_thread_inactive(void)
{
    reset();
    fake.refuse = true;
    CHECK(service_progress_activate(SERVICE_THREAD_EVENT_DRAIN) == SERVICE_PROGRESS_ERR_FULL);
    CHECK(!service_progress_active(SERVICE_THREAD_EVENT_DRAIN));
    service_progress_report(SERVICE_THREAD_EVENT_DRAIN);
    CHECK(total_feeds() == 0);
}

/* Unknown identifiers are refused or ignored, and nothing activates before init. */
static void test_unknown_threads_and_no_init(void)
{
    reset();
    CHECK(service_progress_activate(SERVICE_THREAD_COUNT) == SERVICE_PROGRESS_ERR_ARGUMENT);
    CHECK(service_progress_activate((service_thread_t)-1) == SERVICE_PROGRESS_ERR_ARGUMENT);
    service_progress_report(SERVICE_THREAD_COUNT);
    service_progress_report((service_thread_t)-1);
    CHECK(!service_progress_active(SERVICE_THREAD_COUNT));
    CHECK(fake.adds == 0);
    service_progress_init(NULL, 20000u);
    CHECK(service_progress_activate(SERVICE_THREAD_CONSOLE) == SERVICE_PROGRESS_ERR_ARGUMENT);
    service_progress_init(&port, 0u);
    CHECK(service_progress_activate(SERVICE_THREAD_CONSOLE) == SERVICE_PROGRESS_ERR_ARGUMENT);
    CHECK(fake.adds == 0);
}

/* A thread injected silent (scenario fault injection) stops feeding its channel, so it expires; the
 * other threads keep feeding theirs. */
static void test_a_silenced_thread_stops_feeding(void)
{
    reset();
    CHECK(service_progress_activate(SERVICE_THREAD_WEB_MANAGEMENT) == 0);
    CHECK(service_progress_activate(SERVICE_THREAD_CONSOLE) == 1);
    silenced = "web management";
    service_progress_report(SERVICE_THREAD_WEB_MANAGEMENT);
    service_progress_report(SERVICE_THREAD_CONSOLE);
    CHECK(atomic_load(&fake.feeds[0]) == 0);
    CHECK(atomic_load(&fake.feeds[1]) == 1);
}

/* Every thread has a distinct, stable name, which the channel and the fault injection use. */
static void test_names(void)
{
    CHECK(strcmp(service_progress_name(SERVICE_THREAD_EVENT_DRAIN), "event drain") == 0);
    CHECK(strcmp(service_progress_name(SERVICE_THREAD_WEB_SESSION), "web session") == 0);
    CHECK(strcmp(service_progress_name(SERVICE_THREAD_WEB_MANAGEMENT), "web management") == 0);
    CHECK(strcmp(service_progress_name(SERVICE_THREAD_CONSOLE), "console") == 0);
    CHECK(service_progress_name(SERVICE_THREAD_COUNT) == NULL);
}

/* Reports from several threads at once: every report feeds its own thread's channel, none feeds
 * another's, and no feed is lost. */
#define REPORTS 20000

static atomic_bool go;

static void *reporter(void *argument)
{
    const service_thread_t thread = *(const service_thread_t *)argument;

    while (!atomic_load(&go)) {
    }
    for (int index = 0; index < REPORTS; index++) {
        service_progress_report(thread);
    }
    return NULL;
}

static void test_concurrent_reports(void)
{
    static const service_thread_t threads[] = {
        SERVICE_THREAD_EVENT_DRAIN, SERVICE_THREAD_WEB_SESSION, SERVICE_THREAD_WEB_MANAGEMENT,
        SERVICE_THREAD_CONSOLE};
    pthread_t ids[4];

    reset();
    atomic_store(&go, false);
    for (size_t index = 0; index < 4u; index++) {
        CHECK(service_progress_activate(threads[index]) == (int)index);
        CHECK(pthread_create(&ids[index], NULL, reporter, (void *)&threads[index]) == 0);
    }
    atomic_store(&go, true);
    for (size_t index = 0; index < 4u; index++) {
        CHECK(pthread_join(ids[index], NULL) == 0);
    }
    for (int handle = 0; handle < 4; handle++) {
        CHECK(atomic_load(&fake.feeds[handle]) == REPORTS);
    }
}

int main(void)
{
    test_a_thread_that_is_not_started_has_no_channel();
    test_activation_adds_one_channel_and_reports_feed_it();
    test_a_second_activation_changes_nothing();
    test_a_refused_channel_leaves_the_thread_inactive();
    test_unknown_threads_and_no_init();
    test_a_silenced_thread_stops_feeding();
    test_names();
    test_concurrent_reports();
    printf("service_progress: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
