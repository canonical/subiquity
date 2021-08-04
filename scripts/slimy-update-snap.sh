#!/bin/bash

# slimy-update-snap.sh $old_snap $new_snap

set -eux

src="$(dirname "$(dirname "$(readlink -f "${0}")")")"
old="$(readlink -f "${1}")"
new="$(readlink -f "${2}")"

tmpdir="$(mktemp -d)"
cd "${tmpdir}"

_MOUNTS=()

do_mount_existing () {
    local mountpoint="${!#}"
    mount "$@"
    _MOUNTS=("${mountpoint}" "${_MOUNTS[@]+"${_MOUNTS[@]}"}")
}

do_mount () {
    local mountpoint="${!#}"
    mkdir "${mountpoint}"
    do_mount_existing "$@"
}

add_overlay() {
    local lower="$1"
    local mountpoint="$2"
    local work="$(mktemp -dp "${tmpdir}")"
    if [ -n "${3-}" ]; then
        local upper="${3}"
    else
        local upper="$(mktemp -dp "${tmpdir}")"
    fi
    chmod go+rx "${work}" "${upper}"
    do_mount -t overlay overlay -o lowerdir="${lower}",upperdir="${upper}",workdir="${work}" "${mountpoint}"
}


cleanup () {
    for m in "${_MOUNTS[@]+"${_MOUNTS[@]}"}"; do
        umount "${m}"
    done
    rm -rf "${tmpdir}"
}

trap cleanup EXIT

do_mount $old old

add_overlay old new

rm -rf new/lib/python3.6/site-packages/curtin
rm -rf new/lib/python3.6/site-packages/subiquity
rm -rf new/lib/python3.6/site-packages/subiquitycore

(cd "${src}" && ./scripts/update-part.py curtin)

rsync -a $src/subiquity $src/subiquitycore $src/curtin/curtin new/lib/python3.6/site-packages

mksquashfs new $new -comp gzip -Xcompression-level 3
