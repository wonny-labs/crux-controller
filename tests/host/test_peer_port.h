/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_PEER_PORT_H
#define TEST_PEER_PORT_H

/* The peer port of test_net_client. In the firmware image the port is a Kconfig value, a
 * constant of the build. The host test cannot use a constant: a fixed port would collide with a
 * second copy of the test, or with another program on the machine. The build therefore defines
 * CONFIG_CRUX_CONTROLLER_PEER_PORT as this variable, which the test sets to the port that the
 * system assigned to its listener before each exchange. The production source is not changed. */
extern unsigned short test_peer_port;

#endif
