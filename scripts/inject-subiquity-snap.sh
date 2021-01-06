#!/bin/bash

set -eux

cmds=
interactive=no
edit_filesystem=no
source_installer=old_iso/casper/installer.squashfs
source_filesystem=
# Path on disk to a custom snapd (e.g. one that trusts the test keys)
snapd_pkg=
store_url=
tracking=stable
while getopts ":ifc:s:n:p:u:t:" opt; do
    case "${opt}" in
        i)
            interactive=yes
            ;;
        c)
            cmds="${OPTARG}"
            ;;
        f)
            edit_filesystem=yes
            ;;
        s)
            source_installer="$(readlink -f "${OPTARG}")"
            ;;
        n)
            source_filesystem="$(readlink -f "${OPTARG}")"
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

# inject-subiquity-snap.sh $old_iso $subiquity_snap $new_iso

OLD_ISO="$(readlink -f "${1}")"
SUBIQUITY_SNAP_PATH="$(readlink -f "${2}")"
SUBIQUITY_SNAP="$(basename $SUBIQUITY_SNAP_PATH)"
SUBIQUITY_ASSERTION="${SUBIQUITY_SNAP_PATH%.snap}.assert"
if [ ! -f "$SUBIQUITY_ASSERTION" ]; then
    SUBIQUITY_ASSERTION=
fi
NEW_ISO="$(readlink -f "${3}")"

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

cleanup () {
    for m in "${_MOUNTS[@]+"${_MOUNTS[@]}"}"; do
        umount "${m}"
    done
    rm -rf "${tmpdir}"
}

trap cleanup EXIT

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

do_mount -t iso9660 -o loop,ro "${OLD_ISO}" old_iso
unsquashfs -d new_installer "${source_installer}"
do_mount -t squashfs ${source_filesystem:-old_iso/casper/filesystem.squashfs} old_filesystem
add_overlay old_filesystem tree new_installer
do_mount_existing dev-live -t devtmpfs "tree/dev"
do_mount_existing devpts-live -t devpts "tree/dev/pts"
do_mount_existing proc-live -t proc "tree/proc"
do_mount_existing sysfs-live -t sysfs "tree/sys"
do_mount_existing securityfs-live -t securityfs "tree/sys/kernel/security"


python3 -c '
import os, sys, yaml
with open("tree/var/lib/snapd/seed/seed.yaml") as fp:
     old_seed = yaml.safe_load(fp)
new_snaps = []

subiquity_snap = {
    "name": "subiquity",
    "classic": True,
    "file": sys.argv[1],
    "channel": sys.argv[3],
    }

if sys.argv[2] == "":
    subiquity_snap["unasserted"] = True

for snap in old_seed["snaps"]:
    if snap["name"] == "subiquity":
        new_snaps.append(subiquity_snap)
    else:
        new_snaps.append(snap)

with open("tree/var/lib/snapd/seed/seed.yaml", "w") as fp:
     yaml.dump({"snaps": new_snaps}, fp)
' "$SUBIQUITY_SNAP" "$SUBIQUITY_ASSERTION" "$tracking"

rm -f tree/var/lib/snapd/seed/assertions/subiquity*.assert
rm -f tree/var/lib/snapd/seed/snaps/subiquity*.snap
cp "${SUBIQUITY_SNAP_PATH}" tree/var/lib/snapd/seed/snaps/
if [ -n "${SUBIQUITY_ASSERTION}" ]; then
    cp "${SUBIQUITY_ASSERTION}" tree/var/lib/snapd/seed/assertions/
fi

if [ -n "$store_url" ]; then
    STORE_CONFIG=tree/etc/systemd/system/snapd.service.d/store.conf
    mkdir -p "$(dirname $STORE_CONFIG)"
    cat > "$STORE_CONFIG" <<EOF
[Service]
Environment=SNAPD_DEBUG=1 SNAPD_DEBUG_HTTP=7 SNAPPY_TESTING=1
Environment=SNAPPY_FORCE_API_URL=$store_url
EOF
fi

if [ -n "$snapd_pkg" ]; then
    cp "$snapd_pkg" tree/
    chroot tree dpkg -i $(basename "$snapd_pkg")
    rm tree/$(basename "$snapd_pkg")
fi

add_overlay old_iso new_iso

if [ "$edit_filesystem" = "yes" ]; then
    do_mount -t squashfs ${source_filesystem:-old_iso/casper/filesystem.squashfs} old_filesystem
    add_overlay old_filesystem new_filesystem
fi


if [ -n "$cmds" ]; then
    bash -c "$cmds"
fi
if [ "$interactive" = "yes" ]; then
    bash
fi

/usr/lib/snapd/snap-preseed --reset $(realpath tree)
/usr/lib/snapd/snap-preseed $(realpath tree)
chroot tree apparmor_parser --skip-read-cache --write-cache --skip-kernel-load --verbose  -j `nproc` /etc/apparmor.d

if [ "$edit_filesystem" = "yes" ]; then
    rm new_iso/casper/filesystem.squashfs
    mksquashfs new_filesystem new_iso/casper/filesystem.squashfs
elif [ -n "${source_filesystem}" ]; then
    rm new_iso/casper/filesystem.squashfs
    cp "${source_filesystem}" new_iso/casper/filesystem.squashfs
fi

rm new_iso/casper/installer.squashfs new_iso/casper/installer.squashfs.gpg
mksquashfs new_installer new_iso/casper/installer.squashfs

(
    cd new_iso
    sed -i'' '/\.\/casper\/installer.squashfs/d' md5sum.txt
    md5sum ./casper/installer.squashfs >> md5sum.txt
)

eval set -- $(xorriso -indev ${OLD_ISO} -report_el_torito as_mkisofs 2>/dev/null)
xorriso -as mkisofs "$@" -o ${NEW_ISO} -V Ubuntu\ custom new_iso
