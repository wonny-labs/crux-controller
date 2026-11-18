#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run a shell, or one command, in the dev container without VS Code. It needs Docker Engine and
# nothing else of Docker (no Docker Desktop): Docker Engine inside a WSL2 distribution is enough.
#
#   scripts/dev-shell.sh                      an interactive shell in the repository
#   scripts/dev-shell.sh <command> [args...]  one command, with the repository as working directory
#
# It builds the image of .devcontainer/Dockerfile, mounts the parent folder of the clone as the
# west workspace at /workspaces/ws, and runs .devcontainer/setup.sh before the command. The first run
# fetches Zephyr, the west modules and the Zephyr SDK (a long time, several GiB); later runs find
# them in the workspace folder and in a Docker volume of that workspace folder, named
# crux-controller-dev-cache-<number>. Each workspace folder has its own, so that two workspaces with
# different Zephyr requirements do not share one virtual environment.
#
# CRUX_DEV_IMAGE overrides the image name. GH_TOKEN, when set, is passed to the container for the
# SDK download. See docs/try-on-native-sim.md, "Dev container".
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
    printf 'dev-shell: docker is not installed. Install Docker Engine (docs/try-on-native-sim.md, "Dev container").\n' >&2
    exit 2
fi
if [[ "$(basename "$repo")" != "crux-controller" ]]; then
    printf 'dev-shell: the clone must be in a folder named crux-controller, and it is in %s.\n' "$(basename "$repo")" >&2
    exit 2
fi

volume="$volume_prefix-$(printf '%s' "$workspace" | cksum | cut -d' ' -f1)"

docker build --platform linux/amd64 \
    --build-arg "USER_UID=$(id -u)" --build-arg "USER_GID=$(id -g)" \
    -t "$image" "$repo/.devcontainer"

flags=(--rm --platform linux/amd64 --user vscode
    -v "$workspace:/workspaces/ws" -v "$volume:/opt/crux-cache"
    -w /workspaces/ws/crux-controller)
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
    bash -c 'bash .devcontainer/setup.sh </dev/null && exec "$@"' dev-shell "$@"
