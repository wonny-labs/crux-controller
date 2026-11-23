# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_system_native_sim LANGUAGES C)

# The test builds the application's own glue and policy, not copies of them, against the real
# Crux System provider. On native_sim that provider has no watchdog device, so the watchdog start
# is refused as not supported; the boot line and the unavailable watchdog are what this scenario
# can show. Each scenario of testcase.yaml selects one case through SYSTEM_CASE, so that every case
# starts from a fresh image: Crux System allows one watchdog start per boot.
get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
target_sources(app PRIVATE src/test_system.c
               ${controller_root}/app/src/health.c ${controller_root}/app/src/health_policy.c)
target_include_directories(app PRIVATE ${controller_root}/app/src)
target_link_libraries(app PRIVATE crux::system crux::logging)
if(NOT DEFINED SYSTEM_CASE)
    message(FATAL_ERROR "SYSTEM_CASE is not set: run this test through its testcase.yaml")
endif()
target_compile_definitions(app PRIVATE SYSTEM_CASE_${SYSTEM_CASE}=1)

# The application's own sources keep the application's warning level.
set_source_files_properties(${controller_root}/app/src/health.c
                            ${controller_root}/app/src/health_policy.c
                            PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")
