# SPDX-License-Identifier: Apache-2.0

# The held-application scenario of the controller framework on native_sim: the fixture application
# of ../fixture in the production watchdog configuration with no watchdog (criterion 19). This file
# names no source or include directory of the framework.

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_application_held_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim: its entropy source is a test source")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
   OR CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG OR CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION
   OR CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG OR CONFIG_TASK_WDT_HW_FALLBACK)
    message(FATAL_ERROR "The held-application scenario needs the production watchdog configuration "
                        "with no watchdog")
endif()

target_sources(app PRIVATE src/test_application_held.c ../fixture/fixture.c ../common/scenario.c)
target_include_directories(app PRIVATE ../common ../fixture)
target_link_libraries(app PRIVATE controller::framework crux::file crux::configuration crux::logging)
controller_framework_image()
