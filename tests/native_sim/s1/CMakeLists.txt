# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_s1_native_sim)

# The test builds the application's own domain source and its own adapter zone (the build file of
# app/os adds the real adapter source to this target), not copies of them. The thread and queue
# calls are in the zone, so no Crux Thread or Queue library is linked.
get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
add_subdirectory(${controller_root}/workload workload)
add_subdirectory(${controller_root}/app/os os)
target_sources(app PRIVATE src/test_s1.c ${controller_root}/app/src/workload_thread.c)
target_include_directories(app PRIVATE ${controller_root}/app/src)
target_link_libraries(app PRIVATE workload crux::time crux::logging)

# The application's own source keeps the application's warning level.
set_source_files_properties(${controller_root}/app/src/workload_thread.c
                            PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")
