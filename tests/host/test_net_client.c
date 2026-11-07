/* SPDX-License-Identifier: Apache-2.0 */

/* Runs the application's own net_client.c against a peer on the loopback interface. The
 * peer is a thread of this test with one behaviour per case. This tests the exchange logic
 * and its error paths on the host. It says nothing about the Zephyr network stack. */

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "net_client.h"
#include "workload.h"

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

typedef enum {
    PEER_ECHO,
    PEER_EARLY_CLOSE,
    PEER_WRONG_REPLY,
    PEER_SILENT,
    PEER_SHORT_WRITES,
} peer_mode_t;

typedef struct {
    int listener;
    peer_mode_t mode;
} peer_t;

static int open_listener(void)
{
    struct sockaddr_in address;
    const int one = 1;
    const int listener = socket(AF_INET, SOCK_STREAM, 0);

    memset(&address, 0, sizeof address);
    address.sin_family = AF_INET;
    address.sin_port = htons(CONFIG_CRUX_CONTROLLER_PEER_PORT);
    inet_pton(AF_INET, CONFIG_CRUX_CONTROLLER_PEER_ADDRESS, &address.sin_addr);
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    if (bind(listener, (struct sockaddr *)&address, sizeof address) != 0 ||
        listen(listener, 1) != 0) {
        printf("cannot listen on the test port: %s\n", strerror(errno));
        return -1;
    }
    return listener;
}

static void *peer_main(void *argument)
{
    peer_t *peer = argument;
    const int client = accept(peer->listener, NULL, NULL);
    uint8_t data[WORKLOAD_MESSAGE_SIZE];
    size_t got = 0;

    if (client < 0) {
        return NULL;
    }
    while (got < sizeof data) {
        const ssize_t count = recv(client, data + got, sizeof data - got, 0);

        if (count <= 0) {
            break;
        }
        got += (size_t)count;
    }
    switch (peer->mode) {
    case PEER_ECHO:
        (void)send(client, data, got, 0);
        break;
    case PEER_WRONG_REPLY:
        data[0] ^= 0xFF;
        (void)send(client, data, got, 0);
        break;
    case PEER_SHORT_WRITES:
        for (size_t i = 0; i < got; i++) {
            (void)send(client, data + i, 1, 0);
            usleep(20000);
        }
        break;
    case PEER_SILENT:
        usleep(2600000); /* longer than the client's deadline */
        break;
    case PEER_EARLY_CLOSE:
        break;
    }
    close(client);
    return NULL;
}

static int exchange_with(peer_mode_t mode)
{
    const workload_message_t message = {.cycle = 7, .value = 0xA1B2C3D4u};
    peer_t peer = {.listener = open_listener(), .mode = mode};
    pthread_t thread;
    int result = -100;

    if (peer.listener < 0) {
        failures++;
        return result;
    }
    pthread_create(&thread, NULL, peer_main, &peer);
    result = net_client_exchange(&message);
    pthread_join(thread, NULL);
    close(peer.listener);
    return result;
}

int main(void)
{
    CHECK(exchange_with(PEER_ECHO) == NET_CLIENT_OK);
    CHECK(exchange_with(PEER_SHORT_WRITES) == NET_CLIENT_OK);
    CHECK(exchange_with(PEER_WRONG_REPLY) == NET_CLIENT_ERR_PROTOCOL);
    CHECK(exchange_with(PEER_EARLY_CLOSE) == NET_CLIENT_ERR_RECEIVE);
    CHECK(exchange_with(PEER_SILENT) == NET_CLIENT_ERR_TIMEOUT);

    /* No listener: the connection is refused. */
    {
        const workload_message_t message = {.cycle = 1, .value = 2};

        CHECK(net_client_exchange(&message) == NET_CLIENT_ERR_CONNECT);
        CHECK(net_client_exchange(NULL) == NET_CLIENT_ERR_PROTOCOL);
    }
    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
