#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Scan the files of the checkout for secrets, and fail on a finding.
#
#   scripts/ci/secret-scan.sh
#
# The secret scan of specification criterion 41 (requirement Q1), on every change: Gitleaks, at a
# pinned release whose archive is checked against its SHA-256, scans the working tree with its
# default rules (private keys, API tokens, passwords in known formats) and prints each finding with
# the secret redacted. A finding fails the check. Gitleaks reads the configuration .gitleaks.toml
# of the repository root when one exists; there is none, so no rule is turned off. Run from the
# repository root. Nothing is uploaded. Label: a secret scan is documented but optional (GitHub
# documentation, secret scanning; specification section 6.4, Q1), and the tool is the choice of this
# repository, which the specification leaves open (section 6.3); Gitleaks documents the dir command
# and its default rules in its README.
set -euo pipefail

GITLEAKS_VERSION=8.30.1
GITLEAKS_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb

tool="$(mktemp -d)"
trap 'rm -rf "$tool"' EXIT
archive="$tool/gitleaks.tar.gz"
curl --fail --silent --show-error --location --retry 3 --output "$archive" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
echo "${GITLEAKS_SHA256}  ${archive}" | sha256sum --check --strict -
tar -xzf "$archive" -C "$tool" gitleaks
"$tool/gitleaks" dir . --redact --no-banner --exit-code 1
