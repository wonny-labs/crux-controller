#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Check the folder layout on the host before the dev container is created. VS Code runs it as the
# initializeCommand of devcontainer.json, and scripts/dev-shell.sh runs it before it builds the image.
# It needs only bash and the coreutils, so it also runs in a bare WSL distribution.
#
# The dev container mounts the PARENT folder of the clone as the west workspace, and west init puts
# .west, zephyr/ and modules/ into it. So the parent folder must be a folder of its own:
#
#   <workspace>/crux-controller     the clone, named exactly so (west.yml, self: path)
#   <workspace>/.west, zephyr, modules, ...   created by .devcontainer/setup.sh
#
# It refuses (exit status 2) when the clone has another name, when the parent folder is the home
# directory or the root directory, or when the parent folder holds a home directory marker. It only
# warns when the parent folder holds other entries, because they become visible in the container
# and a west update or a clean-up in it should not meet somebody else's files.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
workspace="$(dirname "$repo")"

refuse() {
    printf 'check-host: %s\n' "$*" >&2
    exit 2
}

[[ "$(basename "$repo")" == "crux-controller" ]] \
    || refuse "the clone is in a folder named '$(basename "$repo")'. It must be named crux-controller (west.yml, self: path). Clone it as <workspace>/crux-controller."

if [[ "$workspace" == "/" ]]; then
    refuse "the clone is directly in the root directory. Put it in a folder of its own, for example ~/work/controller-ws/crux-controller, because the whole parent folder is mounted into the container."
fi

home_physical=""
if [[ -n "${HOME:-}" && -d "$HOME" ]]; then
    home_physical="$(cd "$HOME" && pwd -P)"
fi
if [[ -n "$home_physical" && "$workspace" == "$home_physical" ]]; then
    refuse "the parent folder '$workspace' is your home directory. Put the clone in a folder of its own, for example ~/work/controller-ws/crux-controller, because the whole parent folder is mounted into the container and west init puts .west, zephyr/ and modules/ next to the clone."
fi

for marker in .ssh .gnupg .bashrc .profile .gitconfig; do
    if [[ -e "$workspace/$marker" ]]; then
        refuse "the parent folder '$workspace' looks like a home directory ($marker is in it). Put the clone in a folder of its own, for example ~/work/controller-ws/crux-controller, because the whole parent folder is mounted into the container."
    fi
done

others=""
shopt -s nullglob dotglob
for entry in "$workspace"/*; do
    name="${entry##*/}"
    case "$name" in
        crux-controller | .west | zephyr | modules | bootloader | tools | crux-pilot | twister-out*) ;;
        *) others="$others $name" ;;
    esac
done
if [[ -n "$others" ]]; then
    printf "check-host: warning: the parent folder '%s' also holds:%s\n" "$workspace" "$others" >&2
    printf 'check-host: warning: the container sees all of it. A folder of its own for the clone avoids surprises.\n' >&2
fi
