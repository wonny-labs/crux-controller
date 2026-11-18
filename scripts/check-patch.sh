#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Run Zephyr's checkpatch on the C lines that a Git range changes in a product repository.
# It runs the checkpatch.pl of the Zephyr checkout that ZEPHYR_BASE names, from the product
# root. This repository does not copy that tool: it is GPL-2.0 code that stays in Zephyr.
# Crux's scripts/check-patch.sh does the same for the Crux repository and works in any
# repository too. This copy exists so that a product does not depend on where Crux sits.

usage() {
    cat <<'EOF'
Usage: check-patch.sh [BASE [HEAD]]

Check the changed .c and .h lines of the Git range BASE..HEAD (default HEAD^..HEAD) of the
repository that contains the current directory, with Zephyr's checkpatch.pl and --no-tree.

Environment:
  ZEPHYR_BASE       the prepared Zephyr checkout (scripts/checkpatch.pl required)
  CHECKPATCH_TYPES  the checkpatch message types to check, comma separated (default BRACES)

BRACES alone is the rule set of Crux's own gate. Zephyr's checkpatch expects tab indentation by
default, so it reports every line of 4-space code (see docs/coding-guidelines.md in Crux).
EOF
}

case "${1:-}" in
-h | --help)
    usage
    exit 0
    ;;
esac
if (($# > 2)); then
    usage >&2
    exit 2
fi

repo="$(git rev-parse --show-toplevel)"
base="${1:-HEAD^}"
head="${2:-HEAD}"
types="${CHECKPATCH_TYPES:-BRACES}"

if [[ -z "${ZEPHYR_BASE:-}" || ! -f "$ZEPHYR_BASE/scripts/checkpatch.pl" ]]; then
    printf 'Set ZEPHYR_BASE to the prepared Zephyr checkout (scripts/checkpatch.pl required).\n' >&2
    exit 2
fi
for revision in "$base" "$head"; do
    if ! git -C "$repo" rev-parse --verify -q "${revision}^{commit}" >/dev/null; then
        printf 'Missing Git commit %s. Fetch the comparison history before running this check.\n' "$revision" >&2
        exit 2
    fi
done

if git -C "$repo" diff --quiet --no-ext-diff "$base" "$head" -- '*.c' '*.h'; then
    printf 'No changed C source or header files to check.\n'
    exit 0
fi

# checkpatch uses the first .checkpatch.conf it finds in the current directory, then $HOME,
# then .scripts. Run it from the product root: a product's own file applies, else a user's
# ~/.checkpatch.conf, and Zephyr's does not.
cd "$repo"
git diff --no-ext-diff --no-color "$base" "$head" -- '*.c' '*.h' |
    perl "$ZEPHYR_BASE/scripts/checkpatch.pl" --no-tree --no-signoff --types "$types" -
