#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install host packages on a GitHub-hosted Ubuntu runner from the Ubuntu archive alone: run
# `apt-get update` and `apt-get install -y ARGUMENTS` with only the Ubuntu sources file of the
# runner image, so that a failing third-party source of the image (for example
# packages.microsoft.com) cannot fail the job. The workflows call it; Jenkins does not, because its
# stages run in the Dev Container image, which installs its packages in the Dockerfile.
#
#   scripts/ci/apt-install.sh [--no-install-recommends] PACKAGE[=VERSION]...
#
# The options are documented: -o and Dir::Etc::sourcelist in apt.conf(5), APT::Get::List-Cleanup
# in apt-get(8), Dir::Etc::SourceParts in apt's configure-index. "-" names a folder that does not
# exist, so no file of /etc/apt/sources.list.d/ is read; List-Cleanup=0 keeps the lists of the
# other sources. On ubuntu-24.04 the Ubuntu sources file is /etc/apt/sources.list.d/ubuntu.sources
# (actions/runner-images, images/ubuntu/scripts/build/configure-apt-sources.sh);
# CRUX_APT_SOURCES names another one.
set -euo pipefail
if [[ $# -eq 0 ]]; then
    printf 'Usage: %s [--no-install-recommends] PACKAGE[=VERSION]...\n' "$0" >&2
    exit 2
fi
sources=${CRUX_APT_SOURCES:-/etc/apt/sources.list.d/ubuntu.sources}
if [[ ! -f "$sources" ]]; then
    printf 'apt-install: no Ubuntu sources file at %s. Set CRUX_APT_SOURCES to it; see %s.\n' \
        "$sources" "$0" >&2
    exit 1
fi
options=(-o "Dir::Etc::sourcelist=$sources" -o "Dir::Etc::sourceparts=-"
    -o "APT::Get::List-Cleanup=0")
sudo apt-get "${options[@]}" update
sudo apt-get "${options[@]}" install -y "$@"
