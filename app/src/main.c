/* SPDX-License-Identifier: Apache-2.0 */

#include <crux/status.h>
#include <crux/time.h>

/* The skeleton only proves that the build chain links a public Crux target.
 * Console output arrives with the Logging composition of step S1. */
int main(void)
{
    crux_monotonic_time_t now;

    return crux_monotonic_now(&now) == CRUX_OK ? 0 : -1;
}
