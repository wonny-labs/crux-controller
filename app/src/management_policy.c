/* SPDX-License-Identifier: Apache-2.0 */

#include "management_policy.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ADDRESS_PARTS 4u
#define PART_DIGITS_MAX 3u
#define PART_VALUE_MAX 255u

bool management_address_parse(const char *text, uint8_t octets[4])
{
    uint8_t found[ADDRESS_PARTS];

    if (text == NULL || octets == NULL) {
        return false;
    }

    for (unsigned int part = 0; part < ADDRESS_PARTS; part++) {
        unsigned int digits = 0;
        unsigned int value = 0;

        while (text[digits] >= '0' && text[digits] <= '9') {
            if (digits == PART_DIGITS_MAX) {
                return false;
            }
            value = value * 10u + (unsigned int)(text[digits] - '0');
            digits++;
        }
        if (digits == 0u || (digits > 1u && text[0] == '0') || value > PART_VALUE_MAX) {
            return false;
        }
        found[part] = (uint8_t)value;
        text += digits;

        if (part + 1u < ADDRESS_PARTS) {
            if (*text != '.') {
                return false;
            }
            text++;
        }
    }
    if (*text != '\0') {
        return false;
    }
    for (unsigned int part = 0; part < ADDRESS_PARTS; part++) {
        octets[part] = found[part];
    }
    return true;
}

bool management_address_valid(const char *text)
{
    uint8_t octets[ADDRESS_PARTS];

    return management_address_parse(text, octets);
}

/* Both Crux Access limits, as copies: a name is at most 31 bytes, a permission at most 63. */
#define ACCESS_NAME_LENGTH_MAX 31u
#define ACCESS_PERMISSION_LENGTH_MAX 63u

static const char *const administrator_permissions[] = {
    MANAGEMENT_PERMISSION_ACCESS_MANAGE,
    MANAGEMENT_PERMISSION_STATUS_READ,
    MANAGEMENT_PERMISSION_CONFIG_SAVE,
};

static const char *const read_only_permissions[] = {
    MANAGEMENT_PERMISSION_STATUS_READ,
};

static const management_role_t roles[] = {
    {MANAGEMENT_ROLE_ADMINISTRATOR, administrator_permissions,
     sizeof administrator_permissions / sizeof administrator_permissions[0]},
    {MANAGEMENT_ROLE_READ_ONLY, read_only_permissions,
     sizeof read_only_permissions / sizeof read_only_permissions[0]},
};

static const management_policy_t policy = {
    .roles = roles,
    .role_count = sizeof roles / sizeof roles[0],
    .session_idle_limit_s = MANAGEMENT_SESSION_IDLE_LIMIT_S,
    .session_absolute_limit_s = MANAGEMENT_SESSION_ABSOLUTE_LIMIT_S,
};

const management_policy_t *management_policy_get(void)
{
    return &policy;
}

/* The length of text up to its terminator, or maximum + 1 when it is longer than maximum. */
static size_t bounded_length(const char *text, size_t maximum)
{
    size_t length = 0;

    while (length <= maximum && text[length] != '\0') {
        length++;
    }
    return length;
}

static bool text_valid(const char *text, size_t maximum)
{
    size_t length;

    if (text == NULL) {
        return false;
    }
    length = bounded_length(text, maximum);
    return length >= 1u && length <= maximum;
}

static bool text_equal(const char *left, const char *right)
{
    size_t index = 0;

    while (left[index] != '\0' && left[index] == right[index]) {
        index++;
    }
    return left[index] == right[index];
}

bool management_permission_names_match(const char *access_manage, const char *status_read,
                                       const char *config_save)
{
    return access_manage != NULL && status_read != NULL && config_save != NULL &&
           text_equal(access_manage, MANAGEMENT_PERMISSION_ACCESS_MANAGE) &&
           text_equal(status_read, MANAGEMENT_PERMISSION_STATUS_READ) &&
           text_equal(config_save, MANAGEMENT_PERMISSION_CONFIG_SAVE);
}

static bool role_valid(const management_role_t *role)
{
    if (!text_valid(role->name, ACCESS_NAME_LENGTH_MAX)) {
        return false;
    }
    if (role->permission_count > 0u && role->permissions == NULL) {
        return false;
    }
    for (size_t index = 0; index < role->permission_count; index++) {
        if (!text_valid(role->permissions[index], ACCESS_PERMISSION_LENGTH_MAX)) {
            return false;
        }
        for (size_t earlier = 0; earlier < index; earlier++) {
            if (text_equal(role->permissions[earlier], role->permissions[index])) {
                return false;
            }
        }
    }
    return true;
}

static bool role_holds_manage(const management_role_t *role)
{
    for (size_t index = 0; index < role->permission_count; index++) {
        if (text_equal(role->permissions[index], MANAGEMENT_PERMISSION_ACCESS_MANAGE)) {
            return true;
        }
    }
    return false;
}

bool management_policy_valid(const management_policy_t *candidate)
{
    bool has_administrator = false;

    if (candidate == NULL || candidate->roles == NULL || candidate->role_count == 0u ||
        candidate->session_idle_limit_s == 0u || candidate->session_absolute_limit_s == 0u ||
        candidate->session_idle_limit_s > candidate->session_absolute_limit_s) {
        return false;
    }
    for (size_t index = 0; index < candidate->role_count; index++) {
        const management_role_t *role = &candidate->roles[index];

        if (!role_valid(role)) {
            return false;
        }
        for (size_t earlier = 0; earlier < index; earlier++) {
            if (text_equal(candidate->roles[earlier].name, role->name)) {
                return false;
            }
        }
        has_administrator = has_administrator || role_holds_manage(role);
    }
    return has_administrator;
}

bool management_version_valid(const char *text)
{
    size_t length;

    if (text == NULL) {
        return false;
    }
    length = bounded_length(text, MANAGEMENT_VERSION_LENGTH_MAX);
    if (length < 1u || length > MANAGEMENT_VERSION_LENGTH_MAX) {
        return false;
    }
    for (size_t index = 0; index < length; index++) {
        const unsigned char byte = (unsigned char)text[index];

        if (byte < 0x20u || byte > 0x7Eu) {
            return false;
        }
    }
    return true;
}
