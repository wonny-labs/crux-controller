# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_management_native_sim LANGUAGES C)

# The scenario builds the product's own files, not copies of them: the route wiring and the packaged
# page (app/management/management.cmake, which names Crux's route sources and calls its route and
# asset functions), the composition zone with the start sequence (app/compose) and the policy. It
# needs the Mbed TLS modules of Crux's optional group, so it lives beside tests/native_sim and not in
# it, and only the management job selects it, in a workspace that has the group switched on.
#
# The simulator's entropy source is a fake one, so a key made here means nothing. That is why this
# file does not include app/management/entropy.cmake, which refuses a test source, and why it
# refuses any other board.
get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

if(NOT CONFIG_BOARD_NATIVE_SIM OR NOT CONFIG_FAKE_ENTROPY_NATIVE_SIM)
    message(FATAL_ERROR "This scenario is restricted to native_sim: its entropy source is a test source")
endif()

add_subdirectory(${controller_root}/app/compose compose)
target_sources(app PRIVATE src/test_management.c ${controller_root}/app/src/management_policy.c)
target_include_directories(app PRIVATE ${controller_root}/app/src)
target_link_libraries(app PRIVATE crux::web compose)
include(${controller_root}/app/management/management.cmake)

# The application's own sources keep the application's warning level. Crux's route sources and the
# generated route table compile with the flags of the target and not with -Werror here, so that the
# warnings of the host compiler on Crux's sources do not hide the handshake. The board image of the
# management job compiles them with -Werror, as the application target does there.
set_source_files_properties(${controller_root}/app/src/management_policy.c
                            PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")
