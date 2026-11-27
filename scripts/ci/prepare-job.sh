#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Prepare the west workspace of one CI job of scripts/ci/checks.toml before its checks run:
#
#   scripts/ci/prepare-job.sh JOB
#
# The GitHub workflows and scripts/ci/jenkins/run-job.sh call it after they installed the job's
# tools, and only when the tier selected a check of the job. The clone must be the folder
# crux-controller in the west workspace folder. A job whose checks set up their own workspace, or
# need none, prepares nothing here. See CONTRIBUTING.md#ci-tiers.
set -euo pipefail
job=${1:-}
if [[ -z "$job" || $# -ne 1 ]]; then
    printf 'Usage: %s JOB (see scripts/ci/run-tier.sh --list-jobs)\n' "$0" >&2
    exit 2
fi
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ "$(basename "$repo")" != crux-controller ]]; then
    printf 'error: the clone must be the folder crux-controller in the west workspace folder, and it is %s. See CONTRIBUTING.md#ci-tiers.\n' "$(basename "$repo")" >&2
    exit 2
fi
cd "$(dirname "$repo")"

# The workspace of the product: west init, west update, then the Python requirements of Zephyr.
fetch_workspace() {
    west init -l crux-controller
    west update
    python -m pip install -r zephyr/scripts/requirements-base.txt "$@"
}

install_sdk() {
    crux-controller/scripts/ci/install-sdk.sh zephyr
}

case "$job" in
    tooling | host-OFF | host-ON | static | patch-style | devcontainer | rebuild | release | scheduled-main | product-integration)
        ;;
    pins)
        west init -l crux-controller
        west update
        ;;
    boundary)
        west init -l crux-controller
        west update crux-pilot
        ;;
    workload)
        fetch_workspace -r zephyr/scripts/requirements-build-test.txt -r zephyr/scripts/requirements-run-test.txt
        install_sdk
        ;;
    management | base)
        # The default update only. The checks switch the Mbed TLS group on after they checked the
        # project list, fetch the modules with the Zephyr requirements, then install the SDK.
        west init -l crux-controller
        west update
        ;;
    budget-management | budget-base)
        # The checks switch the Mbed TLS group on and fetch its modules, then install the SDK.
        fetch_workspace
        ;;
    net | file | system | sntp | minimal | budget-*)
        fetch_workspace
        install_sdk
        ;;
    *)
        printf 'error: scripts/ci/prepare-job.sh does not know job %s. Add its set-up here. See CONTRIBUTING.md#ci-tiers.\n' "$job" >&2
        exit 2
        ;;
esac
