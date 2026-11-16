/* SPDX-License-Identifier: Apache-2.0 */
#ifndef MANAGEMENT_POLICY_H
#define MANAGEMENT_POLICY_H

/*
 * The product's policy for HTTPS management, as plain C with ISO C includes only, so the host
 * builds and tests it with no Crux or Zephyr header. No firmware image compiles this file yet.
 */

#include <stdbool.h>

/*
 * True when text is a strict dotted IPv4 address: four decimal parts separated by single dots,
 * each part 0 to 255, written with one to three digits and no leading zero (a part that starts
 * with zero is exactly "0"). No sign, no space, no other character and no text after the last
 * part. A null pointer and the empty text are refused. The text ends at its first NUL, so bytes
 * after a NUL are not seen.
 *
 * The Zephyr web server treats a bind text that is not an address as "every address", so a
 * composition that wants one interface has to refuse such a text itself, and this is the check.
 */
bool management_address_valid(const char *text);

#endif
