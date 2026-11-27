/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RETAINED_PORT_H
#define RETAINED_PORT_H

/*
 * The port of the retained region (specification section 5.1), implemented in the adapter zone
 * (framework/os/retained_zephyr.c) over the Zephyr retention area that the devicetree node label
 * controller_retained names. The area adds Zephyr's prefix and checksum around the bytes of
 * boot_record.h. An image without that node has no retained region: reads fail and writes do
 * nothing, and the framework keeps the boot counter in RAM for that boot only.
 *
 * The fatal error handler writes through this port too, so no call takes a mutex or waits:
 * retained_port_lock() masks interrupts, and the image builds the retention subsystem and the
 * retained memory driver without their mutexes.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* True when the image has the region and its device is ready. */
bool retained_port_present(void);

/* Read size bytes. False when the region is absent, its prefix or checksum is not valid, or the
 * read fails. */
bool retained_port_read(uint8_t *buffer, size_t size);

/* Write size bytes, Zephyr's checksum last. False when the region is absent or the write fails. */
bool retained_port_write(const uint8_t *buffer, size_t size);

/* Mask interrupts around an update of the region; nestable, usable in the fatal error handler. */
unsigned int retained_port_lock(void);
void retained_port_unlock(unsigned int key);

#endif
