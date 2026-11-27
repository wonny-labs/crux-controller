/* SPDX-License-Identifier: Apache-2.0 */

#include "https.h"

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>

/* The listener opens on Zephyr's own thread, so the first connects can be refused. */
#define CONNECT_ATTEMPTS 40
#define CONNECT_RETRY_MS 100
#define READ_WAIT_MS 3000
#define POLLS 50
#define POLL_MS 100

static int connect_tls(void)
{
    struct net_sockaddr_in address = {
        .sin_family = NET_AF_INET,
        .sin_port = net_htons(CONFIG_CRUX_WEB_PORT),
    };
    const int none = ZSOCK_TLS_PEER_VERIFY_NONE;

    if (zsock_inet_pton(NET_AF_INET, "127.0.0.1", &address.sin_addr) != 1) {
        return -1;
    }
    for (int attempt = 0; attempt < CONNECT_ATTEMPTS; attempt++) {
        const int sock = zsock_socket(NET_AF_INET, NET_SOCK_STREAM, NET_IPPROTO_TLS_1_3);

        if (sock < 0) {
            return -1;
        }
        if (zsock_setsockopt(sock, ZSOCK_SOL_TLS, ZSOCK_TLS_PEER_VERIFY, &none, sizeof none) == 0 &&
            zsock_setsockopt(sock, ZSOCK_SOL_TLS, ZSOCK_TLS_HOSTNAME, HTTPS_HOST,
                             sizeof HTTPS_HOST) == 0 &&
            zsock_connect(sock, (const struct net_sockaddr *)&address, sizeof address) == 0) {
            return sock;
        }
        (void)zsock_close(sock);
        k_msleep(CONNECT_RETRY_MS);
    }
    return -1;
}

static size_t read_until_quiet(int sock, char *buffer, size_t capacity)
{
    size_t used = 0;

    while (used + 1u < capacity) {
        struct zsock_pollfd wait = {.fd = sock, .events = ZSOCK_POLLIN};

        if (zsock_poll(&wait, 1, READ_WAIT_MS) <= 0) {
            break;
        }
        const ssize_t got = zsock_recv(sock, buffer + used, capacity - 1u - used, 0);

        if (got <= 0) {
            break;
        }
        used += (size_t)got;
    }
    buffer[used] = '\0';
    return used;
}

int https_request(const char *method, const char *path, const char *extra_headers, const char *body,
                  char *response, size_t capacity)
{
    char request[1024];
    const size_t body_length = body != NULL ? strlen(body) : 0u;
    const int length = snprintf(request, sizeof request,
                                "%s %s HTTP/1.1\r\nHost: " HTTPS_HOST "\r\n%s"
                                "Content-Length: %u\r\nConnection: close\r\n\r\n%s",
                                method, path, extra_headers != NULL ? extra_headers : "",
                                (unsigned)body_length, body != NULL ? body : "");

    if (length <= 0 || (size_t)length >= sizeof request || capacity < 16u) {
        return -1;
    }
    const int sock = connect_tls();

    if (sock < 0) {
        return -1;
    }
    for (size_t sent = 0; sent < (size_t)length;) {
        const ssize_t wrote = zsock_send(sock, request + sent, (size_t)length - sent, 0);

        if (wrote <= 0) {
            (void)zsock_close(sock);
            return -1;
        }
        sent += (size_t)wrote;
    }
    const size_t got = read_until_quiet(sock, response, capacity);

    (void)zsock_close(sock);
    if (got < 12u || strncmp(response, "HTTP/1.1 ", 9) != 0) {
        return -1;
    }
    return atoi(&response[9]);
}

/* Append the name=value of every Set-Cookie line of the answer to the Cookie header. */
static int collect_cookies(const char *response, char *cookie, size_t capacity)
{
    size_t used = (size_t)snprintf(cookie, capacity, "Cookie: ");
    int found = 0;

    for (const char *line = strstr(response, "Set-Cookie: "); line != NULL;
         line = strstr(line + 1, "Set-Cookie: ")) {
        const char *value = line + strlen("Set-Cookie: ");
        const size_t length = strcspn(value, ";\r\n");

        if (used + length + 3u >= capacity) {
            return -1;
        }
        used += (size_t)snprintf(&cookie[used], capacity - used, "%s%.*s", found > 0 ? "; " : "",
                                 (int)length, value);
        found++;
    }
    if (found == 0 || used + 3u >= capacity) {
        return -1;
    }
    (void)snprintf(&cookie[used], capacity - used, "\r\n");
    return 0;
}

int https_login(const char *user, const char *password, char *cookie, size_t capacity)
{
    static char response[4096];
    char body[160];
    char path[160];
    char id[80];

    (void)snprintf(body, sizeof body, "{\"user\":\"%s\",\"password\":\"%s\"}", user, password);
    if (https_request("POST", "/api/v1/session",
                      "Origin: https://" HTTPS_HOST "\r\nContent-Type: application/json\r\n", body,
                      response, sizeof response) != 202) {
        return -1;
    }
    const char *start = strstr(response, "{\"id\":\"");

    if (start == NULL) {
        return -1;
    }
    start += strlen("{\"id\":\"");
    const size_t length = strcspn(start, "\"");

    if (length == 0u || length >= sizeof id) {
        return -1;
    }
    memcpy(id, start, length);
    id[length] = '\0';
    (void)snprintf(path, sizeof path, "/api/v1/session/attempt/%s", id);
    for (int poll = 0; poll < POLLS; poll++) {
        if (https_request("GET", path, "X-Crux-Request: 1\r\n", NULL, response, sizeof response) !=
            200) {
            return -1;
        }
        if (strstr(response, "\"state\":\"pending\"") == NULL) {
            return collect_cookies(response, cookie, capacity);
        }
        k_msleep(POLL_MS);
    }
    return -1;
}
