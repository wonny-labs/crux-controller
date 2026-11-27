/* SPDX-License-Identifier: Apache-2.0 */
#ifndef REBOOT_PORT_H
#define REBOOT_PORT_H

/*
 * The framework's reboot thread (framework/os/reboot_zephyr.c), which carries out the restarts that
 * operators request through Crux Reboot. Start it once, after Crux Reboot has started with the
 * framework's policy (reboot_policy.h). Returns 0, or -1 on a second call.
 */
int reboot_port_start(void);

#endif
