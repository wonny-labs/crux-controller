#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Check the folder layout on the host before the dev container is created. VS Code runs it as the
# initializeCommand of devcontainer.json. (scripts/dev-shell.sh does not call it yet.)
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

refuse() {
    printf 'check-host: %s\n' "$*" >&2
    exit 2
}

# check_layout <repo, symbolic links resolved> <repo, as it was reached>. The parent folder is looked
# at twice: a clone folder that is a symbolic link has a physical parent and a logical one (the folder
# the link is in), and a mount of <folder>/.. may resolve to either, so a home directory must be
# neither. .crux-extra-ca.crt is the optional certificate file of setup.sh and is not a stranger.
check_layout() {
    local repo="$1" logical_repo="$2" workspace logical_workspace resolved_logical
    local home_physical="" parent marker others name entry
    workspace="$(dirname "$repo")"
    logical_workspace="$(dirname "$logical_repo")"
    resolved_logical="$logical_workspace"
    if [[ -d "$logical_workspace" ]]; then
        resolved_logical="$(cd "$logical_workspace" && pwd -P)"
    fi

    [[ "$(basename "$repo")" == "crux-controller" ]] \
        || refuse "the clone is in a folder named '$(basename "$repo")'. It must be named crux-controller (west.yml, self: path). Clone it as <workspace>/crux-controller."

    if [[ "$workspace" == "/" || "$logical_workspace" == "/" ]]; then
        refuse "the clone is directly in the root directory. Put it in a folder of its own, for example ~/work/crux-controller-workspace/crux-controller, because the whole parent folder is mounted into the container."
    fi

    if [[ -n "${HOME:-}" && -d "$HOME" ]]; then
        home_physical="$(cd "$HOME" && pwd -P)"
    fi
    for parent in "$workspace" "$logical_workspace" "$resolved_logical"; do
        if [[ -n "$home_physical" && ( "$parent" == "$home_physical" || "$parent" == "${HOME%/}" ) ]]; then
            refuse "the parent folder '$parent' is your home directory. Put the clone in a folder of its own, for example ~/work/crux-controller-workspace/crux-controller, because the whole parent folder is mounted into the container and west init puts .west, zephyr/ and modules/ next to the clone."
        fi
    done

    for parent in "$workspace" "$logical_workspace"; do
        for marker in .ssh .gnupg .bashrc .profile .gitconfig; do
            if [[ -e "$parent/$marker" ]]; then
                refuse "the parent folder '$parent' looks like a home directory ($marker is in it). Put the clone in a folder of its own, for example ~/work/crux-controller-workspace/crux-controller, because the whole parent folder is mounted into the container."
            fi
        done
    done

    others=""
    shopt -s nullglob dotglob
    for entry in "$workspace"/*; do
        name="${entry##*/}"
        case "$name" in
            crux-controller | .west | zephyr | modules | bootloader | tools | crux-pilot | twister-out* | .crux-extra-ca.crt) ;;
            *) others="$others $name" ;;
        esac
    done
    if [[ -n "$others" ]]; then
        printf "check-host: warning: the parent folder '%s' also holds:%s\n" "$workspace" "$others" >&2
        printf 'check-host: warning: the container sees all of it. A folder of its own for the clone avoids surprises.\n' >&2
    fi
}

# Run the check unless the file is only sourced (the tests call check_layout with other paths).
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    script_dir="$(dirname "${BASH_SOURCE[0]}")"
    check_layout "$(cd "$script_dir/.." && pwd -P)" "$(cd "$script_dir/.." && pwd -L)"
fi
