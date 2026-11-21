#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run a shell, or one command, in the optional board container without VS Code: the dev container plus
# the SEGGER J-Link software, with the USB bus of the host. UNTESTED on hardware and on WSL2: nobody has
# reached a probe with it. docs/board-bring-up.md is the route, and no command run through this script
# may touch a board without the project owner's explicit authorisation for the task.
#
#   scripts/board-shell.sh                      an interactive shell in the repository
#   scripts/board-shell.sh <command> [args...]  one command, with the repository as working directory
#
# Before it calls Docker it checks that exactly one JLink_Linux_<version>_x86_64.deb, downloaded by you,
# is in .devcontainer/board/jlink/, and that the USB bus folder exists (/dev/bus/usb; under WSL2 it
# appears once a device is attached with usbipd). CRUX_BOARD_USB_DIR overrides that folder.
#
# It builds the default image with .devcontainer/board/build-base.sh, builds the board layer of
# .devcontainer/board/Dockerfile on it, and runs .devcontainer/setup.sh before the command, as
# scripts/dev-shell.sh does. It uses the same cache volume as scripts/dev-shell.sh for the same workspace
# folder, so the Zephyr SDK is not fetched again. The USB bus is bind-mounted and opened with a device
# cgroup rule for USB devices (character major 189); the container is never privileged.
#
# CRUX_DEV_IMAGE and CRUX_BOARD_IMAGE override the image names. GH_TOKEN, when set, is passed on.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/.." && pwd)"
workspace="$(dirname "$repo")"
image="${CRUX_DEV_IMAGE:-crux-controller-dev}"
board_image="${CRUX_BOARD_IMAGE:-crux-controller-board}"
usb_dir="${CRUX_BOARD_USB_DIR:-/dev/bus/usb}"
volume_prefix="crux-controller-dev-cache"

refuse() {
    printf 'board-shell: %s\n' "$*" >&2
    exit 2
}

[[ "$(id -u)" -ne 0 ]] || refuse "run this as your normal user, not as root."
command -v docker >/dev/null 2>&1 \
    || refuse "docker is not installed. Install Docker Engine (docs/try-on-native-sim.md, \"Dev container\")."
[[ "$(basename "$repo")" == "crux-controller" ]] \
    || refuse "the clone must be in a folder named crux-controller, and it is in $(basename "$repo")."

shopt -s nullglob
packages=("$repo"/.devcontainer/board/jlink/JLink_Linux_*_x86_64.deb)
shopt -u nullglob
((${#packages[@]} == 1)) \
    || refuse "put exactly one JLink_Linux_<version>_x86_64.deb, downloaded by you from SEGGER, into .devcontainer/board/jlink/ (found ${#packages[@]}). See docs/board-bring-up.md."
[[ -d "$usb_dir" ]] \
    || refuse "$usb_dir does not exist. Attach the probe first (under WSL2: usbipd attach --wsl --busid <busid>, docs/board-bring-up.md)."

volume="$volume_prefix-$(printf '%s' "$workspace" | cksum | cut -d' ' -f1)"

CRUX_DEV_IMAGE="$image" bash "$repo/.devcontainer/board/build-base.sh"
docker build --platform linux/amd64 --build-arg "BASE_IMAGE=$image" \
    -t "$board_image" "$repo/.devcontainer/board"

flags=(--rm --platform linux/amd64 --user vscode
    -v "$workspace:/workspaces/ws" -v "$volume:/opt/crux-cache"
    -v "$usb_dir:/dev/bus/usb" --device-cgroup-rule "c 189:* rmw"
    -w /workspaces/ws/crux-controller)
if [[ -t 0 && -t 1 ]]; then
    flags+=(-it)
elif [[ ! -t 0 ]]; then
    flags+=(-i)
fi
if [[ -n "${GH_TOKEN:-}" ]]; then
    flags+=(-e GH_TOKEN)
fi

if (($# == 0)); then
    set -- bash
fi
exec docker run "${flags[@]}" "$board_image" \
    bash -c 'bash .devcontainer/setup.sh </dev/null && exec "$@"' board-shell "$@"
