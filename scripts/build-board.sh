#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Board build of one build configuration of app/ for the RT1060-EVKB, for the VS Code tasks and debug profiles.
#
#   scripts/build-board.sh <configuration>   build it in build/<configuration>
#   scripts/build-board.sh --clean           delete every build/<configuration> and the current build link
#
# The CMake arguments of each configuration are those of the Budget job (.github/workflows/budget.yml), with the
# baseline gate required; a tooling test compares them. They are passed only when the build folder has no build
# system yet: extra arguments make west configure again, and the folder keeps them in its CMake cache, so a later
# run is an incremental build. After a successful build, the link build/mimxrt1060_evk_B_qspi--current points at
# the folder just built, and the VS Code profiles and the task Board: Flash use the image behind it. A failed
# build leaves the link as it was. The script runs from the repository root wherever it is started. It never
# flashes or touches a board.
set -euo pipefail

board='mimxrt1060_evk@B//qspi'
link='mimxrt1060_evk_B_qspi--current'
configurations=(base workload net file system sntp management)

usage() {
    printf 'Usage: %s <configuration> | --clean\n' "$0" >&2
    printf '       configurations: %s\n' "${configurations[*]}" >&2
    exit 2
}

[[ $# -eq 1 ]] || usage
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "$1" == --clean ]]; then
    for name in "${configurations[@]}"; do
        rm -rf -- "build/$name"
    done
    rm -f -- "build/$link"
    exit 0
fi

conf=""
overlay=""
case "$1" in
    base) ;;
    workload) conf="conf/workload.conf" ;;
    net)
        conf="conf/workload.conf;conf/net.conf"
        overlay="boards/net.overlay"
        ;;
    file)
        conf="conf/workload.conf;conf/file.conf"
        overlay="boards/file.overlay"
        ;;
    system)
        conf="conf/workload.conf;conf/system.conf"
        overlay="boards/system.overlay"
        ;;
    sntp)
        conf="conf/workload.conf;conf/net.conf;conf/sntp.conf"
        overlay="boards/net.overlay"
        ;;
    management)
        conf="conf/workload.conf;conf/net.conf;conf/management.conf"
        overlay="boards/net.overlay;boards/management.overlay"
        ;;
    *) usage ;;
esac
name="$1"
build="build/$name"

if [[ -d "build/$link" && ! -L "build/$link" ]]; then
    printf 'build-board: build/%s is a folder, not a link; move it away, then run this again\n' "$link" >&2
    exit 1
fi

cmake_args=()
if [[ ! -f "$build/build.ninja" ]]; then
    cmake_args=(-- -DCRUX_REQUIRE_VERIFIED_ZEPHYR=ON)
    [[ -z "$conf" ]] || cmake_args+=("-DEXTRA_CONF_FILE=$conf")
    [[ -z "$overlay" ]] || cmake_args+=("-DEXTRA_DTC_OVERLAY_FILE=$overlay")
fi

west build --pristine=never -b "$board" -d "$build" app ${cmake_args[@]+"${cmake_args[@]}"}

if [[ ! -f "$build/zephyr/zephyr.elf" ]]; then
    printf 'build-board: the build produced no %s\n' "$build/zephyr/zephyr.elf" >&2
    exit 1
fi
rm -f -- "build/$link"
ln -s "$name" "build/$link"
printf 'build-board: %s built; build/%s points at it\n' "$name" "$link"
