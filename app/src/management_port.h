/* SPDX-License-Identifier: Apache-2.0 */
#ifndef MANAGEMENT_PORT_H
#define MANAGEMENT_PORT_H

/*
 * The product-owned port of HTTPS management. app/src declares it, and the composition zone
 * (app/compose) is the place where an implementation would call the Crux services and the Zephyr
 * web server, so this header names no Crux, Zephyr or composition header. It includes only ISO C
 * and the policy header of this repository, so that it needs nothing from Crux to be read or
 * tested. The implementation copies the policy into the Crux type and sets no password rule, so
 * that Crux uses its reference rule.
 *
 * The composition zone implements this port in app/compose/management_start.c, and
 * app/src/composition.c calls it when management is built. The order below is a reading of
 * three Crux sources at the pinned revision, and it has not run on a board: the "Boot order"
 * section of docs/management-in-a-product.md, the start calls of the module test
 * tests/native/management_module/src/main.c (configuration service, management status and security
 * event start, and only then the TLS certificate start), and the header
 * components/web/ports/zephyr/include/crux/web_zephyr.h (services started, TLS material registered
 * under the security tag, then the session and management init with their workers, then start).
 *
 *   1. security event init, realtime init, mount the medium and bind the two store roots
 *   2. credential store start, then Access init with the policy below
 *   3. config service start, management status start, then security event start
 *   4. TLS certificate start
 *   5. take the certificate material and register it under the web security tag, and fail the
 *      start if either registration fails (the web listener does not report a missing certificate)
 *   6. web session init and web management init, each with its worker
 *   7. web start, with the session authenticate function
 *
 * The guide puts the first account between steps 3 and 4. This port does not create one: that
 * is the serial console's work, in a later change.
 *
 * management_port_start() runs the whole sequence once, on one thread, before any request.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "management_policy.h"

typedef enum {
    MANAGEMENT_PORT_OK = 0,
    MANAGEMENT_PORT_ERR_INVALID_ARGUMENT = -1,
    MANAGEMENT_PORT_ERR_ALREADY_STARTED = -2, /* A second start; nothing changed. */
    MANAGEMENT_PORT_ERR_STEP_FAILED = -3,     /* A step of the sequence refused; nothing serves. */
} management_port_status_t;

typedef struct {
    /* The roles and the session limits, borrowed for the program's life. */
    const management_policy_t *policy;
    /* At most 63 bytes each, from the build. Borrowed for the call. */
    const char *platform_version;
    const char *project_version;
} management_port_config_t;

/* Start HTTPS management, or refuse and leave it off. Returns once, never serves a half start. */
management_port_status_t management_port_start(const management_port_config_t *config);

#endif
