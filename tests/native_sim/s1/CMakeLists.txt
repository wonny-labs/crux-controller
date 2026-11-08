# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_s1_native_sim)

# The test builds the application's own adapter source, not a copy of it.
get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
add_subdirectory(${controller_root}/workload workload)
target_sources(app PRIVATE src/test_s1.c ${controller_root}/app/src/workload_thread.c)
target_include_directories(app PRIVATE ${controller_root}/app/src)
target_link_libraries(app PRIVATE workload crux::thread crux::queue crux::time crux::logging)
