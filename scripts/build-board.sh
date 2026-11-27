#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Board build of one build configuration of app/, for the VS Code tasks and debug profiles.
#
#   scripts/build-board.sh [--board <board>] <configuration>   build it in build/<board folder>/<configuration>
#   scripts/build-board.sh [--board <board>] --clean           delete build/<board folder>, and the current build
#                                                             link if it points into that folder
#
# The VS Code tasks pass the setting crux.board as --board. The board is --board, else the environment variable
# CRUX_BOARD_TARGET (the name that Crux's scripts use), else west's own setting build.board (`west config
# build.board`), else the default board below. The board folder is the board name with each run of characters other
# than letters, digits, '_', '.' and '-' replaced by one '_' (Crux's rule for its board key, so crux.boardKey of
# .vscode/settings.json is this folder name); board_folder() below is the only place that derives it. The folder
# follows the spelling given: mimxrt1060_evk@B//qspi and mimxrt1060_evk@B/mimxrt1062/qspi name the same board target
# but get different folders. west's build.dir-fmt is not used for it: its {board} keeps the '/' of the
# qualifiers and it has no field for the build configuration. A board folder holds the file .board-build; the script
# builds in, and --clean deletes, only a folder that holds it or does not exist yet, so a board name can never
# clean or reuse another folder of build/, such as build/host.
#
# The CMake arguments of each configuration are those of the Budget job (.github/workflows/budget.yml), with the
# baseline gate required; a tooling test compares them. They are passed only when the build folder has no build
# system yet: extra arguments make west configure again, and the folder keeps them in its CMake cache, so a later
# run is an incremental build. After a successful build, the link build/current points at the folder just built,
# and the VS Code profiles and the task Board: Flash use the image behind it; west flash reads the board from that
# build. A failed build leaves the link as it was. The script runs from the repository root wherever it is started.
# It never flashes or touches a board.
set -euo pipefail

default_board='mimxrt1060_evk@B/mimxrt1062/qspi'
link='current'
configurations=(minimal workload net file system sntp management base)

usage() {
    printf 'Usage: %s [--board <board>] <configuration> | [--board <board>] --clean\n' "$0" >&2
    printf '       configurations: %s\n' "${configurations[*]}" >&2
    exit 2
}

# The folder below build/ of a board target such as mimxrt1060_evk@B/mimxrt1062/qspi.
board_folder() {
    printf '%s' "$1" | sed -E 's/[^A-Za-z0-9_.-]+/_/g'
}

board=""
if [[ $# -ge 1 && "$1" == --board ]]; then
    [[ $# -ge 2 && -n "$2" ]] || usage
    board="$2"
    shift 2
fi
[[ $# -eq 1 ]] || usage
cd "$(dirname "${BASH_SOURCE[0]}")/.."

board="${board:-${CRUX_BOARD_TARGET:-}}"
if [[ -z "$board" ]]; then
    board="$(west config build.board 2>/dev/null || true)"
    board="${board:-$default_board}"
fi
# A Zephyr board target: board name, optional @revision, optional /qualifiers. Nothing else, because the name
# becomes a folder below build/.
if [[ ! "$board" =~ ^[A-Za-z0-9_]+(@[A-Za-z0-9_.]+)?(/[A-Za-z0-9_]*)*$ ]]; then
    printf 'build-board: %s is not a board target (board[@revision][/soc[/variant]])\n' "$board" >&2
    exit 2
fi
folder="build/$(board_folder "$board")"
marker="$folder/.board-build"
if [[ -e "$folder" && ! -f "$marker" ]] || [[ "$folder" == "build/$link" ]]; then
    printf 'build-board: %s is not a board folder of this script; pick another board name\n' "$folder" >&2
    exit 2
fi

if [[ "$1" == --clean ]]; then
    target="$(readlink "build/$link" 2>/dev/null || true)"
    if [[ -n "$target" && "build/${target%%/*}" == "$folder" ]]; then
        rm -f -- "build/$link"
    fi
    rm -rf -- "$folder"
    exit 0
fi

conf=""
overlay=""
case "$1" in
    minimal) ;;
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
    base)
        conf="conf/base.conf"
        overlay="boards/net.overlay;boards/management.overlay;boards/retained.overlay"
        ;;
    *) usage ;;
esac
name="$1"
build="$folder/$name"

if [[ -d "build/$link" && ! -L "build/$link" ]]; then
    printf 'build-board: build/%s is a folder, not a link; move it away, then run this again\n' "$link" >&2
    exit 1
fi

mkdir -p "$folder"
touch "$marker"
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
ln -s "${build#build/}" "build/$link"
printf 'build-board: %s for %s built; build/%s points at it\n' "$name" "$board" "$link"
