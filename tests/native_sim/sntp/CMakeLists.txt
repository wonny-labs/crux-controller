# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_sntp_native_sim LANGUAGES C)

# The test builds the application's own glue, policy and adapter, not copies of them, against the
# real Crux Time provider and Zephyr's SNTP library. A UDP responder of the test answers on port
# 123 of the loopback interface. Each scenario of testcase.yaml selects one case through SNTP_CASE,
# so that every case starts from a fresh image: Crux Time keeps its state for the whole run. The
# product's settings are Kconfig values in the image, so the test defines them: a short timeout
# and a stale age of two seconds keep the cases fast.
get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
target_sources(app PRIVATE src/test_sntp.c
               ${controller_root}/app/src/time_sync.c
               ${controller_root}/app/src/time_sync_policy.c
               ${controller_root}/app/os/time_sync_zephyr.c)
target_include_directories(app PRIVATE ${controller_root}/app/src)
target_link_libraries(app PRIVATE crux::time crux::logging)
if(NOT DEFINED SNTP_CASE)
    message(FATAL_ERROR "SNTP_CASE is not set: run this test through its testcase.yaml")
endif()
target_compile_definitions(app PRIVATE
    SNTP_CASE_${SNTP_CASE}=1
    CONFIG_CRUX_CONTROLLER_TIME_SERVER="127.0.0.1"
    CONFIG_CRUX_CONTROLLER_TIME_INTERVAL_S=1
    CONFIG_CRUX_CONTROLLER_TIME_TIMEOUT_MS=600
    CONFIG_CRUX_CONTROLLER_TIME_STALE_AGE_S=2
    CONFIG_CRUX_CONTROLLER_TIME_THRESHOLD_MS=100
    CONFIG_CRUX_CONTROLLER_TIME_MAX_STEP_MS=1000
    CONFIG_CRUX_CONTROLLER_TIME_STACK=8192)

# The application's own sources keep the application's warning level.
set_source_files_properties(${controller_root}/app/src/time_sync.c
                            ${controller_root}/app/src/time_sync_policy.c
                            ${controller_root}/app/os/time_sync_zephyr.c
                            PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")
