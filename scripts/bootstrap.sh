#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The one entry that prepares a clone for work. The Dev Container runs it after it is created
# (postCreateCommand: scripts/bootstrap.sh --keep-going) and prints its status when VS Code attaches
# (postAttachCommand: scripts/bootstrap.sh status). scripts/dev-shell.sh runs it before every command, and you
# can run it again at any time: the steps below check what is done and do nothing then.
#
#   scripts/bootstrap.sh [--keep-going] [all|host|zephyr|status|board-host]
#
#   host        the check of the folder layout (.devcontainer/check-host.sh)
#   zephyr      the workspace, the Python tools and the Zephyr SDK (.devcontainer/setup.sh)
#   all         both, in that order (the default; CRUX_BOOTSTRAP=host|zephyr|all sets another default)
#   status      say whether the workspace and the SDK are there and whether the J-Link software is installed;
#               it installs nothing
#   board-host  only for a board: prepare the Linux system that the J-Link probe is attached to (the WSL2
#               distribution or native Linux) so that the Dev Container can open the probe. It is the step of
#               the Crux checkout in the workspace folder (crux-pilot/scripts/bootstrap.sh board-host) and is
#               never run automatically. Run it outside the container.
#
# It only chooses and orders; the work, its markers and its messages stay in the scripts it calls. Without
# --keep-going the first failed step stops it with that step's exit status. With --keep-going a failed step is
# reported with the command that runs it again, and the exit status is 0, so a failed download never keeps the
# Dev Container from opening. Everything it prints goes to the standard error stream, so a command that
# scripts/dev-shell.sh runs after it keeps a clean standard output. Nothing here flashes, resets or talks to a
# board.
set -euo pipefail

exec 1>&2

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$(dirname "$repo")"

usage() {
    printf 'Usage: %s [--keep-going] [all|host|zephyr|status|board-host]\n' "$0"
    printf '       (default: $CRUX_BOOTSTRAP, else all)\n'
    exit 2
}

keep_going=0
mode=""
for argument in "$@"; do
    case "$argument" in
        --keep-going) keep_going=1 ;;
        all | host | zephyr | status | board-host)
            [[ -z "$mode" ]] || usage
            mode="$argument"
            ;;
        *) usage ;;
    esac
done
mode="${mode:-${CRUX_BOOTSTRAP:-all}}"
case "$mode" in
    host | zephyr | all | status | board-host) ;;
    *)
        printf 'bootstrap: CRUX_BOOTSTRAP must be host, zephyr or all, and it is "%s".\n' "$mode"
        exit 2
        ;;
esac

in_container() {
    [[ -f "${CRUX_DOCKERENV:-/.dockerenv}" ]]
}

if [[ "$mode" == board-host ]]; then
    if in_container; then
        printf 'bootstrap: run "scripts/bootstrap.sh board-host" on the Linux system that has the probe (the WSL2 distribution or native Linux), not in the Dev Container.\n'
        exit 2
    fi
    crux_entry="$workspace/crux-pilot/scripts/bootstrap.sh"
    if [[ ! -f "$crux_entry" ]]; then
        printf 'bootstrap: %s does not exist. The Crux checkout is fetched by the first Dev Container start (west update); open the Dev Container once, then run this again.\n' "$crux_entry"
        exit 1
    fi
    exec bash "$crux_entry" board-host
fi

if [[ "$mode" == status ]]; then
    if [[ -f "$workspace/.west/config" && -d "$workspace/zephyr" ]]; then
        printf 'bootstrap: workspace   ok\n'
    else
        printf 'bootstrap: workspace   not set up   rerun: CRUX_BOOTSTRAP=zephyr bash scripts/bootstrap.sh\n'
    fi
    sdk="${ZEPHYR_SDK_INSTALL_DIR:-}"
    if [[ -n "$sdk" && -f "$sdk/.crux-installed" ]]; then
        printf 'bootstrap: Zephyr SDK  ok\n'
    else
        printf 'bootstrap: Zephyr SDK  not installed   rerun: CRUX_BOOTSTRAP=zephyr bash scripts/bootstrap.sh\n'
    fi
    if command -v JLinkExe >/dev/null 2>&1; then
        printf 'J-Link software: installed (%s)\n' "$(command -v JLinkExe)"
    elif in_container; then
        cat <<'NOTE'
J-Link software is not installed in this container. Host and native_sim work without it; flashing and
debugging a board need it. Download JLink_Linux_<version>_x86_64.deb from SEGGER (accept its licence there),
place it in .devcontainer/jlink/packages/ on the host, then run "Dev Containers: Rebuild Container".
See docs/board-bring-up.md.
NOTE
    fi
    exit 0
fi

failed=""
run_step() {
    local name="$1" script="$2" status=0
    bash "$repo/.devcontainer/$script" || status=$?
    if ((status == 0)); then
        return 0
    fi
    printf 'bootstrap: %s failed (exit %s); rerun: CRUX_BOOTSTRAP=%s bash scripts/bootstrap.sh\n' \
        "$name" "$status" "$name"
    if ((keep_going == 0)); then
        exit "$status"
    fi
    failed="$failed $name"
    return 1
}

steps=()
case "$mode" in
    host) steps=(host:check-host.sh) ;;
    zephyr) steps=(zephyr:setup.sh) ;;
    all) steps=(host:check-host.sh zephyr:setup.sh) ;;
esac
for step in "${steps[@]}"; do
    # A failed layout check must not be followed by a setup in a folder that is not a workspace.
    if [[ -n "$failed" && "${step%%:*}" == zephyr ]]; then
        printf 'bootstrap: zephyr skipped after the failed step;%s. Fix it, then rerun.\n' "$failed"
        continue
    fi
    run_step "${step%%:*}" "${step#*:}" || true
done
if [[ -n "$failed" ]]; then
    printf 'bootstrap: not finished:%s. The Dev Container is usable; run the command above again.\n' "$failed"
fi
