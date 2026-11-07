/* SPDX-License-Identifier: Apache-2.0 */

#include <crux/status.h>
#include <crux/time.h>

#include <zephyr/sys/printk.h>

int main(void)
{
    crux_monotonic_time_t now;
    const crux_status_t status = crux_monotonic_now(&now);

    if (status != CRUX_OK) {
        printk("crux-controller: clock failed, status=%d\n", (int)status);
        return -1;
    }

    printk("crux-controller: ready\n");
    return 0;
}
