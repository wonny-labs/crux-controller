/* SPDX-License-Identifier: Apache-2.0 */

#include "management_policy.h"

#include <stdbool.h>
#include <stddef.h>

#define ADDRESS_PARTS 4u
#define PART_DIGITS_MAX 3u
#define PART_VALUE_MAX 255u

bool management_address_valid(const char *text)
{
    if (text == NULL) {
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
        text += digits;

        if (part + 1u < ADDRESS_PARTS) {
            if (*text != '.') {
                return false;
            }
            text++;
        }
    }
    return *text == '\0';
}
