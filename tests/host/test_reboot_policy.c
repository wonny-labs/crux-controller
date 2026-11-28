/* SPDX-License-Identifier: Apache-2.0 */

/* The operator reset marker rule for Crux Reboot (specification section 5.1, gap C14; criterion
 * 18) and the withdrawal of a factory reset mark when a restart ends without a reset (section 5.3):
 * plain C with a fake port, no Crux or Zephyr include. */

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "reboot_policy.h"

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

static struct {
    bool reboot_thread;
    bool allowed;
    bool marker;
    int marker_writes;
    int work_calls;
    /* What the fake crux_reboot_work_once() does: ask the policy as Crux does before a reset. */
    bool work_asks_policy;
    /* A job that ends before the second check (a delay or settle wait failure in Crux). */
    bool work_fails_early;
    /* The framework's factory reset mark, withdrawn by request_ended. */
    bool factory_reset_marked;
    int request_ended_calls;
} fake;

static bool on_reboot_thread(void)
{
    return fake.reboot_thread;
}

static bool restart_allowed(void)
{
    return fake.allowed;
}

static void marker_write(bool set)
{
    fake.marker = set;
    fake.marker_writes++;
}

static const reboot_policy_port_t port;

static void request_ended(void)
{
    fake.request_ended_calls++;
    fake.factory_reset_marked = false;
}

static bool work_once(void)
{
    fake.work_calls++;
    if (fake.work_fails_early) {
        return true;
    }
    if (fake.work_asks_policy) {
        /* The second check on the calling thread; the reset "returned", so the call returns. */
        (void)reboot_policy_allow(&port);
        return true;
    }
    return false;
}

static const reboot_policy_port_t port = {on_reboot_thread, restart_allowed, marker_write,
                                          work_once, request_ended};

static void reset(void)
{
    memset(&fake, 0, sizeof fake);
    fake.allowed = true;
}

static void test_an_allowed_check_on_the_reboot_thread_writes_the_marker(void)
{
    reset();
    fake.reboot_thread = true;
    CHECK(reboot_policy_allow(&port));
    CHECK(fake.marker);
    CHECK(fake.marker_writes == 1);
}

static void test_an_allowed_check_on_another_thread_writes_none(void)
{
    reset();
    fake.reboot_thread = false;
    CHECK(reboot_policy_allow(&port));
    CHECK(!fake.marker);
    CHECK(fake.marker_writes == 0);
}

static void test_a_refusal_writes_none(void)
{
    reset();
    fake.allowed = false;
    fake.reboot_thread = true;
    CHECK(!reboot_policy_allow(&port));
    CHECK(fake.marker_writes == 0);
    fake.reboot_thread = false;
    CHECK(!reboot_policy_allow(&port));
    CHECK(fake.marker_writes == 0);
}

static void test_the_reboot_thread_clears_a_marker_when_work_once_returns(void)
{
    reset();
    fake.reboot_thread = true;
    fake.work_asks_policy = true;
    reboot_policy_pass(&port);
    CHECK(fake.work_calls == 1);
    CHECK(!fake.marker);
    CHECK(fake.marker_writes == 2);
}

static void test_a_pass_with_no_request_writes_nothing(void)
{
    reset();
    fake.reboot_thread = true;
    reboot_policy_pass(&port);
    CHECK(fake.work_calls == 1);
    CHECK(fake.marker_writes == 0);
}

/* A factory reset whose restart the second check refuses must not erase at a later plain restart
 * (specification sections 5.3 and 6.2): the pass withdraws the mark. */
static void test_a_refused_second_check_withdraws_the_factory_reset_mark(void)
{
    reset();
    fake.reboot_thread = true;
    fake.work_asks_policy = true;
    fake.allowed = false;
    fake.factory_reset_marked = true;
    reboot_policy_pass(&port);
    CHECK(fake.request_ended_calls == 1);
    CHECK(!fake.factory_reset_marked);
    CHECK(fake.marker_writes == 0);
}

/* Crux ends a job as failed before the second check when its delay or settle wait fails. */
static void test_a_job_that_fails_before_the_second_check_withdraws_the_mark(void)
{
    reset();
    fake.reboot_thread = true;
    fake.work_fails_early = true;
    fake.factory_reset_marked = true;
    reboot_policy_pass(&port);
    CHECK(fake.request_ended_calls == 1);
    CHECK(!fake.factory_reset_marked);
    CHECK(fake.marker_writes == 0);
}

/* A reset that returned is a restart that did not happen either. */
static void test_a_reset_that_returned_ends_the_request(void)
{
    reset();
    fake.reboot_thread = true;
    fake.work_asks_policy = true;
    reboot_policy_pass(&port);
    CHECK(fake.request_ended_calls == 1);
    CHECK(!fake.marker);
}

/* A pass that carried out nothing keeps the mark of a request posted just before the pass ends. */
static void test_an_idle_pass_keeps_the_factory_reset_mark(void)
{
    reset();
    fake.reboot_thread = true;
    fake.factory_reset_marked = true;
    reboot_policy_pass(&port);
    reboot_policy_pass(&port);
    CHECK(fake.work_calls == 2);
    CHECK(fake.request_ended_calls == 0);
    CHECK(fake.factory_reset_marked);
}

static void test_an_incomplete_port_refuses(void)
{
    const reboot_policy_port_t none = {NULL, NULL, NULL, NULL, NULL};
    const reboot_policy_port_t no_end = {on_reboot_thread, restart_allowed, marker_write, work_once,
                                         NULL};

    reset();
    CHECK(!reboot_policy_allow(NULL));
    CHECK(!reboot_policy_allow(&none));
    CHECK(!reboot_policy_allow(&no_end));
    reboot_policy_pass(NULL);
    reboot_policy_pass(&none);
    reboot_policy_pass(&no_end);
    CHECK(fake.marker_writes == 0);
    CHECK(fake.work_calls == 0);
}

int main(void)
{
    test_an_allowed_check_on_the_reboot_thread_writes_the_marker();
    test_an_allowed_check_on_another_thread_writes_none();
    test_a_refusal_writes_none();
    test_the_reboot_thread_clears_a_marker_when_work_once_returns();
    test_a_pass_with_no_request_writes_nothing();
    test_a_refused_second_check_withdraws_the_factory_reset_mark();
    test_a_job_that_fails_before_the_second_check_withdraws_the_mark();
    test_a_reset_that_returned_ends_the_request();
    test_an_idle_pass_keeps_the_factory_reset_mark();
    test_an_incomplete_port_refuses();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
