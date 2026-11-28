# SPDX-License-Identifier: Apache-2.0

# The storage scenario of the controller framework on native_sim: LittleFS on the flash simulator, the
# size limit of the application data root (criterion 24), the factory reset with a power cut before
# the erase (criterion 42) and failed logins (criterion 43). The scenario's main() is the application:
# it passes its own descriptor and writes under its data root through Crux File, as a product would.
# This file names no source or include directory of the framework.

cmake_minimum_required(VERSION 3.20.0)
list(APPEND DTS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../common")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_framework_storage_native_sim LANGUAGES C)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim: its entropy source is a test source")
endif()
if(NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_SUPERVISION OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_REBOOT
   OR NOT CONFIG_CRUX_CONTROLLER_FRAMEWORK_MANAGEMENT OR NOT CONFIG_CRUX_FILE_SIMULATOR
   OR NOT CONFIG_FILE_SYSTEM_LITTLEFS OR NOT CONFIG_CRUX_SYSTEM_NATIVE_SIM_WATCHDOG)
    message(FATAL_ERROR "The storage scenario needs supervision, Crux Reboot, web management, LittleFS "
                        "on the flash simulator and the simulated watchdog")
endif()

target_sources(app PRIVATE src/test_storage.c ../common/scenario.c ../common/retained_env.c
    ../common/https.c)
target_include_directories(app PRIVATE ../common)
# crux::security_event: the scenario waits for the event drain before a line that follows events.
target_link_libraries(app PRIVATE controller::framework crux::access crux::file crux::config_service
    crux::credential_store crux::logging crux::security_event)
# Test-only: Crux's account erase resolves to __wrap_crux_credential_erase_accounts in
# src/test_storage.c, which cuts the power in boot 1, before anything is erased, and calls Crux's
# erase in the other boots. GNU ld's --wrap, as the application scenario wraps the TLS start.
target_link_options(app PUBLIC -Wl,--wrap=crux_credential_erase_accounts)
# Test-only: the session creation of Crux Access for channel adapters, which no product reaches, so
# that the test can make an account of the read-only role and save the configuration in the
# administrator's name. PRIVATE to this test image, as in the application scenario.
target_include_directories(app PRIVATE "${ZEPHYR_CRUX_MODULE_DIR}/components/access/adapter")
controller_framework_image()
