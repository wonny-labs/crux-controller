# SPDX-License-Identifier: Apache-2.0

# The fixture product's application on native_sim. It is built in its own west workspace, where
# crux-controller is a project and so a Zephyr module that west finds: this file names no path,
# source or include directory of crux-controller and adds no module. It links the interface target
# of the framework and calls the framework's image function, as a product image does.

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_product_integration LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "The fixture product is restricted to native_sim: its entropy source is a test source")
endif()
# An unmet Kconfig dependency only warns, and would build an image without the service.
if(NOT CONFIG_ZEPHYR_CRUX_CONTROLLER_MODULE OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_CLI_SERIAL
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_TIME_SYNC)
    message(FATAL_ERROR "The fixture product needs the framework module with web management, the serial "
                        "command line and time synchronisation")
endif()

target_sources(app PRIVATE src/test_product_import.c)
target_link_libraries(app PRIVATE controller::framework)
controller_framework_image()
