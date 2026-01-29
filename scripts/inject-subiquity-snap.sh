#!/bin/bash

set -eux

LIVEFS_EDITOR="${LIVEFS_EDITOR-$(readlink -f "$(dirname $(dirname ${0}))/livefs-editor")}"
[ -d $LIVEFS_EDITOR ] || git clone https://github.com/mwhudson/livefs-editor $LIVEFS_EDITOR

LIVEFS_EDITOR=$(readlink -f $LIVEFS_EDITOR)

# Path on disk to a custom snapd (e.g. one that trusts the test keys)
snapd_pkg=
store_url=
tracking=stable

LIVEFS_OPTS=

add_livefs_opts () {
    LIVEFS_OPTS="${LIVEFS_OPTS+$LIVEFS_OPTS }$@"
}

while getopts ":ifc:s:n:p:u:t:" opt; do
    case "${opt}" in
        i)
            add_livefs_opts --shell
            ;;
        c)
            add_livefs_opts --shell "${OPTARG}"
            ;;
        f|s|n)
            echo "switch to livefs-editor directly please" >2
            exit 1
            ;;
        p)
            snapd_pkg="$(readlink -f "${OPTARG}")"
            ;;
        u)
            store_url="${OPTARG}"
            ;;
        t)
            tracking="${OPTARG}"
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND-1))

if [ "$#" -lt 3 ]; then
    cat >&2 <<EOF
usage: $0 [option...] <SRC_ISO> <SNAP> <DEST_ISO>

positional arguments:
  SRC_ISO    path to the source ISO to use
  SNAP       path to the snap to inject
  DEST_ISO   path to the destination ISO to create

options:
  -i            launch an interactive shell in the unpacked rootfs
  -c COMMAND    execute a command in the rootfs
  -p SNAPD_DEB  path to a snapd deb package to install
  -u URL        override the URL of the snap store
  -t CHANNEL    make the subiquity snap track the specified channel (default: stable)

example:
  $0 /srv/iso/noble-live-server-amd64.iso subiquity_6871.snap custom.iso
EOF
    exit 1
fi

# inject-subiquity-snap.sh $old_iso $subiquity_snap $new_iso

OLD_ISO="$(readlink -f "${1}")"
SUBIQUITY_SNAP_PATH="$(readlink -f "${2}")"
SUBIQUITY_SNAP="$(basename $SUBIQUITY_SNAP_PATH)"
NEW_ISO="$(readlink -f "${3}")"

tmpdir="$(mktemp -d)"
cd "${tmpdir}"

cleanup () {
    rm -rf "${tmpdir}"
}

trap cleanup EXIT

if [ -n "$store_url" ]; then
    cat > "store.conf" <<EOF
[Service]
Environment=SNAPD_DEBUG=1 SNAPD_DEBUG_HTTP=7 SNAPPY_TESTING=1
Environment=SNAPPY_FORCE_API_URL=$store_url
EOF
    add_livefs_opts --setup-rootfs --shell 'mkdir -p rootfs/etc/systemd/system/snapd.service.d/' \
                    --cp store.conf rootfs/etc/systemd/system/snapd.service.d/store.conf
fi

if [ -n "$snapd_pkg" ]; then
    add_livefs_opts --setup-rootfs \
                    --cp "$snapd_pkg" rootfs \
                    --shell "chroot rootfs dpkg -i $(basename "$snapd_pkg")"
                    --shell "rm rootfs/$(basename "$snapd_pkg")"
fi

PYTHONPATH=$LIVEFS_EDITOR python3 -m livefs_edit $OLD_ISO $NEW_ISO --inject-snap $SUBIQUITY_SNAP_PATH $tracking $LIVEFS_OPTS
