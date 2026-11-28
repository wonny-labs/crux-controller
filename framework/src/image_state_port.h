/* SPDX-License-Identifier: Apache-2.0 */
#ifndef IMAGE_STATE_PORT_H
#define IMAGE_STATE_PORT_H

/*
 * The port of the image state (specification section 6.1), implemented by the update component
 * over Crux's image state contract. Crux has no image state provider for Zephyr yet (gap C10), so
 * no image implements this port and no image builds image_trial.c; the host tests implement it with
 * a fake (tests/host/test_image_trial.c).
 *
 * The partition layout, the image format and the confirmation call come from Crux's secure boot
 * work; this port names none of them. With MCUboot, a test image that is not confirmed is reverted
 * at the next boot, and confirmation sets the Image OK byte of the image trailer (MCUboot design,
 * "Boot Swap Types" and "Image Trailer"). MCUboot itself has no confirmation timeout, so the trial
 * deadline of image_trial.h requests the reset that lets the boot loader revert.
 */

#include <stdbool.h>

typedef enum {
    IMAGE_STATE_UNKNOWN = 0, /* no provider, or the state could not be read */
    IMAGE_STATE_CONFIRMED,   /* the running image is confirmed */
    IMAGE_STATE_TEST,        /* the running image is a test image that is not confirmed yet */
} image_state_t;

/* The state of the running image. */
image_state_t image_state_port_read(void);

/* Confirm the running image, so that the boot loader keeps it. False when it failed. */
bool image_state_port_confirm(void);

/*
 * Request a planned reset, at which the boot loader reverts the test image. The reset carries no
 * operator reset marker, so it counts as a fault reset (section 5.1). False when the request was
 * not accepted; true when it was accepted, whether or not the reset has happened yet.
 */
bool image_state_port_request_reset(void);

#endif
