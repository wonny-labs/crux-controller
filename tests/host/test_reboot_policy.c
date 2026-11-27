/* SPDX-License-Identifier: Apache-2.0 */

/* The operator reset marker rule for Crux Reboot (specification section 5.1, gap C14; criterion
 * 18): plain C with a fake port, no Crux or Zephyr include. */

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

static bool work_once(void)
{
    fake.work_calls++;
    if (fake.work_asks_policy) {
        /* The second check on the calling thread; the reset "returned", so the call returns. */
        (void)reboot_policy_allow(&port);
        return true;
    }
    return false;
}

static const reboot_policy_port_t port = {on_reboot_thread, restart_allowed, marker_write,
                                          work_once};

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

static void test_an_incomplete_port_refuses(void)
{
    const reboot_policy_port_t none = {NULL, NULL, NULL, NULL};

    reset();
    CHECK(!reboot_policy_allow(NULL));
    CHECK(!reboot_policy_allow(&none));
    reboot_policy_pass(NULL);
    reboot_policy_pass(&none);
    CHECK(fake.marker_writes == 0);
}

int main(void)
{
    test_an_allowed_check_on_the_reboot_thread_writes_the_marker();
    test_an_allowed_check_on_another_thread_writes_none();
    test_a_refusal_writes_none();
    test_the_reboot_thread_clears_a_marker_when_work_once_returns();
    test_a_pass_with_no_request_writes_nothing();
    test_an_incomplete_port_refuses();
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
