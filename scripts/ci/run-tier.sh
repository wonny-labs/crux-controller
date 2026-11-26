#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The one entry point of CI on every CI system and on a developer machine:
#
#   scripts/ci/run-tier.sh fast|full|nightly|auto [--job JOB] [--check ID] [--base REF] [--plan]
#
# CONTRIBUTING.md (section "CI tiers") describes the tiers and options. The checks and their selection rules are in
# scripts/ci/checks.toml.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
python=${CRUX_CI_PYTHON:-python3}
if ! "$python" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    printf 'error: scripts/ci/run-tier.sh needs Python 3.11 or later as python3 (or set CRUX_CI_PYTHON). See CONTRIBUTING.md#ci-tiers.\n' >&2
    exit 2
fi
exec "$python" "$here/tiers.py" "$@"
