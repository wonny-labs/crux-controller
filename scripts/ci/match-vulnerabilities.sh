#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Match the SPDX documents of a folder against a public vulnerability database.
#
#   scripts/ci/match-vulnerabilities.sh SPDX_FOLDER                 report: a table per document
#   scripts/ci/match-vulnerabilities.sh --json OUT_FOLDER SPDX_FOLDER   write Grype JSON reports
#
# Specification criterion 36 (requirement V2): Grype, at a pinned release whose archive is checked
# against its SHA-256, reads each tag-value SPDX document that west spdx wrote and matches its
# packages against Grype's database, which Grype builds from public sources (the NVD, GitHub
# security advisories and distribution feeds) and downloads at run time.
#
# The default mode is the nightly part (delivery stage 2): each match is printed, and
# release/check_sbom.py, which the same job runs, prints each package without a purl or CPE, which
# Grype cannot match. The --json mode is for the release check (delivery stage 4): it writes Grype's
# JSON output for each document to OUT_FOLDER/<document>.grype.json, and release/check_triage.py
# then fails on a match without an accepted triage record. In both modes the script itself exits 0
# whatever it finds, and fails only when the tool cannot run. Nothing is uploaded.
#
# Label: matching the SBOM against a public database is standard (specification section 6.4, V2,
# from CRA Annex I Part II (1) and (2), unofficial text). The tool, Grype, is documented but
# optional (Grype README, read: it scans SBOMs for known vulnerabilities; no standard names it), as
# the specification leaves it open (section 6.3). Grype's README documents the sbom: input, and the
# SBOM decoders of Syft, which Grype uses, include SPDX tag-value (syft/format/decoders.go).
set -euo pipefail

GRYPE_VERSION=0.121.3
GRYPE_SHA256=e9da18cc1429e786722e32161288103600efffd8e483c90761f90485bd1bec85

usage() { printf 'Usage: %s [--json OUT_FOLDER] SPDX_FOLDER\n' "$0" >&2; exit 2; }
json_dir=
if [[ ${1:-} == --json ]]; then
  [[ $# -eq 3 ]] || usage
  json_dir=$2
  shift 2
fi
[[ $# -eq 1 && -d "$1" ]] || usage
folder=$1
tool="$(mktemp -d)"
trap 'rm -rf "$tool"' EXIT
archive="$tool/grype.tar.gz"
curl --fail --silent --show-error --location --retry 3 --output "$archive" \
  "https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/grype_${GRYPE_VERSION}_linux_amd64.tar.gz"
echo "${GRYPE_SHA256}  ${archive}" | sha256sum --check --strict -
tar -xzf "$archive" -C "$tool" grype
export GRYPE_DB_CACHE_DIR="$tool/db"
export GRYPE_CHECK_FOR_APP_UPDATE=false

shopt -s nullglob
documents=("$folder"/*.spdx)
[[ ${#documents[@]} -gt 0 ]] || { printf 'error: no .spdx file in %s\n' "$folder" >&2; exit 2; }
[[ -z "$json_dir" ]] || mkdir -p "$json_dir"
for document in "${documents[@]}"; do
  name="$(basename "$document")"
  printf '### %s\n' "$name"
  if [[ -n "$json_dir" ]]; then
    report="$json_dir/${name%.spdx}.grype.json"
    "$tool/grype" "sbom:$document" --output json --quiet > "$report" || {
      printf 'error: grype could not read %s\n' "$name" >&2
      exit 1
    }
    printf 'written %s\n' "$(basename "$report")"
  else
    "$tool/grype" "sbom:$document" --output table --quiet || {
      printf 'error: grype could not read %s\n' "$name" >&2
      exit 1
    }
  fi
done
if [[ -n "$json_dir" ]]; then
  echo "Reports written: release/check_triage.py decides the release (criterion 36, delivery stage 4)."
else
  echo "Report only: no match fails this nightly check (criterion 36, delivery stage 2)."
fi
