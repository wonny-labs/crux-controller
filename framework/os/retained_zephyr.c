/* SPDX-License-Identifier: Apache-2.0 */

/*
 * The adapter zone of the retained region (framework/src/retained_port.h): the Zephyr retention
 * area that the devicetree node label controller_retained names, with Zephyr's prefix and checksum
 * around the bytes of boot_record.h. Zephyr's retention write puts the data first, then the prefix,
 * then the checksum, so a write that a reset cuts fails the checksum on the next boot.
 *
 * The fatal error handler writes here too, so nothing may take a mutex: the image builds the
 * retention subsystem and the retained memory driver without their mutexes, which the assertions
 * below check, and every update holds an interrupt lock instead. An image without the node has no
 * region.
 *
 * Where the region lies is the board overlay's choice. Whether it survives a watchdog reset and a
 * pin reset of the board, and whether a power cycle leaves it invalid, are board facts that only a
 * board check shows (specification section 5.6); none has been run.
 */

#include "../src/retained_port.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>
#include <zephyr/retention/retention.h>

#define RETAINED_NODE DT_NODELABEL(controller_retained)

#if DT_NODE_HAS_STATUS_OKAY(RETAINED_NODE) && defined(CONFIG_RETENTION)
#define HAS_REGION 1
BUILD_ASSERT(!IS_ENABLED(CONFIG_RETENTION_MUTEXES),
             "the fatal error handler writes the retained region: set CONFIG_RETENTION_MUTEXES=n");
BUILD_ASSERT(
    !IS_ENABLED(CONFIG_RETAINED_MEM_MUTEXES),
    "the fatal error handler writes the retained region: set CONFIG_RETAINED_MEM_MUTEXES=n");
static const struct device *const region = DEVICE_DT_GET(RETAINED_NODE);
#else
#define HAS_REGION 0
#endif

bool retained_port_present(void)
{
#if HAS_REGION
    return device_is_ready(region);
#else
    return false;
#endif
}

bool retained_port_read(uint8_t *buffer, size_t size)
{
#if HAS_REGION
    const ssize_t available = retention_size(region);

    return buffer != NULL && retained_port_present() && available >= 0 &&
           (size_t)available >= size && retention_is_valid(region) == 1 &&
           retention_read(region, 0, buffer, size) == 0;
#else
    (void)buffer;
    (void)size;
    return false;
#endif
}

bool retained_port_write(const uint8_t *buffer, size_t size)
{
#if HAS_REGION
    const ssize_t available = retention_size(region);

    return buffer != NULL && retained_port_present() && available >= 0 &&
           (size_t)available >= size && retention_write(region, 0, buffer, size) == 0;
#else
    (void)buffer;
    (void)size;
    return false;
#endif
}

unsigned int retained_port_lock(void)
{
    return irq_lock();
}

void retained_port_unlock(unsigned int key)
{
    irq_unlock(key);
}
