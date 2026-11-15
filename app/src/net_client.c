/* SPDX-License-Identifier: Apache-2.0 */

#include "net_client.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

enum { DEADLINE_MS = 2000 };

/* The socket of one exchange and the deadline of the whole exchange. They travel together so that
 * every wait is measured against the same deadline and a call cannot mix up its numeric arguments.
 */
struct exchange_link {
    int descriptor;
    int64_t deadline_ms;
};

static int64_t monotonic_ms(void)
{
    struct timespec now;

    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        return -1;
    }
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

/* Wait until the descriptor is ready for the events, or the overall deadline passes. Poll
 * only says that an operation can be tried. An error or hang-up is left to that operation. */
static int wait_ready(const struct exchange_link *link, short events)
{
    for (;;) {
        const int64_t now = monotonic_ms();

        if (now < 0 || now >= link->deadline_ms) {
            return NET_CLIENT_ERR_TIMEOUT;
        }
        struct pollfd entry = {.fd = link->descriptor, .events = events, .revents = 0};
        const int ready = poll(&entry, 1, (int)(link->deadline_ms - now));

        if (ready > 0) {
            return NET_CLIENT_OK;
        }
        if (ready < 0 && errno != EINTR) {
            return NET_CLIENT_ERR_SOCKET;
        }
    }
}

static int connect_peer(const struct exchange_link *link)
{
    struct sockaddr_in peer;

    memset(&peer, 0, sizeof peer);
    peer.sin_family = AF_INET;
    peer.sin_port = htons(CONFIG_CRUX_CONTROLLER_PEER_PORT);
    if (inet_pton(AF_INET, CONFIG_CRUX_CONTROLLER_PEER_ADDRESS, &peer.sin_addr) != 1) {
        return NET_CLIENT_ERR_SOCKET;
    }
    if (connect(link->descriptor, (const struct sockaddr *)&peer, sizeof peer) == 0) {
        return NET_CLIENT_OK;
    }
    if (errno != EINPROGRESS) {
        return NET_CLIENT_ERR_CONNECT;
    }
    const int ready = wait_ready(link, POLLOUT);

    if (ready != NET_CLIENT_OK) {
        return ready;
    }
    int outcome = 0;
    socklen_t length = sizeof outcome;

    if (getsockopt(link->descriptor, SOL_SOCKET, SO_ERROR, &outcome, &length) != 0 ||
        outcome != 0) {
        return NET_CLIENT_ERR_CONNECT;
    }
    return NET_CLIENT_OK;
}

static int send_all(const struct exchange_link *link, const uint8_t *data, size_t length)
{
    size_t sent = 0;

    while (sent < length) {
        const int ready = wait_ready(link, POLLOUT);

        if (ready != NET_CLIENT_OK) {
            return ready;
        }
        const ssize_t count = send(link->descriptor, data + sent, length - sent, 0);

        if (count > 0) {
            sent += (size_t)count;
        } else if (count < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
            return NET_CLIENT_ERR_SEND;
        }
    }
    return NET_CLIENT_OK;
}

static int receive_all(const struct exchange_link *link, uint8_t *data, size_t length)
{
    size_t received = 0;

    while (received < length) {
        const int ready = wait_ready(link, POLLIN);

        if (ready != NET_CLIENT_OK) {
            return ready;
        }
        const ssize_t count = recv(link->descriptor, data + received, length - received, 0);

        if (count > 0) {
            received += (size_t)count;
        } else if (count == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) {
            /* The peer closed early, or the receive failed. errno is read only when count < 0. */
            return NET_CLIENT_ERR_RECEIVE;
        }
    }
    return NET_CLIENT_OK;
}

int net_client_exchange(const workload_message_t *message)
{
    uint8_t request[WORKLOAD_MESSAGE_SIZE];
    uint8_t reply[WORKLOAD_MESSAGE_SIZE];
    size_t length = 0;

    if (workload_message_encode(message, request, sizeof request, &length) != WORKLOAD_OK) {
        return NET_CLIENT_ERR_PROTOCOL;
    }
    const int64_t start = monotonic_ms();

    if (start < 0) {
        return NET_CLIENT_ERR_TIMEOUT;
    }
    const struct exchange_link link = {
        .descriptor = socket(AF_INET, SOCK_STREAM, 0),
        .deadline_ms = start + DEADLINE_MS,
    };

    if (link.descriptor < 0) {
        return NET_CLIENT_ERR_SOCKET;
    }
    int result = NET_CLIENT_ERR_SOCKET;
    const int flags = fcntl(link.descriptor, F_GETFL);

    if (flags >= 0 && fcntl(link.descriptor, F_SETFL, flags | O_NONBLOCK) == 0) {
        result = connect_peer(&link);
        if (result == NET_CLIENT_OK) {
            result = send_all(&link, request, length);
        }
        if (result == NET_CLIENT_OK) {
            result = receive_all(&link, reply, sizeof reply);
        }
        if (result == NET_CLIENT_OK && memcmp(request, reply, sizeof request) != 0) {
            result = NET_CLIENT_ERR_PROTOCOL;
        }
    }
    /* Close once. A failure here does not change the outcome of the exchange. */
    (void)close(link.descriptor);
    return result;
}
