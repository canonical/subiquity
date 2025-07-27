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
    do_mount -t overlay overlay \
        -o lowerdir="${lower}",upperdir="${upper}",workdir="${work}" \
        "${mountpoint}"
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

rm -rf new/lib/python3.12/site-packages/curtin
rm -rf new/lib/python3.12/site-packages/probert

if [ -d new/lib/python3.12/site-packages/subiquity ] ; then
    subiquity_dest=new/lib/python3.12/site-packages
    bin_dest=new/system_scripts/
elif [ -d new/bin/subiquity/subiquity ] ; then
    subiquity_dest=new/bin/subiquity
    bin_dest=new/bin/subiquity/system_scripts/
else
    echo "unrecognized snap" >&2
    exit 1
fi

rm -rf "${subiquity_dest}/subiquity"
rm -rf "${subiquity_dest}/subiquitycore"

(cd "${src}" && ./scripts/update-part.py curtin)
(cd "${src}" && ./scripts/update-part.py probert)

# Build probert for the C extensions
(cd "${src}"/probert && python3.12 setup.py build_ext --inplace)

rsync -a --chown 0:0 $src/curtin/curtin new/lib/python3.12/site-packages
rsync -a --chown 0:0 $src/probert/probert new/lib/python3.12/site-packages
rsync -a --chown 0:0 $src/subiquity $src/subiquitycore $subiquity_dest
rsync -a --chown 0:0 $src/system_scripts/ $bin_dest

snapcraft pack new --output $new
