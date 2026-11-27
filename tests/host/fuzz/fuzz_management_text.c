/* SPDX-License-Identifier: Apache-2.0 */

/*
 * Fuzz target of the text parsers of the management policy (management_policy.h; criterion 41):
 * the web management bind address and the version texts. The framework has no parser of the
 * application's parameter table of its own (Crux's configuration service validates the table and
 * parses each value), so these are the nearest portable parsers of configuration text in this
 * repository. The input is one text; bytes after a NUL are not seen, as the functions document.
 *
 * Properties checked, each with abort() on failure:
 * - the address check and the address parse agree;
 * - a parsed address, written again as four decimal parts, parses to the same four parts;
 * - a failed parse leaves the destination as it was;
 * - a version text that passes is 1 to MANAGEMENT_VERSION_LENGTH_MAX bytes of printable ASCII.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fuzz_target.h"
#include "management_policy.h"

/* The longest text that the target passes on; longer input is cut. */
#define TEXT_MAX 256u

static void require(bool condition)
{
    if (!condition) {
        abort();
    }
}

static bool printable_ascii(const char *text, size_t length)
{
    for (size_t index = 0; index < length; index++) {
        if ((unsigned char)text[index] < 0x20u || (unsigned char)text[index] > 0x7eu) {
            return false;
        }
    }
    return true;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    char text[TEXT_MAX + 1u];
    const size_t length = size < TEXT_MAX ? size : TEXT_MAX;
    uint8_t octets[4] = {0xa5u, 0xa5u, 0xa5u, 0xa5u};

    if (length > 0u) {
        memcpy(text, data, length);
    }
    text[length] = '\0';

    const bool valid = management_address_valid(text);
    const bool parsed = management_address_parse(text, octets);

    require(valid == parsed);
    if (parsed) {
        char again[16];
        uint8_t octets_again[4];

        (void)snprintf(again, sizeof again, "%u.%u.%u.%u", (unsigned)octets[0], (unsigned)octets[1],
                       (unsigned)octets[2], (unsigned)octets[3]);
        require(management_address_parse(again, octets_again));
        require(memcmp(octets, octets_again, sizeof octets) == 0);
    } else {
        for (size_t index = 0; index < sizeof octets; index++) {
            require(octets[index] == 0xa5u);
        }
    }

    if (management_version_valid(text)) {
        const size_t text_length = strlen(text);

        require(text_length >= 1u && text_length <= MANAGEMENT_VERSION_LENGTH_MAX);
        require(printable_ascii(text, text_length));
    }
    return 0;
}
