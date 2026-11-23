#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Install the root certificates of an organisation whose proxy inspects TLS (decrypts HTTPS and
# re-signs it) into the Dev Container image. The Dockerfile runs it as its first step, before any
# download, with the files that the developer placed in .devcontainer/certs/. Git ignores that
# folder apart from .gitkeep and README.md, so every developer places their own file and none is
# committed. An empty folder installs nothing. docs/dev-container.md, "Behind a proxy or with a
# company certificate", says how to export and check the file.
#
#   install-org-certs.sh <source folder> [<target folder>]
#
# Each *.crt, *.pem or *.cer file of the source folder (not its subfolders) is installed as
# <name>.crt in the target folder, /usr/local/share/ca-certificates/crux-org by default:
#   - a PEM file (a BEGIN CERTIFICATE line) as it is, with Windows line ends removed;
#   - else a DER file, converted to PEM with openssl when openssl is there;
#   - a file that holds a private key, or that is neither PEM nor DER, is skipped with a message.
# Any other file is skipped with a message; README.md and .gitkeep are not reported. A skipped file
# never stops the build. Then update-ca-certificates builds the system bundle
# (/etc/ssl/certs/ca-certificates.crt). A base image without it leaves that to the package step of
# the Dockerfile, which installs ca-certificates and runs it. Only file names are printed, never the
# contents.
#
# Environment:
#   CRUX_OPENSSL  the openssl command (default: openssl); only tests change it
set -eu

source_dir=${1:?usage: install-org-certs.sh <source folder> [<target folder>]}
target_dir=${2:-/usr/local/share/ca-certificates/crux-org}
openssl=${CRUX_OPENSSL:-openssl}
convert_hint="Convert a DER file with: openssl x509 -inform der -in company.cer -out company.crt"

installed=0
skipped=0

say() {
    printf 'certs: %s\n' "$*"
}
skip() {
    printf 'certs: skipping %s\n' "$*" >&2
    skipped=$((skipped + 1))
}

# A file name that update-ca-certificates handles: letters, digits, dot, dash and underscore.
safe_name() {
    printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'
}

for file in "$source_dir"/* "$source_dir"/.[!.]*; do
    [ -f "$file" ] || continue
    name=${file##*/}
    case "$name" in
        README.md | .gitkeep) continue ;;
    esac
    stem=${name%.*}
    ending=$(printf '%s' "${name##*.}" | tr 'A-Z' 'a-z')
    case "$name" in
        *.*) ;;
        *) ending="" ;;
    esac
    case "$ending" in
        crt | pem | cer) ;;
        *)
            skip "$name: only .crt, .pem and .cer files are installed"
            continue
            ;;
    esac
    if grep -q -- '-----BEGIN [A-Z ]*PRIVATE KEY-----' "$file"; then
        skip "$name: it holds a private key; place only the certificate here"
        continue
    fi

    mkdir -p "$target_dir"
    target="$target_dir/$(safe_name "$stem").crt"
    if [ -e "$target" ]; then
        target="$target_dir/$(safe_name "$stem")-$ending.crt"
    fi
    if grep -q -- '-----BEGIN CERTIFICATE-----' "$file"; then
        # awk prints every line with a line end, so the last line gets one too.
        awk '{ sub(/\r$/, ""); print }' "$file" >"$target"
        say "installing $name as ${target##*/}"
    elif command -v "$openssl" >/dev/null 2>&1 \
        && "$openssl" x509 -inform der -in "$file" -out "$target" 2>/dev/null; then
        say "converted $name from DER to PEM, installing it as ${target##*/}"
    else
        rm -f "$target"
        if command -v "$openssl" >/dev/null 2>&1; then
            skip "$name: not a PEM or DER certificate. $convert_hint"
        else
            skip "$name: not a PEM certificate, and openssl is not there to convert DER. $convert_hint"
        fi
        continue
    fi
    chmod 0644 "$target"
    installed=$((installed + 1))
done

if [ "$installed" -eq 0 ] && [ "$skipped" -eq 0 ]; then
    say "no certificate in $source_dir; nothing to install"
    exit 0
fi
say "installed $installed certificate(s), skipped $skipped file(s)"
if [ "$installed" -gt 0 ]; then
    if command -v update-ca-certificates >/dev/null 2>&1; then
        update-ca-certificates
    else
        say "update-ca-certificates is not in the base image; the package step installs ca-certificates and builds the bundle"
    fi
fi
