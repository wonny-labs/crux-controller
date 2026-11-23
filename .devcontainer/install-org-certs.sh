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
#   - a PEM file (a BEGIN CERTIFICATE line) as it is, with Windows line ends removed, after openssl
#     has parsed it;
#   - else a DER file, converted to PEM with openssl;
#   - without openssl, a file that is not PEM is skipped with the command that converts it.
# A file that holds a private key, a file that is neither PEM nor DER and a PEM file that does not
# parse stop the build with an error that names the file, and then nothing is installed. A file with
# another ending is skipped with a message; README.md and .gitkeep are not reported. Then
# update-ca-certificates builds the system bundle (/etc/ssl/certs/ca-certificates.crt). A base image
# without it leaves that to the package step of the Dockerfile, which installs ca-certificates and
# runs it. Only file names are printed, never the contents.
#
# Environment:
#   CRUX_OPENSSL  the openssl command (default: openssl); only tests change it
set -eu

source_dir=${1:?usage: install-org-certs.sh <source folder> [<target folder>]}
target_dir=${2:-/usr/local/share/ca-certificates/crux-org}
openssl=${CRUX_OPENSSL:-openssl}
convert_hint="Convert a DER file with: openssl x509 -inform der -in company.cer -out company.crt"
readme=".devcontainer/certs/README.md"

have_openssl=0
if command -v "$openssl" >/dev/null 2>&1; then
    have_openssl=1
fi

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
staged=0
failed=0

say() {
    printf 'certs: %s\n' "$*"
}
skip() {
    printf 'certs: skipping %s\n' "$*" >&2
}
refuse() {
    printf 'error: .devcontainer/certs/%s: %s See %s.\n' "$1" "$2" "$readme" >&2
    failed=1
}

# A file name that update-ca-certificates handles: letters, digits, dot, dash and underscore.
safe_name() {
    printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'
}
# A name that is free in this run and in the target folder.
taken() {
    [ -e "$stage/$1" ] || [ -e "$target_dir/$1" ]
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
    if grep -q -- 'PRIVATE KEY-----' "$file"; then
        refuse "$name" "holds a private key. Put only the CA certificate here, never a key."
        continue
    fi

    # <stem>.crt, else <stem>-<ending>.crt, else with a number: no file is ever overwritten.
    base=$(safe_name "$stem")
    target="$base.crt"
    if taken "$target"; then
        target="$base-$ending.crt"
        number=2
        while taken "$target"; do
            target="$base-$ending-$number.crt"
            number=$((number + 1))
        done
    fi
    if grep -q -- '-----BEGIN CERTIFICATE-----' "$file"; then
        # awk prints every line with a line end, so the last line gets one too.
        awk '{ sub(/\r$/, ""); print }' "$file" >"$stage/$target"
        if [ "$have_openssl" -eq 1 ] && ! "$openssl" x509 -noout -in "$stage/$target" >/dev/null 2>&1; then
            rm -f "$stage/$target"
            refuse "$name" "is not a valid certificate."
            continue
        fi
        say "installing $name as $target"
    elif [ "$have_openssl" -eq 0 ]; then
        skip "$name: not a PEM certificate, and openssl is not there to convert DER. $convert_hint"
        continue
    elif "$openssl" x509 -inform der -in "$file" -out "$stage/$target" 2>/dev/null; then
        say "converted $name from DER to PEM, installing it as $target"
    else
        rm -f "$stage/$target"
        refuse "$name" "is neither a PEM nor a DER certificate."
        continue
    fi
    staged=$((staged + 1))
done

if [ "$failed" -ne 0 ]; then
    echo "error: no organisation CA was installed. Fix or remove the files named above, then rebuild the container." >&2
    exit 1
fi
if [ "$staged" -eq 0 ]; then
    say "no certificate in $source_dir; nothing to install"
    exit 0
fi
mkdir -p "$target_dir"
for cert in "$stage"/*.crt; do
    install -m 0644 "$cert" "$target_dir/"
done
say "installed $staged certificate(s)"
if command -v update-ca-certificates >/dev/null 2>&1; then
    update-ca-certificates
else
    say "update-ca-certificates is not in the base image; the package step installs ca-certificates and builds the bundle"
fi
