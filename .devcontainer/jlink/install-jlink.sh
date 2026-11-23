#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Install the SEGGER J-Link Debian package in the Dev Container image. Run by the
# Dockerfile unless CRUX_JLINK=0.
#
# The package comes from one of two places, in this order:
#   1. a JLink_Linux_<version>_x86_64.deb that the developer downloaded from
#      SEGGER, accepting its licence, and placed in .devcontainer/jlink/packages/;
#   2. CRUX_JLINK_URL: a copy that an organisation hosts after accepting the
#      SEGGER licence itself. It is empty in this repository, needs
#      CRUX_JLINK_DEB_SHA256 and must be an https:// URL.
# The script never downloads from SEGGER and never accepts a licence for anyone.
#
# Environment:
#   CRUX_JLINK             auto (default): install the package from 1. or 2.; with
#                          neither, print a warning and install nothing, so the
#                          image still builds. 1: fail without a package.
#   CRUX_JLINK_DEB         file name of the package in the folder (optional when
#                          the folder holds exactly one JLink_Linux_*_x86_64.deb)
#   CRUX_JLINK_DEB_SHA256  expected SHA-256 of the package (required with a URL)
#   CRUX_JLINK_URL         HTTPS URL of a hosted copy of the package (optional)
#   CRUX_JLINK_UDEVADM     path of the temporary udevadm stub; only tests change it
set -eu

dir=${1:?usage: install-jlink.sh <package folder>}
mode=${CRUX_JLINK:-auto}
case "$mode" in
    auto | 1) ;;
    *)
        echo "error: CRUX_JLINK must be auto, 1 or 0 (0 is handled by the Dockerfile), not $mode" >&2
        exit 1
        ;;
esac
deb=${CRUX_JLINK_DEB:-}
url=${CRUX_JLINK_URL:-}
expected=$(printf '%s' "${CRUX_JLINK_DEB_SHA256:-}" | tr 'A-F' 'a-f')

cd "$dir"
if [ -z "$deb" ]; then
    set -- JLink_Linux_*_x86_64.deb
    if [ "$#" -eq 1 ] && [ -f "$1" ]; then
        deb=$1
    elif [ "$#" -gt 1 ]; then
        echo "error: place exactly one SEGGER J-Link package (JLink_Linux_<version>_x86_64.deb)" \
             "in .devcontainer/jlink/packages/, or name one with CRUX_JLINK_DEB" >&2
        exit 1
    elif [ -n "$url" ]; then
        if [ -z "$expected" ]; then
            echo "error: CRUX_JLINK_URL needs CRUX_JLINK_DEB_SHA256, the SHA-256 of the hosted package" >&2
            exit 1
        fi
        case "$url" in
            https://*) ;;
            *)
                echo "error: CRUX_JLINK_URL must be an https:// URL" >&2
                exit 1
                ;;
        esac
        deb=JLink_Linux_download_x86_64.deb
        # Put no token in the URL: build arguments are visible in the image
        # history and in the tracked devcontainer.json.
        command -v curl >/dev/null 2>&1 || { echo "error: CRUX_JLINK_URL needs curl in the image" >&2; exit 1; }
        echo "Downloading the J-Link package from CRUX_JLINK_URL"
        curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --output "$deb" "$url"
    elif [ "$mode" = auto ]; then
        echo "warning: no SEGGER J-Link package; the image is built without the J-Link software." \
             "Host and native_sim work without it; flashing and debugging a board need it. To add it," \
             "download JLink_Linux_<version>_x86_64.deb from SEGGER, accept its licence, place the file" \
             "in .devcontainer/jlink/packages/ and run Dev Containers: Rebuild Container, or set the" \
             "build arguments CRUX_JLINK_URL and CRUX_JLINK_DEB_SHA256 to a copy that your" \
             "organisation hosts" >&2
        exit 0
    else
        echo "error: no SEGGER J-Link package. Either download JLink_Linux_<version>_x86_64.deb" \
             "from SEGGER, accept its licence and place the file in .devcontainer/jlink/packages/," \
             "or set the build arguments CRUX_JLINK_URL and CRUX_JLINK_DEB_SHA256 to a copy" \
             "that your organisation hosts" >&2
        exit 1
    fi
fi

case "$deb" in
    */* | .* | -*)
        echo "error: CRUX_JLINK_DEB must be a plain file name in .devcontainer/jlink/packages/" >&2
        exit 1
        ;;
esac
if [ ! -f "$deb" ]; then
    echo "error: .devcontainer/jlink/packages/$deb not found" >&2
    exit 1
fi

actual=$(sha256sum "$deb" | cut -d ' ' -f 1)
echo "J-Link package: $deb, SHA-256 $actual"
if [ -n "$expected" ] && [ "$actual" != "$expected" ]; then
    echo "error: SHA-256 of $deb is $actual, expected $expected" >&2
    exit 1
fi

# The J-Link package's postinst runs `udevadm control --reload-rules` and
# `udevadm trigger` and fails the install when udevadm is missing, as it is in
# this image. The container needs no udev: the probe's device node gets its
# permissions from 99-crux-jlink.rules on the Linux host. So a no-op udevadm is
# put where dpkg's maintainer scripts look for it, /usr/sbin (a stub in
# /usr/local/bin was not found in the first run), for the install only. It is
# removed right after the install and, through the trap, when the install fails.
# An existing udevadm is left alone.
stub=${CRUX_JLINK_UDEVADM:-/usr/sbin/udevadm}
stub_created=
remove_stub() {
    if [ -n "$stub_created" ]; then
        rm -f "$stub"
        stub_created=
    fi
}
trap remove_stub EXIT
trap 'exit 1' HUP INT TERM
if [ ! -e "$stub" ]; then
    stub_created=1
    printf '#!/bin/sh\n# Temporary no-op from install-jlink.sh, removed after the install.\nexit 0\n' > "$stub"
    chmod 0755 "$stub"
fi

apt-get update
apt-get install -y --no-install-recommends usbutils "./$deb"
remove_stub
# The Dockerfile removes the apt lists and the package folder after this script.

# The probe's device node belongs to group plugdev on a native Linux host (see
# 99-crux-jlink.rules). Debian and Ubuntu give plugdev the same fixed ID (46).
usermod -aG plugdev vscode

for tool in JLinkExe JLinkGDBServer; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "error: $tool is missing after installing $deb" >&2
        exit 1
    fi
done
# The VS Code Cortex-Debug profiles start JLinkGDBServerCLExe. Only warn: west
# needs just the two tools above.
if ! command -v JLinkGDBServerCLExe >/dev/null 2>&1; then
    echo "warning: JLinkGDBServerCLExe is missing; the Cortex-Debug profiles need it" >&2
fi
