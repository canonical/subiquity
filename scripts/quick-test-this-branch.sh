#!/bin/bash

set -eux

src="$(dirname "$(dirname "$(readlink -f "${0}")")")"
old_iso="$(readlink -f "${1}")"
new_iso="$(readlink -f "${2}")"

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

clean_mounts () {
    for m in "${_MOUNTS[@]+"${_MOUNTS[@]}"}"; do
        umount "${m}"
    done
    _MOUNTS=()
}

cleanup () {
    clean_mounts
    rm -rf "${tmpdir}"
}

trap cleanup EXIT

do_mount $old_iso old_iso
do_mount old_iso/casper/installer.squashfs installer

$src/scripts/slimy-update-snap.sh installer/var/lib/snapd/seed/snaps/subiquity_*.snap subiquity_new.snap

clean_mounts

$src/scripts/inject-subiquity-snap.sh $old_iso subiquity_new.snap $new_iso
