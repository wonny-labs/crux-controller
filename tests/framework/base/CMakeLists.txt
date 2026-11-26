# SPDX-License-Identifier: Apache-2.0

# The base composition of the controller framework on native_sim, built as a product builds it:
# the framework is the Zephyr module of this repository, turned on by CONFIG_CRUX_CONTROLLER_FRAMEWORK
# in prj.conf. This file names no source and no include directory of this repository. It links the
# interface target of the module and calls the module's image function, which adds the route table
# and the packaged page of web management to the target app, as the base image does.

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_base_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim: its entropy source is a test source")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC)
    message(FATAL_ERROR "The base scenario needs the framework with web management and time synchronisation")
endif()

target_sources(app PRIVATE src/test_base.c)
target_link_libraries(app PRIVATE controller::framework)
controller_framework_image()
