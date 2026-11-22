#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The one entry that prepares a clone for work. The Dev Container runs it after it is created
# (postCreateCommand), scripts/dev-shell.sh runs it before every command, and you can run it again at any
# time: both steps below check what is done and do nothing then.
#
#   CRUX_BOOTSTRAP=host     the check of the folder layout (.devcontainer/check-host.sh)
#   CRUX_BOOTSTRAP=zephyr   the workspace, the Python tools and the Zephyr SDK (.devcontainer/setup.sh)
#   CRUX_BOOTSTRAP=all      both, in that order (the default)
#
# It only chooses and orders; the work, its markers and its messages stay in the two scripts. Everything it
# prints goes to the standard error stream, so a command that scripts/dev-shell.sh runs after it keeps a
# clean standard output.
set -euo pipefail

exec 1>&2

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${CRUX_BOOTSTRAP:-all}"

case "$mode" in
    host | zephyr | all) ;;
    *)
        printf 'bootstrap: CRUX_BOOTSTRAP must be host, zephyr or all, and it is "%s".\n' "$mode"
        exit 2
        ;;
esac

status=0
trap 'status=$?; ((status == 0)) || printf "bootstrap: failed; rerun: CRUX_BOOTSTRAP=%s bash scripts/bootstrap.sh\n" "$mode"' EXIT

if [[ "$mode" == host || "$mode" == all ]]; then
    bash "$repo/.devcontainer/check-host.sh"
fi
if [[ "$mode" == zephyr || "$mode" == all ]]; then
    bash "$repo/.devcontainer/setup.sh"
fi
