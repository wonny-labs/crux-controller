# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(controller_file_native_sim LANGUAGES C)

# The test builds the application's own store and the composition zone, not copies of them.
# Each scenario of testcase.yaml selects one case through FILE_CASE, so that every case starts
# from a fresh image: File is bound once per program, and there is no unbind.
get_filename_component(controller_root "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
add_subdirectory(${controller_root}/workload workload)
add_subdirectory(${controller_root}/framework/compose compose)
target_sources(app PRIVATE src/test_file.c ${controller_root}/app/src/config_store.c)
target_include_directories(app PRIVATE ${controller_root}/app/src ${controller_root}/framework/src)
target_link_libraries(app PRIVATE workload compose crux::file)
if(NOT DEFINED FILE_CASE)
    message(FATAL_ERROR "FILE_CASE is not set: run this test through its testcase.yaml")
endif()
target_compile_definitions(app PRIVATE FILE_CASE_${FILE_CASE}=1)

# The application's own source keeps the application's warning level.
set_source_files_properties(${controller_root}/app/src/config_store.c
                            PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")
