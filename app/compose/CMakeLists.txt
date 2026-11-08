# SPDX-License-Identifier: Apache-2.0

# The composition zone of step S3 as a library of its own. It is the only target that links the
# File composition interface, so the application target gets no include path to it: the boundary
# check reads includes, this file keeps the build in line with it. The library needs the Zephyr
# headers of the image (zephyr_interface); the provider itself is selected by Kconfig and
# appended to the Zephyr link by Crux, not linked here. The one source includes the port header
# of app/src with a relative quoted path, so no include directory is added either.
add_library(compose STATIC storage_mount.c)
target_link_libraries(compose PRIVATE zephyr_interface crux::file_zephyr)
target_compile_options(compose PRIVATE -Wall -Wextra -Werror)
