# SPDX-License-Identifier: Apache-2.0

# Portable core of the synthetic workload. Plain C17, no Crux, Zephyr or vendor include.
add_library(workload STATIC src/config_record.c src/cycle.c src/message.c)
target_include_directories(workload PUBLIC include)
target_compile_features(workload PUBLIC c_std_17)
