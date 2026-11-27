# SPDX-License-Identifier: Apache-2.0

# The scenario of a refused TLS certificate start on native_sim (specification section 4.1): the
# fixture application of ../fixture with the configuration service as a start prerequisite. This
# file names no source or include directory of the framework.

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_tls_refused_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim: its entropy source is a test source")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
   OR NOT CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG
   OR NOT CONFIG_CRUX_CONTROLLER_PREREQUISITE_CONFIGURATION)
    message(FATAL_ERROR "The scenario needs supervision, web management, the reboot thread, the serial "
                        "command line, start without a watchdog and the configuration prerequisite")
endif()

target_sources(app PRIVATE src/test_tls_refused.c ../fixture/fixture.c ../common/scenario.c)
target_include_directories(app PRIVATE ../common ../fixture)
target_link_libraries(app PRIVATE controller::framework crux::file crux::configuration crux::logging
    crux::tls_certificate)
# Test-only: the TLS certificate start of Crux resolves to __wrap_crux_tls_certificate_start in
# src/test_tls_refused.c, which refuses it. GNU ld's --wrap, as Zephyr's own native-based tests use
# it (tests/bsim/bluetooth/host/iso/frag/CMakeLists.txt). No framework source changes for the test.
target_link_options(app PUBLIC -Wl,--wrap=crux_tls_certificate_start)
controller_framework_image()
