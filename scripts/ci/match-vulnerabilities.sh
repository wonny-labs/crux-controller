#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Match the SPDX documents of a folder against a public vulnerability database and report.
#
#   scripts/ci/match-vulnerabilities.sh SPDX_FOLDER
#
# The nightly part of specification criterion 36 (requirement V2): Grype, at a pinned release whose
# archive is checked against its SHA-256, reads each tag-value SPDX document that west spdx wrote and
# matches its packages against Grype's database, which Grype builds from public sources (the NVD,
# GitHub security advisories and distribution feeds) and downloads at run time. Each match is
# printed; release/check_sbom.py, which the same job runs, prints each package without a purl or
# CPE, which Grype cannot match. The run only reports: it exits 0 whatever it finds, and fails only
# when the tool cannot run. A release check that fails on an untriaged match belongs to delivery
# stage 4. Nothing is uploaded. Label: matching the SBOM against a public database is standard
# (specification section 6.4, V2, from CRA Annex I Part II (1) and (2), unofficial text); the tool is
# the choice of this repository, which the specification leaves open (section 6.3). Grype's README
# documents the sbom: input, and the SBOM decoders of Syft, which Grype uses, include SPDX tag-value
# (syft/format/decoders.go).
set -euo pipefail

GRYPE_VERSION=0.121.3
GRYPE_SHA256=e9da18cc1429e786722e32161288103600efffd8e483c90761f90485bd1bec85

[[ $# -eq 1 && -d "$1" ]] || { printf 'Usage: %s SPDX_FOLDER\n' "$0" >&2; exit 2; }
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
for document in "${documents[@]}"; do
  printf '### %s\n' "$(basename "$document")"
  "$tool/grype" "sbom:$document" --output table --quiet || {
    printf 'error: grype could not read %s\n' "$(basename "$document")" >&2
    exit 1
  }
done
echo "Report only: no match fails this nightly check (criterion 36, delivery stage 2)."
