/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The composition zone of step S6: the one place that starts Crux's HTTPS management. It implements
 * the port that app/src declares (management_port.h) in the order that the port documents, with the
 * public headers of the Crux services, the two composition interfaces the zone may name
 * (<crux/file_zephyr.h> through the storage port, and <crux/web_zephyr.h>) and one Zephyr header on
 * the zone's allow-list, <zephyr/net/tls_credentials.h>, because Crux takes no part in registering
 * the TLS material: Zephyr's own credential store carries it to the listener.
 *
 * The roles, the session limits and the three permission names are the product's policy
 * (management_policy.h, plain C). This file copies the policy into the Crux type member by member
 * and refuses to start when the product's copy of a permission name is not the Crux text. The
 * password rule is left to Crux's reference rule. No account is made here: the first account is
 * made from the serial console, in a later change.
 *
 * The route sources, the packaged page and the route table are not here. They belong to the target
 * `app` and are named by app/management/management.cmake.
 *
 * Status: built in CI for the board and run on native_sim; never run on a board. The order below
 * is the one of management_port.h, which was read in Crux's guide, module fixture and web start
 * header at the pinned revision.
 *
 * A credential store that Crux reports as unusable (CRUX_CREDENTIAL_ERR_UNUSABLE) ends the start,
 * because nothing after it could keep a key or an account. That is fine on a RAM disk, where the
 * store is made again blank at every start, and it is to be revisited for a persistent medium,
 * where a damaged store would then leave management off until someone repairs it.
 */

#include "../src/management_port.h"
#include "../src/storage_port.h"

#include <crux/access.h>
#include <crux/config_service.h>
#include <crux/credential_store.h>
#include <crux/logging.h>
#include <crux/management_status.h>
#include <crux/security_event.h>
#include <crux/status.h>
#include <crux/system.h>
#include <crux/time.h>
#include <crux/tls_certificate_start.h>
#include <crux/web.h>
#include <crux/web_management.h>
#include <crux/web_session.h>
#include <crux/web_zephyr.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/net/tls_credentials.h>

/* A text that is no address would make Zephyr's server listen on every address, so the build asks
 * for one, and the start checks that it is a dotted IPv4 text. */
_Static_assert(sizeof(CONFIG_CRUX_WEB_BIND_ADDRESS) > 1u,
               "step S6 listens on one address: set CONFIG_CRUX_WEB_BIND_ADDRESS");

#define LOG_TAG "mgmt"
/* The roles that the copy into the Crux type holds. The product has two. */
#define ROLES_MAX 4u
/* Declared time limit of one handler, counted by the web core when it is exceeded. */
#define HANDLER_LIMIT_MS 100u
/* The names in the certificate, besides the address. */
#define CERTIFICATE_COMMON_NAME "crux-controller"
#define CERTIFICATE_DNS_NAME "crux-controller"

/* One start per program. Crux's init functions run once, so a start that began cannot be retried.
 */
static bool started;

static crux_access_role_t access_roles[ROLES_MAX];
static crux_access_policy_t access_policy;

static const char *const certificate_dns_names[] = {CERTIFICATE_DNS_NAME};
static uint8_t certificate_ipv4[1][4];
static crux_tls_certificate_options_t certificate_options;

static void note(crux_log_level_t level, const char *text)
{
    (void)crux_log_write(level, LOG_TAG, text);
}

/* Say which step refused and refuse the start. Nothing serves. */
static management_port_status_t failed(const char *step)
{
    char text[CRUX_LOG_TEXT_MAX];

    (void)snprintf(text, sizeof text, "management start refused at %s", step);
    note(CRUX_LOG_ERROR, text);
    return MANAGEMENT_PORT_ERR_STEP_FAILED;
}

/* The product's three permission names are copies, because management_policy.h has no Crux
 * include. They must be the text that the services check, or a role would grant nothing or the
 * wrong thing, so the start compares them with the Crux macros. */
static bool permission_names_agree(void)
{
    return management_permission_names_match(CRUX_ACCESS_PERMISSION_MANAGE,
                                             CRUX_MGMT_STATUS_PERMISSION_READ,
                                             CRUX_CONFIG_SERVICE_PERMISSION_SAVE);
}

static bool management_role_count_fits(const management_policy_t *policy)
{
    return policy->role_count <= ROLES_MAX;
}

/* Copy the policy into the Crux type, member by member. The strings are the product's, borrowed
 * for the program's life, and the arrays are static for the same reason. */
static void copy_policy(const management_policy_t *policy)
{
    for (size_t index = 0; index < policy->role_count; index++) {
        access_roles[index] = (crux_access_role_t){
            .name = policy->roles[index].name,
            .permissions = policy->roles[index].permissions,
            .permission_count = policy->roles[index].permission_count,
        };
    }
    access_policy = (crux_access_policy_t){
        .roles = access_roles,
        .role_count = policy->role_count,
        .session_idle_limit_s = policy->session_idle_limit_s,
        .session_absolute_limit_s = policy->session_absolute_limit_s,
        /* NULL selects the reference rule of Crux Access. */
        .password_acceptable = NULL,
    };
}

/* The generated certificate to Zephyr's TLS credentials, before the listener. The material is the
 * program's to keep: its bytes stay valid until the program ends, it is not copied, released or
 * logged, and it goes to Zephyr by pointer. A listener with no certificate under the tag does not
 * listen and does not say so, so both registrations are checked. */
static int tls_credentials_register(void)
{
    static crux_tls_certificate_material_t material;

    if (crux_tls_certificate_material_take(&material) != CRUX_TLS_CERTIFICATE_OK) {
        return -1;
    }
    int result = tls_credential_add(CONFIG_CRUX_WEB_TLS_SEC_TAG, TLS_CREDENTIAL_PUBLIC_CERTIFICATE,
                                    material.certificate, material.certificate_length);
    if (result == 0) {
        result = tls_credential_add(CONFIG_CRUX_WEB_TLS_SEC_TAG, TLS_CREDENTIAL_PRIVATE_KEY,
                                    material.private_key, material.private_key_length);
    }
    return result;
}

/* The certificate names the one address that the listener binds, and a DNS name. The options are
 * borrowed by Crux for the program's life, so they are static. The clock is not trusted before
 * time synchronisation, so the module's default start of validity applies, and the validity is
 * the module's default too. */
static void set_certificate_options(const uint8_t octets[4])
{
    memcpy(certificate_ipv4[0], octets, 4u);
    certificate_options = (crux_tls_certificate_options_t){
        .names =
            {
                .common_name = CERTIFICATE_COMMON_NAME,
                .dns_names = certificate_dns_names,
                .dns_count = sizeof certificate_dns_names / sizeof certificate_dns_names[0],
                .ipv4 = (const uint8_t(*)[4])certificate_ipv4,
                .ipv4_count = 1u,
            },
        .not_before_s = CRUX_TLS_CERTIFICATE_DEFAULT_NOT_BEFORE_S,
        .validity_days = 0u,
    };
}

management_port_status_t management_port_start(const management_port_config_t *config)
{
    uint8_t octets[4];
    crux_tls_certificate_start_t how = CRUX_TLS_CERTIFICATE_STARTED;
    crux_reset_cause_t cause = {0};
    char fingerprint[CRUX_TLS_CERTIFICATE_FINGERPRINT_TEXT_SIZE];
    char text[CRUX_LOG_TEXT_MAX];

    if (started) {
        return MANAGEMENT_PORT_ERR_ALREADY_STARTED;
    }
    if (config == NULL || !management_policy_valid(config->policy) ||
        !management_role_count_fits(config->policy) ||
        !management_version_valid(config->platform_version) ||
        !management_version_valid(config->project_version)) {
        return MANAGEMENT_PORT_ERR_INVALID_ARGUMENT;
    }
    if (!permission_names_agree()) {
        return failed("permission names");
    }
    if (!management_address_parse(CONFIG_CRUX_WEB_BIND_ADDRESS, octets)) {
        return failed("bind address");
    }
    /* From here on a step has begun, and Crux's init functions cannot be repeated. */
    started = true;

    /* 1. Events first, so that everything after can emit. Then the clock, the medium and the two
     * roots of the store. */
    if (crux_security_event_init(NULL, 0u) != CRUX_OK) {
        return failed("security events");
    }
    if (crux_realtime_init() != CRUX_OK) {
        return failed("time");
    }
    if (storage_port_mount(STORAGE_PORT_FORMAT_ON_FAILED_MOUNT) != STORAGE_PORT_OK) {
        return failed("medium");
    }
    if (storage_port_bind_store() != STORAGE_PORT_OK) {
        return failed("store roots");
    }

    /* 2. The credential store, then Access with the product's roles. A store that is unusable
     * ends here: nothing after it could keep a key or an account. */
    if (crux_credential_start(STORAGE_PORT_STORE_ROOT_A, STORAGE_PORT_STORE_ROOT_B) !=
        CRUX_CREDENTIAL_OK) {
        return failed("credential store");
    }
    copy_policy(config->policy);
    if (crux_access_init(&access_policy) != CRUX_ACCESS_OK) {
        return failed("access");
    }

    /* 3. The configuration service with no parameter of its own, the status service with the reset
     * cause that this step captures once and never clears, and the event thread. The cause is read
     * before the initialiser that holds it, because the members of an initialiser are not
     * evaluated in a fixed order. */
    if (crux_config_service_start(NULL, 0u) != CRUX_CONFIG_SERVICE_OK) {
        return failed("configuration service");
    }
    const crux_status_t cause_status = crux_system_reset_cause_get(&cause);
    const crux_mgmt_status_config_t status = {
        .platform_version = config->platform_version,
        .project_version = config->project_version,
        .boot_reset_cause_status = cause_status,
        .boot_reset_cause = cause,
    };
    if (crux_mgmt_status_start(&status) != CRUX_OK) {
        return failed("status");
    }
    if (crux_security_event_start() != CRUX_OK) {
        return failed("security event thread");
    }

    /* 4. The TLS certificate. The device key is made inside this call, from the hardware random
     * source, when the store holds none. */
    set_certificate_options(octets);
    if (crux_tls_certificate_start(&certificate_options, &how) != CRUX_TLS_CERTIFICATE_OK) {
        return failed("tls certificate");
    }

    /* 5. The material to Zephyr's credentials, before the listener, and the fingerprint to the log
     * so that a person can compare it with what the client shows (trust on first use). */
    if (tls_credentials_register() != 0) {
        return failed("tls credentials");
    }
    if (crux_tls_certificate_fingerprint(fingerprint) != CRUX_TLS_CERTIFICATE_OK) {
        return failed("certificate fingerprint");
    }
    (void)snprintf(text, sizeof text, "certificate sha256=%s source=%s", fingerprint,
                   how == CRUX_TLS_CERTIFICATE_GENERATED ? "generated" : "stored");
    note(CRUX_LOG_INFO, text);

    /* 6. Sessions and management, each with its worker. HTTPS only, and the one accepted Origin is
     * the request's own host, because no list is given. */
    static const crux_web_session_config_t sessions = {"https", NULL, 0u};
    if (crux_web_session_init(&sessions) != CRUX_WEB_OK ||
        crux_web_session_start_worker() != CRUX_WEB_OK) {
        return failed("web session");
    }
    if (crux_web_management_init() != CRUX_WEB_OK ||
        crux_web_management_start_worker() != CRUX_WEB_OK) {
        return failed("web management");
    }

    /* 7. The listener. It opens on Zephyr's own thread, so a success here is not a connection. */
    static const crux_web_config_t web = {
        .authenticate = crux_web_session_authenticate,
        .authenticate_context = NULL,
        .request_deadline_ms = CONFIG_CRUX_WEB_REQUEST_DEADLINE_MS,
        .handler_limit_ms = HANDLER_LIMIT_MS,
    };
    if (crux_web_start(&web) != CRUX_WEB_OK) {
        return failed("https listener");
    }
    (void)snprintf(text, sizeof text, "https management started on %s port %d",
                   CONFIG_CRUX_WEB_BIND_ADDRESS, CONFIG_CRUX_WEB_PORT);
    note(CRUX_LOG_INFO, text);
    return MANAGEMENT_PORT_OK;
}
