# SPDX-License-Identifier: Apache-2.0

# Portable core of the synthetic workload. Plain C17, no Crux, Zephyr or vendor include.
# Under Zephyr it is a Zephyr library, so that it is built with the image's compiler flags.
set(workload_sources src/config_record.c src/cycle.c src/message.c)

if(DEFINED ZEPHYR_BASE)
    zephyr_library_named(workload)
    zephyr_library_sources(${workload_sources})
else()
    add_library(workload STATIC ${workload_sources})
    target_compile_features(workload PUBLIC c_std_17)
endif()
target_include_directories(workload PUBLIC include)
