# SPDX-License-Identifier: Apache-2.0

# The scenario of the controller framework on native_sim with no watchdog and the option that allows
# operation without one: a startup step that passes its deadline ends in a software reset, and the
# next boot reports the record. The framework is the Zephyr module of this repository with health
# supervision only; this file names no source or include directory of the module. The test-only
# retained memory and the helpers of the scenarios are in ../common.

cmake_minimum_required(VERSION 3.20.0)
list(APPEND DTS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../common")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_no_watchdog_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION OR NOT CONFIG_CRUX_CONTROLLER_START_WITHOUT_WATCHDOG
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION OR CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG)
    message(FATAL_ERROR "The scenario needs supervision without a watchdog, the option that allows it, and fault injection")
endif()

target_sources(app PRIVATE src/test_no_watchdog.c ../common/scenario.c ../common/retained_env.c)
target_include_directories(app PRIVATE ../common)
target_link_libraries(app PRIVATE controller::framework)
