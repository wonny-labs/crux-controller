# SPDX-License-Identifier: Apache-2.0

# The base image on native_sim for a person at the host: HTTPS management on the host's loopback
# address, Crux Logging on standard output and the Crux serial console on a pseudo-terminal
# (docs/native-sim-interactive.md). It is built as a product builds the base image: the framework is
# the Zephyr module of this repository, turned on by CONFIG_CRUX_CONTROLLER_FRAMEWORK, and this file
# names no source or include directory of the framework. It is for development only. The entropy is
# the simulator's test source, so a key made here protects nothing, and the build refuses any other
# board; a board image of the framework includes framework/management/entropy.cmake, which refuses a
# test source.

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_interactive_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "The interactive configuration is for native_sim only: its entropy source is a test source")
endif()
if(NOT CONFIG_CRUX_WEB_BIND_ADDRESS STREQUAL "127.0.0.1")
    message(FATAL_ERROR "The interactive configuration listens on the host's loopback address only: "
                        "CONFIG_CRUX_WEB_BIND_ADDRESS must be \"127.0.0.1\"")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL)
    message(FATAL_ERROR "The interactive configuration needs the framework with web management and the serial command line")
endif()

# Interim, development only: native_sim's offload reports a client's FIN so that a close without a TLS
# close_notify does not spin the web server (nsos_rdhup.cmake, docs/native-sim-interactive.md).
include(${CMAKE_CURRENT_LIST_DIR}/nsos_rdhup.cmake)

target_sources(app PRIVATE src/interactive.c)
target_link_libraries(app PRIVATE controller::framework)
controller_framework_image()
