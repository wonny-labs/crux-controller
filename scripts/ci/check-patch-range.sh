#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Check the patch style of the C lines that this CI run's change touches, with
# scripts/check-patch.sh. scripts/ci/run-tier.sh sets CRUX_CI_DIFF_BASE to the commit it compared
# the change with. A post-merge run must have that base; a run without one, such as a manual or
# nightly run, checks the latest commit only. This is the script of the same name of Crux.
# See CONTRIBUTING.md#ci-tiers.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
base=${CRUX_CI_DIFF_BASE:-}
if [[ -z "$base" ]]; then
    if [[ "${CRUX_CI_EVENT:-}" == post-merge ]]; then
        printf 'Missing previous push SHA for complete patch-style comparison. Rerun with CRUX_CI_BASE set to the previous commit of the branch. See CONTRIBUTING.md#ci-tiers.\n' >&2
        exit 2
    fi
    base=HEAD^
fi
exec scripts/check-patch.sh "$base" HEAD
