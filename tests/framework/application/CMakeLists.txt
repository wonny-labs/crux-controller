# SPDX-License-Identifier: Apache-2.0

# The application scenario of the controller framework on native_sim: the fixture application of
# ../fixture with its own main(), prj.conf and descriptor, built with the framework as a Zephyr module,
# as a product builds it (criterion 4). This file names no source or include directory of the
# framework; the fixture reaches it through <controller/NAME.h> and the Kconfig symbols only.

cmake_minimum_required(VERSION 3.20.0)
list(APPEND DTS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../common")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_application_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim: its entropy source is a test source")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION
   OR NOT CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG)
    message(FATAL_ERROR "The application scenario needs supervision, Crux Reboot, web management, fault "
                        "injection and the simulated watchdog")
endif()

target_sources(app PRIVATE src/test_application.c ../fixture/fixture.c ../common/scenario.c
    ../common/retained_env.c ../common/https.c)
target_include_directories(app PRIVATE ../common ../fixture)
target_link_libraries(app PRIVATE controller::framework crux::access crux::file crux::configuration
    crux::logging crux::tls_certificate)
# Test-only: Crux's TLS certificate start resolves to __wrap_crux_tls_certificate_start in
# src/test_application.c, which refuses it in boot 11 and calls Crux's start in the other boots. GNU
# ld's --wrap, as Zephyr's own native-based tests use it (tests/bsim/bluetooth/host/iso/frag).
target_link_options(app PUBLIC -Wl,--wrap=crux_tls_certificate_start)
# Test-only: the session creation of Crux Access for channel adapters, which no product reaches,
# so that the test can make an account of the read-only role. Crux offers no command or route for
# a second account. PRIVATE to this test image; Crux checks only its public targets for this header.
target_include_directories(app PRIVATE "${ZEPHYR_CRUX_MODULE_DIR}/components/access/adapter")
controller_framework_image()
