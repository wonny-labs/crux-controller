#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run a shell, or one command, in the dev container without VS Code. It needs Docker Engine and
# nothing else of Docker (no Docker Desktop): Docker Engine inside a WSL2 distribution is enough.
#
#   scripts/dev-shell.sh                      an interactive shell in the repository
#   scripts/dev-shell.sh <command> [args...]  one command, with the repository as working directory
#
# It builds the image of .devcontainer/Dockerfile, mounts the parent folder of the clone as the
# west workspace at /workspaces/ws, and runs scripts/bootstrap.sh zephyr (which runs .devcontainer/setup.sh) before the command. The first run
# fetches Zephyr, the west modules and the Zephyr SDK (a long time, several GiB); later runs find
# them in the workspace folder and in a Docker volume of that workspace folder, named
# crux-controller-dev-cache-<number>. Each workspace folder has its own, so that two workspaces with
# different Zephyr requirements do not share one virtual environment.
#
# The container gets the USB bus of the host when /dev/bus/usb exists (CRUX_BOARD_USB_DIR names another folder),
# with a device cgroup rule for USB devices (character major 189) and nothing else; it is never privileged.
# The SEGGER J-Link software is installed when the build arguments name a package: a file in
# .devcontainer/jlink/packages/, or CRUX_JLINK_URL with CRUX_JLINK_DEB_SHA256 in the environment (passed by
# name only). Without either the image builds without it.
#
# CRUX_DEV_IMAGE overrides the image name. GH_TOKEN, when set, is passed to the container for the
# SDK download. See docs/dev-container.md, "Network and prerequisites".
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/.." && pwd)"
workspace="$(dirname "$repo")"
image="${CRUX_DEV_IMAGE:-crux-controller-dev}"
volume_prefix="crux-controller-dev-cache"

if [[ "$(id -u)" -eq 0 ]]; then
    printf 'dev-shell: run this as your normal user, not as root. The files of the workspace would belong to root.\n' >&2
    exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
    printf 'dev-shell: docker is not installed. Install Docker Engine (docs/getting-started.md, "Dev Container").\n' >&2
    exit 2
fi
if [[ "$(basename "$repo")" != "crux-controller" ]]; then
    printf 'dev-shell: the clone must be in a folder named crux-controller, and it is in %s.\n' "$(basename "$repo")" >&2
    exit 2
fi

volume="$volume_prefix-$(printf '%s' "$workspace" | cksum | cut -d' ' -f1)"
usb_dir="${CRUX_BOARD_USB_DIR:-/dev/bus/usb}"

# The J-Link build arguments go by name, so that a hosted URL does not appear on the command line.
build_args=()
for name in CRUX_JLINK CRUX_JLINK_DEB CRUX_JLINK_DEB_SHA256 CRUX_JLINK_URL; do
    if [[ -n "${!name:-}" ]]; then
        build_args+=(--build-arg "$name")
    fi
done

docker build --platform linux/amd64 \
    --build-arg "USER_UID=$(id -u)" --build-arg "USER_GID=$(id -g)" \
    ${build_args[@]+"${build_args[@]}"} \
    -t "$image" "$repo/.devcontainer"

flags=(--rm --platform linux/amd64 --user vscode
    -v "$workspace:/workspaces/ws" -v "$volume:/opt/crux-cache"
    -w /workspaces/ws/crux-controller)
if [[ -d "$usb_dir" ]]; then
    flags+=(-v "$usb_dir:/dev/bus/usb" --device-cgroup-rule "c 189:* rmw")
fi
if [[ -t 0 && -t 1 ]]; then
    flags+=(-it)
elif [[ ! -t 0 ]]; then
    # A piped command, for example: scripts/dev-shell.sh bash -s < script.sh
    flags+=(-i)
fi
if [[ -n "${GH_TOKEN:-}" ]]; then
    flags+=(-e GH_TOKEN)
fi

if (($# == 0)); then
    set -- bash
fi
exec docker run "${flags[@]}" "$image" \
    bash -c 'bash scripts/bootstrap.sh zephyr </dev/null && exec "$@"' dev-shell "$@"
