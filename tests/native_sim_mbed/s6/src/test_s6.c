/* SPDX-License-Identifier: Apache-2.0 */

/* Runs the product's own start sequence for HTTPS management (app/compose/management_start.c,
 * through the port of app/src/management_port.h), its route wiring and its packaged page, on the
 * real Crux services and Zephyr's HTTP server with Mbed TLS, in one native_sim image. A TLS client
 * of this test, in the same process, connects to the listener over Zephyr's loopback interface and
 * verifies the server with the certificate that the product registered.
 *
 * One image runs all cases in order, because the start sequence runs once per program: Crux's init
 * calls cannot be repeated, and a case that needs the running server cannot restart it. The first
 * three cases are the ones that matter most: the start sequence returns OK, the generated
 * certificate is in Zephyr's credential store, and a TLS 1.3 handshake with peer verification
 * required completes and the server answers a request for the page. Every case after them is a
 * request over a new connection.
 *
 * What this scenario cannot show: a successful login, any 200 from an API route, roles, a password
 * change, the first account (a later change makes it, from the serial console), a configuration
 * save, handshake time, stack use, heap peaks (the heap here is larger than the product's), the
 * strength of any key (the entropy is the simulator's fake entropy, a test source), the libc of the
 * target (the libc here is the one that prj.conf names, and the web start checks fnmatch() on it),
 * the page in a browser (no browser ran), Ethernet, the address 192.168.77.2, or anything on a
 * board. Zephyr's TLS sockets treat the version as a minimum, so the refusal of a client that can
 * only speak TLS 1.2 is shown with a client whose one cipher suite is a TLS 1.2 suite. */

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/tls_credentials.h>
#include <zephyr/ztest.h>

#include "management_port.h"

#define LOG_UART DEVICE_DT_GET(DT_NODELABEL(logging_test))

/* The trust anchor of the client: the product's certificate, added as a CA under another tag. */
#define CLIENT_CA_TAG 2
/* A name in the certificate, so that the hostname check passes. */
#define SERVER_NAME "crux-controller"
/* The listener opens on Zephyr's own thread, so the first connects can be refused. */
#define CONNECT_ATTEMPTS 40
#define CONNECT_RETRY_MS 100
#define READ_WAIT_MS 3000
/* IANA numbers of the cipher suites: the TLS 1.3 suite of the profile, and a TLS 1.2 one. */
#define SUITE_TLS13_AES_128_GCM_SHA256 0x1301
#define SUITE_TLS12_ECDHE_ECDSA_AES_128_GCM_SHA256 0xC02B

#define RESPONSE_CAPACITY 8192u

static char log_text[8192];
static size_t log_length;
static uint8_t trust_anchor[4096];
static char response[RESPONSE_CAPACITY];
static char attempt_id[80];

/* Everything that Crux Logging wrote since the last call, appended to what was read before.
 * log_flush() wakes the log thread and returns when every message is written. */
static const char *drain_log(void)
{
    log_flush();
    log_length += uart_emul_get_tx_data(LOG_UART, (uint8_t *)log_text + log_length,
                                        sizeof log_text - 1u - log_length);
    log_text[log_length] = '\0';
    return log_text;
}

/* A search that does not stop at a NUL, because a packaged page can be compressed. */
static bool contains(const char *haystack, size_t length, const char *needle)
{
    const size_t size = strlen(needle);

    for (size_t at = 0; at + size <= length; at++) {
        if (memcmp(haystack + at, needle, size) == 0) {
            return true;
        }
    }
    return false;
}

static bool starts_with(const char *text, size_t length, const char *prefix)
{
    const size_t size = strlen(prefix);

    return length >= size && memcmp(text, prefix, size) == 0;
}

static struct net_sockaddr_in loopback_address(void)
{
    struct net_sockaddr_in address = {
        .sin_family = NET_AF_INET,
        .sin_port = net_htons(CONFIG_CRUX_WEB_PORT),
    };

    zassert_equal(zsock_inet_pton(NET_AF_INET, "127.0.0.1", &address.sin_addr), 1);
    return address;
}

static bool configure_tls(int sock, const char *name)
{
    sec_tag_t tags[] = {CLIENT_CA_TAG};
    int required = ZSOCK_TLS_PEER_VERIFY_REQUIRED;

    return zsock_setsockopt(sock, ZSOCK_SOL_TLS, ZSOCK_TLS_SEC_TAG_LIST, tags, sizeof tags) == 0 &&
           zsock_setsockopt(sock, ZSOCK_SOL_TLS, ZSOCK_TLS_PEER_VERIFY, &required,
                            sizeof required) == 0 &&
           zsock_setsockopt(sock, ZSOCK_SOL_TLS, ZSOCK_TLS_HOSTNAME, name, strlen(name) + 1u) == 0;
}

/* Open a TLS socket of the given protocol, optionally restricted to one cipher suite, and connect
 * it to the listener, retrying while the listener is not open yet. The connect of a TLS socket
 * runs the handshake. Returns the socket, or -1 when no attempt connected. */
static int connect_tls(int protocol, int only_suite, int attempts)
{
    const struct net_sockaddr_in address = loopback_address();

    for (int attempt = 0; attempt < attempts; attempt++) {
        int sock = zsock_socket(NET_AF_INET, NET_SOCK_STREAM, protocol);

        zassert_true(sock >= 0, "no socket (errno %d)", errno);
        zassert_true(configure_tls(sock, SERVER_NAME), "TLS options refused (errno %d)", errno);
        if (only_suite != 0) {
            int suites[] = {only_suite};

            zassert_equal(zsock_setsockopt(sock, ZSOCK_SOL_TLS, ZSOCK_TLS_CIPHERSUITE_LIST, suites,
                                           sizeof suites),
                          0);
        }
        if (zsock_connect(sock, (const struct net_sockaddr *)&address, sizeof address) == 0) {
            return sock;
        }
        (void)zsock_close(sock);
        k_msleep(CONNECT_RETRY_MS);
    }
    return -1;
}

/* What the peer sent, up to the capacity, until it closes, or nothing arrives for a while. */
static size_t read_until_quiet(int sock, char *buffer, size_t capacity)
{
    size_t used = 0;

    while (used + 1u < capacity) {
        struct zsock_pollfd wait = {.fd = sock, .events = ZSOCK_POLLIN};
        ssize_t got;

        if (zsock_poll(&wait, 1, READ_WAIT_MS) <= 0) {
            break;
        }
        got = zsock_recv(sock, buffer + used, capacity - 1u - used, 0);
        if (got <= 0) {
            break;
        }
        used += (size_t)got;
    }
    buffer[used] = '\0';
    return used;
}

/* One request over a new TLS 1.3 connection, verified. The answer is in `response`. Returns its
 * length, or -1 when there was no connection. *suite is the cipher suite that the handshake chose,
 * or 0 when the socket could not say. */
static int https_exchange(const char *request, int *suite)
{
    int sock = connect_tls(NET_IPPROTO_TLS_1_3, 0, CONNECT_ATTEMPTS);
    size_t sent = 0;
    const size_t length = strlen(request);

    if (sock < 0) {
        return -1;
    }
    if (suite != NULL) {
        int chosen = 0;
        net_socklen_t size = sizeof chosen;

        *suite =
            zsock_getsockopt(sock, ZSOCK_SOL_TLS, ZSOCK_TLS_CIPHERSUITE_USED, &chosen, &size) == 0
                ? chosen
                : 0;
    }
    while (sent < length) {
        const ssize_t wrote = zsock_send(sock, request + sent, length - sent, 0);

        zassert_true(wrote > 0, "send failed (errno %d)", errno);
        sent += (size_t)wrote;
    }
    const size_t got = read_until_quiet(sock, response, sizeof response);

    (void)zsock_close(sock);
    return (int)got;
}

static int https_get(const char *path, const char *extra_headers)
{
    char request[512];

    (void)snprintf(request, sizeof request,
                   "GET %s HTTP/1.1\r\nHost: " SERVER_NAME "\r\n%sConnection: close\r\n\r\n", path,
                   extra_headers);
    return https_exchange(request, NULL);
}

/* The server still answers a verified request after a case that gave it a bad client. */
static void the_server_still_answers(void)
{
    const int got = https_get("/", "");

    zassert_true(got > 0, "no answer after the previous case");
    zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 200"), "answered: %.40s", response);
}

static management_port_config_t port_config(void)
{
    return (management_port_config_t){
        .policy = management_policy_get(),
        .platform_version = MANAGEMENT_PLATFORM_VERSION,
        .project_version = MANAGEMENT_PROJECT_VERSION,
    };
}

ZTEST_SUITE(s6, NULL, NULL, NULL, NULL, NULL);

/* The start sequence refuses what it must before it begins, returns OK once, and a second start
 * changes nothing. A refusal before the sequence begins does not use up the one start. */
ZTEST(s6, test_01_start_sequence)
{
    management_port_config_t config = port_config();
    management_port_status_t status;

    zassert_equal(management_port_start(NULL), MANAGEMENT_PORT_ERR_INVALID_ARGUMENT);
    config.policy = NULL;
    zassert_equal(management_port_start(&config), MANAGEMENT_PORT_ERR_INVALID_ARGUMENT);
    config = port_config();
    config.platform_version = "";
    zassert_equal(management_port_start(&config), MANAGEMENT_PORT_ERR_INVALID_ARGUMENT);

    config = port_config();
    status = management_port_start(&config);
    if (status != MANAGEMENT_PORT_OK) {
        TC_PRINT("log: %s\n", drain_log());
    }
    zassert_equal(status, MANAGEMENT_PORT_OK, "the start returned %d", (int)status);
    zassert_equal(management_port_start(&config), MANAGEMENT_PORT_ERR_ALREADY_STARTED);
}

/* The generated certificate is in Zephyr's credential store under the web tag, the private key is
 * there too (its length only is asked for, and its bytes are never read), the boot log carries the
 * fingerprint line, and the certificate is added as the client's trust anchor. */
ZTEST(s6, test_02_certificate_registered)
{
    size_t length = sizeof trust_anchor;
    size_t key_length = 0;
    uint8_t probe = 0;

    zassert_equal(tls_credential_get(CONFIG_CRUX_WEB_TLS_SEC_TAG, TLS_CREDENTIAL_PUBLIC_CERTIFICATE,
                                     trust_anchor, &length),
                  0);
    zassert_true(length > 64u && length <= 4088u, "certificate length %u", (unsigned)length);
    zassert_equal(trust_anchor[0], 0x30, "a DER certificate starts with a SEQUENCE");
    zassert_equal(tls_credential_get(CONFIG_CRUX_WEB_TLS_SEC_TAG, TLS_CREDENTIAL_PRIVATE_KEY,
                                     &probe, &key_length),
                  -EFBIG, "the key is registered, and a one byte buffer is too small for it");
    zassert_true(key_length > 0u);
    zassert_equal(
        tls_credential_add(CLIENT_CA_TAG, TLS_CREDENTIAL_CA_CERTIFICATE, trust_anchor, length), 0);

    const char *text = drain_log();

    zassert_not_null(strstr(text, "certificate sha256="), "log: %s", text);
    zassert_not_null(strstr(text, "source=generated"), "a blank disk gives a generated one");
}

/* A TLS 1.3 handshake with peer verification required completes, the suite is the TLS 1.3 one of
 * the profile when the socket can say, the server answers a request for the page, and a second
 * connection is served too. */
ZTEST(s6, test_03_tls13_handshake_verifies)
{
    int suite = 0;
    int got = https_exchange("GET / HTTP/1.1\r\nHost: " SERVER_NAME "\r\nConnection: close\r\n\r\n",
                             &suite);

    if (got < 0) {
        TC_PRINT("log: %s\n", drain_log());
    }
    zassert_true(got > 0, "no TLS connection to the listener");
    zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 200"), "answered: %.60s", response);
    if (suite != 0) {
        zassert_equal(suite, SUITE_TLS13_AES_128_GCM_SHA256, "suite 0x%x", suite);
    } else {
        TC_PRINT("the socket did not report the cipher suite\n");
    }
    the_server_still_answers();
}

/* A client whose only cipher suite is a TLS 1.2 suite is refused. Zephyr takes the version as a
 * minimum, so the suite is the restriction. A client that offers TLS 1.3 anyway would connect, and
 * this case would fail and say so. */
ZTEST(s6, test_04_tls12_only_refused)
{
    const int sock =
        connect_tls(NET_IPPROTO_TLS_1_2, SUITE_TLS12_ECDHE_ECDSA_AES_128_GCM_SHA256, 1);

    if (sock >= 0) {
        (void)zsock_close(sock);
    }
    zassert_true(sock < 0, "a client with only a TLS 1.2 suite connected");
    the_server_still_answers();
}

/* Plain HTTP bytes on the TLS port get no HTTP answer, and the next TLS client is served. */
ZTEST(s6, test_05_plain_http_not_answered)
{
    const struct net_sockaddr_in address = loopback_address();
    static const char plain[] = "GET / HTTP/1.1\r\nHost: " SERVER_NAME "\r\n\r\n";
    int sock = zsock_socket(NET_AF_INET, NET_SOCK_STREAM, NET_IPPROTO_TCP);

    zassert_true(sock >= 0);
    zassert_equal(zsock_connect(sock, (const struct net_sockaddr *)&address, sizeof address), 0);
    (void)zsock_send(sock, plain, sizeof plain - 1u, 0);

    const size_t got = read_until_quiet(sock, response, sizeof response);

    (void)zsock_close(sock);
    zassert_false(starts_with(response, got, "HTTP/"), "plain HTTP was answered: %.40s", response);
    the_server_still_answers();
}

/* Each file of the packaged folder is served with its type and the content policy headers, and its
 * bytes are either the compressed form (the header says gzip) or hold a mark of the file. The
 * packager compresses a file when that is smaller, so the bytes of a small file are not always the
 * text of the file. */
ZTEST(s6, test_06_page_bytes)
{
    static const struct {
        const char *path;
        const char *type;
        const char *mark;
    } files[] = {
        {"/", "text/html", "Crux controller management"},
        {"/index.html", "text/html", "Crux controller management"},
        {"/page.css", "text/css", "background"},
        {"/page.js", "text/javascript", "X-Crux-Request"},
    };

    for (size_t i = 0; i < sizeof files / sizeof files[0]; i++) {
        const int got = https_get(files[i].path, "");

        zassert_true(got > 0, "no answer for %s", files[i].path);
        zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 200"), "%s: %.40s", files[i].path,
                     response);
        zassert_true(contains(response, (size_t)got, files[i].type), "%s has no type %s",
                     files[i].path, files[i].type);
        zassert_true(contains(response, (size_t)got, "Content-Security-Policy"), "%s: no policy",
                     files[i].path);
        zassert_true(contains(response, (size_t)got, "Content-Encoding: gzip") ||
                         contains(response, (size_t)got, files[i].mark),
                     "%s is neither compressed nor the packaged text", files[i].path);
    }
}

/* The status and the account routes need a session: with no cookie they answer 401. */
ZTEST(s6, test_07_status_needs_a_session)
{
    int got = https_get("/api/v1/status", "");

    zassert_true(got > 0);
    zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 401"), "status: %.40s", response);
    got = https_get("/api/v1/session/me", "");
    zassert_true(got > 0);
    zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 401"), "me: %.40s", response);
}

/* A login with the right Origin is queued: 202 and an attempt identifier. The password is wrong
 * by construction, because the image has no account. */
ZTEST(s6, test_08_login_attempt_accepted)
{
    static const char body[] = "{\"user\":\"admin\",\"password\":\"not the password of anyone\"}";
    char request[512];

    (void)snprintf(request, sizeof request,
                   "POST /api/v1/session HTTP/1.1\r\nHost: " SERVER_NAME "\r\n"
                   "Origin: https://" SERVER_NAME "\r\nContent-Type: application/json\r\n"
                   "Content-Length: %u\r\nConnection: close\r\n\r\n%s",
                   (unsigned)(sizeof body - 1u), body);

    const int got = https_exchange(request, NULL);

    zassert_true(got > 0);
    zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 202"), "login: %.60s", response);

    const char *start = strstr(response, "{\"id\":\"");

    zassert_not_null(start, "no attempt identifier in: %s", response);
    start += strlen("{\"id\":\"");

    const char *end = strchr(start, '"');

    zassert_not_null(end);
    zassert_true((size_t)(end - start) > 8u && (size_t)(end - start) < sizeof attempt_id);
    memcpy(attempt_id, start, (size_t)(end - start));
    attempt_id[end - start] = '\0';
}

/* The poll, with the custom header, reports the attempt as rejected once the worker has finished:
 * no account exists, and every failure gives the same answer. */
ZTEST(s6, test_09_poll_reports_rejected)
{
    char path[160];

    (void)snprintf(path, sizeof path, "/api/v1/session/attempt/%s", attempt_id);
    zassert_true(attempt_id[0] != '\0', "the previous case gave no attempt identifier");
    for (int poll = 0; poll < 50; poll++) {
        const int got = https_get(path, "X-Crux-Request: 1\r\n");

        zassert_true(got > 0);
        zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 200"), "poll: %.60s", response);
        if (!contains(response, (size_t)got, "\"state\":\"pending\"")) {
            zassert_true(contains(response, (size_t)got, "\"state\":\"rejected\""),
                         "the attempt ended as: %s", response);
            return;
        }
        k_msleep(100);
    }
    zassert_true(false, "the attempt was still pending after 50 polls");
}

/* The same poll without the custom header answers 403 csrf_rejected, before it looks at the
 * attempt. */
ZTEST(s6, test_10_csrf_rejected_without_header)
{
    char path[160];

    (void)snprintf(path, sizeof path, "/api/v1/session/attempt/%s", attempt_id);

    const int got = https_get(path, "");

    zassert_true(got > 0);
    zassert_true(starts_with(response, (size_t)got, "HTTP/1.1 403"), "poll: %.60s", response);
    zassert_true(contains(response, (size_t)got, "csrf_rejected"), "answer: %s", response);
}
