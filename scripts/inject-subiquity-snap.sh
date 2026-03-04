#!/bin/bash

set -eux


# Path on disk to a custom snapd (e.g. one that trusts the test keys)
snapd_pkg=
store_url=
tracking=stable
use_lxd=

LIVEFS_OPTS=()

add_livefs_opts () {
    LIVEFS_OPTS+=("$@")
}

while getopts ":ifc:s:n:p:u:t:l" opt; do
    case "${opt}" in
        i)
            add_livefs_opts --shell
            ;;
        c)
            add_livefs_opts --shell "${OPTARG}"
            ;;
        f|s|n)
            echo "switch to livefs-editor directly please" >&2
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
        l)
            use_lxd=1
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

if [ -n "${use_lxd}" ]; then
    lxc launch ubuntu-daily:noble subiquity-inject --vm --ephemeral

    # Wait until the LXD agent is up
    until [ "$(lxc info subiquity-inject | grep Processes | awk '{print $2}')" -ge 0 ]; do
        sleep 1
    done

    lxc exec subiquity-inject -- cloud-init status --wait

    lxc exec subiquity-inject -- apt-get install --assume-yes xorriso
    lxc exec subiquity-inject -- git clone https://github.com/mwhudson/livefs-editor /root/livefs-editor
else
    LIVEFS_EDITOR="${LIVEFS_EDITOR-$(readlink -f "$(dirname $(dirname ${0}))/livefs-editor")}"
    [ -d $LIVEFS_EDITOR ] || git clone https://github.com/mwhudson/livefs-editor $LIVEFS_EDITOR

    LIVEFS_EDITOR=$(readlink -f $LIVEFS_EDITOR)
fi

# inject-subiquity-snap.sh $old_iso $subiquity_snap $new_iso

OLD_ISO="$(readlink -f "${1}")"
SUBIQUITY_SNAP_PATH="$(readlink -f "${2}")"
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
                    --shell "chroot rootfs dpkg -i $(basename "$snapd_pkg")" \
                    --shell "rm rootfs/$(basename "$snapd_pkg")"
fi

if [ -n "$use_lxd" ]; then
    old_iso=/old.iso
    new_iso=/new.iso
    snap=/to-inject.snap

    lxc file push "$OLD_ISO" subiquity-inject"$old_iso" --uid 0 --gid 0
    lxc file push "$SUBIQUITY_SNAP_PATH" subiquity-inject"$snap" --uid 0 --gid 0
else
    old_iso="$OLD_ISO"
    new_iso="$NEW_ISO"
    snap="$SUBIQUITY_SNAP_PATH"
fi

cmd=(python3 -m livefs_edit "$old_iso" "$new_iso" --inject-snap "$snap" "$tracking" "${LIVEFS_OPTS[@]}")

if [ -n "$use_lxd" ]; then
    lxc exec subiquity-inject --env PYTHONPATH=/root/livefs-editor -- "${cmd[@]}"

    # lxc file pull considers that the target path is a directory, not a file,
    # so we need to do the rename operation ourselves.
    tmpdir=$(mktemp -d)
    lxc file pull subiquity-inject"$new_iso" "$tmpdir"

    mv -- "$tmpdir/$new_iso" "$NEW_ISO"
    lxc stop subiquity-inject
else
    PYTHONPATH=$LIVEFS_EDITOR "${cmd[@]}"
fi
