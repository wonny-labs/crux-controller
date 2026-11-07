/* SPDX-License-Identifier: Apache-2.0 */
#ifndef NET_CLIENT_H
#define NET_CLIENT_H

#include "workload.h"

enum {
    NET_CLIENT_OK = 0,
    NET_CLIENT_ERR_SOCKET = -1,   /* no socket, or the peer address is not an IPv4 address */
    NET_CLIENT_ERR_CONNECT = -2,  /* the connection failed */
    NET_CLIENT_ERR_TIMEOUT = -3,  /* the exchange did not finish within its deadline */
    NET_CLIENT_ERR_SEND = -4,
    NET_CLIENT_ERR_RECEIVE = -5,  /* a receive error or an early end of stream */
    NET_CLIENT_ERR_PROTOCOL = -6, /* the reply is not the message that was sent */
};

/*
 * One exchange with the peer: connect, send the eight-byte message, expect the same eight
 * bytes back, close. Uses only the calls of the Crux Sockets profile: nonblocking descriptors
 * with poll, and one overall deadline. Returns NET_CLIENT_OK or a negative NET_CLIENT_ERR value.
 * A Linux executable must ignore SIGPIPE before it calls this, as the Sockets profile requires.
 */
int net_client_exchange(const workload_message_t *message);

#endif
