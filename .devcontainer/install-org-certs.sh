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
#   - a PEM file (a BEGIN CERTIFICATE line) split into one file per certificate (<name>-<n>.crt for
#     more than one), with Windows line ends removed, after openssl has parsed every certificate;
#   - else a DER file, converted to PEM with openssl;
#   - without openssl, a file that is not PEM is skipped with the command that converts it.
# A file that holds a private key (whatever its ending), a file that is neither PEM nor DER, a PEM
# file with a block other than CERTIFICATE and a certificate that does not parse stop the build with
# an error that names the file, and then nothing is installed. A file with another ending is skipped
# with a message; README.md and .gitkeep are not reported. Then
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
# Whether any of the names that <base> gives <count> certificates is taken: <base>.crt for one,
# <base>-1.crt to <base>-<count>.crt for a bundle.
names_taken() {
    if [ "$2" -eq 1 ]; then
        taken "$1.crt"
        return
    fi
    n=1
    while [ "$n" -le "$2" ]; do
        if taken "$1-$n.crt"; then
            return 0
        fi
        n=$((n + 1))
    done
    return 1
}

for file in "$source_dir"/* "$source_dir"/.[!.]*; do
    [ -f "$file" ] || continue
    name=${file##*/}
    case "$name" in
        README.md | .gitkeep) continue ;;
    esac
    # A key never belongs here, whatever the file is called.
    if grep -q -- 'PRIVATE KEY-----' "$file"; then
        refuse "$name" "holds a private key. Put only the CA certificate here, never a key."
        continue
    fi
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
    base=$(safe_name "$stem")

    if grep -q -- '-----BEGIN CERTIFICATE-----' "$file"; then
        if tr -d '\r' <"$file" | grep -- '^-----BEGIN ' | grep -v -q -x -- '-----BEGIN CERTIFICATE-----'; then
            refuse "$name" "holds a PEM block that is not a certificate."
            continue
        fi
        # One file per certificate, Windows line ends removed.
        rm -rf "$stage/split"
        mkdir "$stage/split"
        tr -d '\r' <"$file" | awk -v out="$stage/split/part" '
            /^-----BEGIN CERTIFICATE-----$/ { n++; f = sprintf("%s-%04d.pem", out, n); inside = 1 }
            inside { print > f }
            /^-----END CERTIFICATE-----$/ { if (inside) close(f); inside = 0 }'
        set -- "$stage/split/"part-*.pem
        if [ ! -f "$1" ]; then
            refuse "$name" "holds no certificate block that can be read."
            continue
        fi
        count=$#
        number=0
        bad=0
        for part do
            number=$((number + 1))
            if [ "$have_openssl" -eq 1 ] && ! "$openssl" x509 -noout -in "$part" >/dev/null 2>&1; then
                if [ "$count" -eq 1 ]; then
                    refuse "$name" "is not a valid certificate."
                else
                    refuse "$name" "certificate $number of $count is not a valid certificate."
                fi
                bad=1
            fi
        done
        [ "$bad" -eq 0 ] || continue
        # <base>.crt (or <base>-1.crt to <base>-<count>.crt for a bundle), else <base>-<ending>, else
        # <base>-<ending>-<n>, until every name is free: no file of this run or of the target folder is
        # ever overwritten.
        if names_taken "$base" "$count"; then
            stem_base="$base-$ending"
            base=$stem_base
            suffix=2
            while names_taken "$base" "$count"; do
                base="$stem_base-$suffix"
                suffix=$((suffix + 1))
            done
        fi
        number=0
        for part do
            number=$((number + 1))
            if [ "$count" -eq 1 ]; then target="$base.crt"; else target="$base-$number.crt"; fi
            if taken "$target"; then
                refuse "$name" "would overwrite $target."
                break
            fi
            mv "$part" "$stage/$target"
            say "installing $name as $target"
            staged=$((staged + 1))
        done
        continue
    fi

    target="$base.crt"
    if taken "$target"; then
        target="$base-$ending.crt"
        number=2
        while taken "$target"; do
            target="$base-$ending-$number.crt"
            number=$((number + 1))
        done
    fi
    if [ "$have_openssl" -eq 0 ]; then
        skip "$name: not a PEM certificate, and openssl is not there to convert DER. $convert_hint"
        continue
    elif "$openssl" x509 -inform der -in "$file" -out "$stage/$target" 2>/dev/null; then
        say "converted $name from DER to PEM, installing it as $target"
        staged=$((staged + 1))
    else
        rm -f "$stage/$target"
        refuse "$name" "is neither a PEM nor a DER certificate."
    fi
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
