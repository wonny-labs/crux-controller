# SPDX-License-Identifier: Apache-2.0

# The adapter zone of the workload: one source that implements the port that app/src declares
# (workload_os.h) with Zephyr kernel calls. It is a source of the application target, not a library
# of its own, as the application's other sources are: a static library of its own is linked after
# the kernel archive and the kernel objects that it needs (the message queue) are then not pulled
# in. No include path is added, so the application gets none from the zone: the boundary check reads
# includes, this file keeps the build in line with it. The source includes the port header with a
# relative quoted path, and the header's own include of workload.h comes from the workload library
# that the application links. The warning level of the application applies to this source.
target_sources(app PRIVATE ${CMAKE_CURRENT_LIST_DIR}/workload_os_zephyr.c)
set_source_files_properties(${CMAKE_CURRENT_LIST_DIR}/workload_os_zephyr.c
                            TARGET_DIRECTORY app
                            PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror")
