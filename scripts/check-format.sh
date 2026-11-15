#!/usr/bin/env bash
# Check that every C and C++ source and header of this repository is formatted as .clang-format
# says. The file list comes from git, so a new file is checked without a change to this script.
#
# CLANG_FORMAT names the formatter (default: clang-format). Its version is pinned: another
# version may format differently, so the check fails instead of reporting differences that
# the pinned version does not have. Install it with: python3 -m pip install clang-format==18.1.8
set -euo pipefail

required_version="18.1.8"
repo="$(git rev-parse --show-toplevel)"
formatter="${CLANG_FORMAT:-clang-format}"

if ! version_line="$("$formatter" --version 2>/dev/null)"; then
    printf 'check-format: cannot run %s. Install clang-format %s (python3 -m pip install clang-format==%s).\n' \
        "$formatter" "$required_version" "$required_version" >&2
    exit 2
fi
case "$version_line" in
    *"version $required_version"*) ;;
    *)
        printf 'check-format: %s is "%s", but clang-format %s is required (python3 -m pip install clang-format==%s).\n' \
            "$formatter" "$version_line" "$required_version" "$required_version" >&2
        exit 2
        ;;
esac

sources=()
# -z keeps a path with a non-ASCII character as it is. Without it git quotes the path.
while IFS= read -r -d '' source; do
    # Git still lists the old path of a deleted file until the deletion is staged.
    if [[ -f "$repo/$source" ]]; then
        sources+=("$repo/$source")
    fi
done < <(git -C "$repo" ls-files -z --cached --others --exclude-standard -- '*.c' '*.h' '*.cpp' '*.hpp')

if ((${#sources[@]} == 0)); then
    printf 'check-format: no C or C++ files found.\n' >&2
    exit 2
fi

printf 'check-format: %s files, %s\n' "${#sources[@]}" "$version_line"
"$formatter" --dry-run --Werror "${sources[@]}"
