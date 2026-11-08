# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_s2_native_sim LANGUAGES C)

# The test builds the application's own exchange code, not a copy of it. The peer address
# and port are Kconfig values in the image, so the test defines them.
get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
add_subdirectory(${controller_root}/workload workload)
target_sources(app PRIVATE src/test_s2.c ${controller_root}/app/src/net_client.c)
target_include_directories(app PRIVATE ${controller_root}/app/src)
target_compile_definitions(app PRIVATE
    CONFIG_CRUX_CONTROLLER_PEER_ADDRESS="127.0.0.1"
    CONFIG_CRUX_CONTROLLER_PEER_PORT=42431)
target_link_libraries(app PRIVATE workload crux::sockets crux::netif)
