# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(crux_controller)

target_sources(app PRIVATE src/main.c src/composition.c)
target_link_libraries(app PRIVATE crux::time)
target_compile_options(app PRIVATE -Wall -Wextra -Werror)

# Step S1 and later: the workload on Crux threads. Its portable core is a library of this
# repository, so the application takes no include path of its own.
if(CONFIG_CRUX_THREAD)
    add_subdirectory(../workload workload)
    target_sources(app PRIVATE src/workload_thread.c)
    target_link_libraries(app PRIVATE workload crux::thread crux::queue crux::logging)
endif()
