# SPDX-License-Identifier: Apache-2.0

# Interim fix of native_sim's offloaded sockets for the interactive configuration only. It is a
# project-specific workaround, outside the composition interfaces that Crux publishes.
#
# The offload reports a peer's FIN as POLLIN alone, where Zephyr's own TCP adds POLLHUP (sock_is_eof in
# sockets_inet.c). With Mbed TLS that FIN never reaches poll, so a client that closes without a TLS
# close_notify leaves the web server spinning inside zsock_poll, and the simulated clock stops. This
# file builds a copy of the offload's host side, Zephyr's drivers/net/nsos_adapt.c, that also asks
# epoll for EPOLLRDHUP and reports it as POLLHUP. The West checkout is not edited. The copy keeps the
# file's copyright and SPDX-License-Identifier lines.
#
# Provenance: adapted from Crux tests/native/web_https/nsos_rdhup.cmake at 1330195487c3 (the pinned
# Crux, Apache-2.0), without its --no-rdhup test switch. Crux documents the limit in
# docs/https-composition.md, "Abrupt close and the CPU spin".
# Removal: replace this file with the version that Crux publishes for products, or drop it when
# Zephyr's driver reports EPOLLRDHUP itself. docs/native-sim-interactive.md, "Limits", says the same.

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_NET_NATIVE_OFFLOADED_SOCKETS)
    message(FATAL_ERROR "nsos_rdhup.cmake is for native_sim with offloaded sockets only")
endif()

set(nsos_source "${ZEPHYR_BASE}/drivers/net/nsos_adapt.c")
# The driver at Zephyr v4.5.0. Another hash means that Zephyr moved: review the edits again.
set(nsos_sha256 75dabbeb67eccfded419b4e1a105e1d9838c431c985035459bf94af071bb70c0)
file(SHA256 "${nsos_source}" nsos_actual)
if(NOT nsos_actual STREQUAL nsos_sha256)
    message(FATAL_ERROR "${nsos_source} is not the reviewed Zephyr v4.5.0 file (${nsos_actual}): "
                        "review tests/framework/interactive/nsos_rdhup.cmake again")
endif()
file(READ "${nsos_source}" nsos_text)
string(FIND "${nsos_text}" "SPDX-License-Identifier: Apache-2.0" nsos_spdx)
if(nsos_spdx EQUAL -1)
    message(FATAL_ERROR "${nsos_source} has no Apache-2.0 SPDX line to keep")
endif()

# Each anchor must appear exactly once. The texts hold semicolons, so they are not a CMake list.
function(controller_nsos_edit anchor replacement)
    string(FIND "${nsos_text}" "${anchor}" first)
    string(FIND "${nsos_text}" "${anchor}" last REVERSE)
    if(first EQUAL -1 OR NOT first EQUAL last)
        message(FATAL_ERROR "nsos_adapt.c: the anchor must appear once: ${anchor}")
    endif()
    string(REPLACE "${anchor}" "${replacement}" edited "${nsos_text}")
    set(nsos_text "${edited}" PARENT_SCOPE)
endfunction()
controller_nsos_edit("\tMAP_POLL_EPOLL(POLLHUP, EPOLLHUP);\n"
    "\tMAP_POLL_EPOLL(POLLHUP, EPOLLHUP);\n\tif (events_to & EPOLLIN) {\n\t\tevents_to |= EPOLLRDHUP;\n\t}\n")
controller_nsos_edit("\tMAP_POLL_EPOLL(EPOLLHUP, POLLHUP);\n"
    "\tMAP_POLL_EPOLL(EPOLLHUP, POLLHUP);\n\tMAP_POLL_EPOLL(EPOLLRDHUP, POLLHUP);\n")
set(nsos_copy "${CMAKE_CURRENT_BINARY_DIR}/nsos_adapt_rdhup.c")
file(WRITE "${nsos_copy}" "/* Changed copy of Zephyr v4.5.0 drivers/net/nsos_adapt.c, made by\n"
    " * tests/framework/interactive/nsos_rdhup.cmake of crux-controller: it also reports EPOLLRDHUP as POLLHUP.\n"
    " */\n${nsos_text}")

get_target_property(nsos_sources native_simulator INTERFACE_SOURCES)
list(FIND nsos_sources "${nsos_source}" nsos_index)
if(nsos_index EQUAL -1)
    message(FATAL_ERROR "native_simulator does not list nsos_adapt.c: ${nsos_sources}")
endif()
list(REMOVE_AT nsos_sources ${nsos_index})
list(APPEND nsos_sources "${nsos_copy}")
set_property(TARGET native_simulator PROPERTY INTERFACE_SOURCES "${nsos_sources}")
# The copy includes the driver's own headers, which sit beside the original.
target_compile_options(native_simulator INTERFACE "-I${ZEPHYR_BASE}/drivers/net")
