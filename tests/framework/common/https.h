/* SPDX-License-Identifier: Apache-2.0 */
#ifndef HTTPS_H
#define HTTPS_H

/*
 * A minimal HTTPS client of the native_sim scenarios: one request per TLS 1.3 connection to the
 * listener of web management on the loopback address, and the browser login of Crux's session
 * routes (POST /api/v1/session, then the attempt poll, which hands over the session cookies). The
 * client does not verify the server's certificate: the scenarios test the routes, and the
 * management scenario (tests/native_sim_mbed/management) tests the certificate.
 */

#include <stddef.h>

/* The host name of the requests, a name in the framework's certificate. */
#define HTTPS_HOST "crux-controller"

/*
 * Send one request and read the answer into response (NUL-terminated). extra_headers is NULL or
 * lines that each end with CRLF; body is NULL or the text of the body. Returns the HTTP status, or
 * -1 when no answer came.
 */
int https_request(const char *method, const char *path, const char *extra_headers, const char *body,
                  char *response, size_t capacity);

/*
 * Log in through the session routes and write the header line that carries the session cookies
 * ("Cookie: ...\r\n") into cookie. Returns 0, or -1 when the login was not accepted.
 */
int https_login(const char *user, const char *password, char *cookie, size_t capacity);

#endif
