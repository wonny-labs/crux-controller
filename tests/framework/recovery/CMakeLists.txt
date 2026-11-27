# SPDX-License-Identifier: Apache-2.0

# The recovery scenario of the controller framework on native_sim: the base composition with the
# simulated watchdog of Crux System, a retained region that survives the restart of the simulated
# process, and fault injection, over six boots of one run. The framework is the Zephyr module of
# this repository, turned on by CONFIG_CRUX_CONTROLLER_FRAMEWORK in prj.conf; this file names no
# source or include directory of the module. The test-only retained memory and the helpers of the
# scenarios are in ../common.

cmake_minimum_required(VERSION 3.20.0)
list(APPEND DTS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../common")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_recovery_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim: its entropy source is a test source")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_FAULT_INJECTION OR NOT CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG)
    message(FATAL_ERROR "The recovery scenario needs supervision, Crux Reboot, fault injection and the simulated watchdog")
endif()

target_sources(app PRIVATE src/test_recovery.c ../common/scenario.c ../common/retained_env.c)
target_include_directories(app PRIVATE ../common)
target_link_libraries(app PRIVATE controller::framework)
controller_framework_image()
