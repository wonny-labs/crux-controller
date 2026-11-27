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
target_link_libraries(app PRIVATE controller::framework crux::file crux::configuration crux::logging)
controller_framework_image()
