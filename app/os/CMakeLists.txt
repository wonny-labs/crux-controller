# SPDX-License-Identifier: Apache-2.0

# The adapter zone. Its source, for every configuration, implements the port that app/src declares
# (workload_os.h) with Zephyr kernel calls. The adapter of the sntp capability is in the adapter
# zone of the framework module (framework/os), added by framework/configurations.cmake. Both are
# sources of the application target, not libraries of their own, as the application's other
# sources are: a static library of its own is linked after the kernel archive
# and the kernel objects that it needs (the message queue) are then not pulled in. No include path
# is added, so the application gets none from the zone: the boundary check reads includes, this file
# keeps the build in line with it. A source includes its port header with a relative quoted path,
# and the header of the workload port includes workload.h, which comes from the workload library
# that the application links. The warning level of the application applies to each source.
target_sources(app PRIVATE ${CMAKE_CURRENT_LIST_DIR}/workload_os_zephyr.c)
set_source_files_properties(${CMAKE_CURRENT_LIST_DIR}/workload_os_zephyr.c
                            TARGET_DIRECTORY app
                            PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")

