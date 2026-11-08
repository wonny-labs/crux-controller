/* SPDX-License-Identifier: Apache-2.0 */

/* Runs the application's own net_client.c over Zephyr's loopback interface, against a peer
 * thread of this test with one behaviour per case. The peer uses listener calls that are
 * outside the client profile. That is allowed in a test, and it is why this is test code. */

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include "net_client.h"
#include "workload.h"

typedef enum { PEER_ECHO, PEER_WRONG_REPLY, PEER_EARLY_CLOSE } peer_mode_t;

static struct k_thread peer_thread;
K_THREAD_STACK_DEFINE(peer_stack, 4096);
static int listener;
static peer_mode_t mode;

static void peer_entry(void *a, void *b, void *c)
{
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    uint8_t data[WORKLOAD_MESSAGE_SIZE];
    size_t got = 0;
    const int client = accept(listener, NULL, NULL);

    if (client < 0) {
        return;
    }
    while (got < sizeof data) {
        const ssize_t count = recv(client, data + got, sizeof data - got, 0);

        if (count <= 0) {
            break;
        }
        got += (size_t)count;
    }
    if (mode == PEER_WRONG_REPLY) {
        data[0] ^= 0xFF;
    }
    if (mode != PEER_EARLY_CLOSE) {
        (void)send(client, data, got, 0);
    }
    close(client);
}

static void open_listener(void)
{
    struct sockaddr_in address;

    memset(&address, 0, sizeof address);
    address.sin_family = AF_INET;
    address.sin_port = htons(CONFIG_CRUX_CONTROLLER_PEER_PORT);
    zassert_equal(1, inet_pton(AF_INET, CONFIG_CRUX_CONTROLLER_PEER_ADDRESS, &address.sin_addr));
    const int one = 1;

    listener = socket(AF_INET, SOCK_STREAM, 0);
    zassert_true(listener >= 0);
    /* The previous case's connection may still hold the port in a closing state. */
    zassert_equal(0, setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one));
    zassert_equal(0, bind(listener, (struct sockaddr *)&address, sizeof address));
    zassert_equal(0, listen(listener, 1));
}

static int exchange_with(peer_mode_t peer_mode)
{
    const workload_message_t message = {.cycle = 7, .value = 0xA1B2C3D4u};
    int result;

    mode = peer_mode;
    open_listener();
    k_thread_create(&peer_thread, peer_stack, K_THREAD_STACK_SIZEOF(peer_stack), peer_entry, NULL,
                    NULL, NULL, 5, 0, K_NO_WAIT);
    result = net_client_exchange(&message);
    zassert_equal(0, k_thread_join(&peer_thread, K_SECONDS(5)));
    close(listener);
    return result;
}

ZTEST(s2, test_the_exchange_succeeds_against_an_echoing_peer)
{
    zassert_equal(NET_CLIENT_OK, exchange_with(PEER_ECHO));
}

ZTEST(s2, test_a_wrong_reply_is_a_protocol_error)
{
    zassert_equal(NET_CLIENT_ERR_PROTOCOL, exchange_with(PEER_WRONG_REPLY));
}

ZTEST(s2, test_an_early_close_is_a_receive_error)
{
    zassert_equal(NET_CLIENT_ERR_RECEIVE, exchange_with(PEER_EARLY_CLOSE));
}

ZTEST(s2, test_no_listener_is_a_connect_error)
{
    const workload_message_t message = {.cycle = 1, .value = 2};

    zassert_equal(NET_CLIENT_ERR_CONNECT, net_client_exchange(&message));
}

/* The number of open descriptors before and after a case. A descriptor that net_client.c
 * leaves open raises the second number, whichever path the exchange took. Counting is not
 * the same as looking for the lowest free slot: the test's own listener takes the lowest
 * slot first, so a leaked client descriptor would sit above it and go unseen. */
#define DESCRIPTOR_SCAN_LIMIT 64

static int baseline_descriptors;

static int open_descriptors(void)
{
    int count = 0;

    for (int descriptor = 0; descriptor < DESCRIPTOR_SCAN_LIMIT; descriptor++) {
        if (fcntl(descriptor, F_GETFL) >= 0) {
            count++;
        }
    }
    return count;
}

static void before_each(void *fixture)
{
    ARG_UNUSED(fixture);
    baseline_descriptors = open_descriptors();
}

static void after_each(void *fixture)
{
    ARG_UNUSED(fixture);
    zassert_equal(baseline_descriptors, open_descriptors(), "the case left a descriptor open");
}

ZTEST_SUITE(s2, NULL, NULL, before_each, after_each, NULL);
