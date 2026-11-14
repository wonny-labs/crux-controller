# SPDX-License-Identifier: Apache-2.0

# The adapter zone of the workload as a library of its own. It implements the port that app/src
# declares (workload_os.h) with Zephyr kernel calls, so it is the only target that needs the
# kernel header, and the application target gets no include path to it: the boundary check reads
# includes, this file keeps the build in line with it. The library needs the Zephyr headers of the
# image (zephyr_interface) and the workload library, whose header the port header includes. The
# one source includes the port header with a relative quoted path, so no include directory is
# added either.
add_library(os STATIC workload_os_zephyr.c)
target_link_libraries(os PRIVATE zephyr_interface workload)
target_compile_options(os PRIVATE -Wall -Wextra -Werror)
