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
while getopts ":ifc:s:n:p:u:" opt; do
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
NEW_ISO="$(readlink -f "${3}")"

tmpdir="$(mktemp -d)"
cd "${tmpdir}"

_MOUNTS=()

do_mount () {
    local mountpoint="${!#}"
    mkdir "${mountpoint}"
    mount "$@"
    _MOUNTS=("${mountpoint}" "${_MOUNTS[@]+"${_MOUNTS[@]}"}")
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
if [ -n "$snapd_pkg" ]; then
    # Setting up the overlay to install a custom snapd requires
    # new_installer to be a real directory it seems.
    unsquashfs -d new_installer "${source_installer}"
else
    do_mount -t squashfs "${source_installer}" old_installer
    add_overlay old_installer new_installer
fi


python -c '
import sys, yaml
with open("new_installer/var/lib/snapd/seed/seed.yaml") as fp:
     old_seed = yaml.load(fp)
new_snaps = []

for snap in old_seed["snaps"]:
    if snap["name"] == "subiquity":
        new_snaps.append({
            "name": "subiquity",
            "unasserted": True,
            "classic": True,
            "file": sys.argv[1],
            })
    else:
        new_snaps.append(snap)

with open("new_installer/var/lib/snapd/seed/seed.yaml", "w") as fp:
     yaml.dump({"snaps": new_snaps}, fp)
' $SUBIQUITY_SNAP

rm -f new_installer/var/lib/snapd/seed/assertions/subiquity*.assert
rm -f new_installer/var/lib/snapd/seed/snaps/subiquity*.snap
cp "${SUBIQUITY_SNAP_PATH}" new_installer/var/lib/snapd/seed/snaps/

if [ -n "$store_url" ]; then
    STORE_CONFIG=new_installer/etc/systemd/system/snapd.service.d/store.conf
    mkdir -p "$(dirname $STORE_CONFIG)"
    cat > "$STORE_CONFIG" <<EOF
[Service]
Environment=SNAPD_DEBUG=1 SNAPD_DEBUG_HTTP=7 SNAPPY_TESTING=1
Environment=SNAPPY_FORCE_API_URL=http://$store_url
EOF
fi

if [ -n "$snapd_pkg" ]; then
    do_mount -t squashfs ${source_filesystem:-old_iso/casper/filesystem.squashfs} old_filesystem
    add_overlay old_filesystem combined new_installer
    cp "$snapd_pkg" combined/
    chroot combined dpkg -i $(basename "$snapd_pkg")
    rm combined/$(basename "$snapd_pkg")
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

if [ "$edit_filesystem" = "yes" ]; then
    rm new_iso/casper/filesystem.squashfs
    mksquashfs new_filesystem new_iso/casper/filesystem.squashfs
elif [ -n "${source_filesystem}" ]; then
    rm new_iso/casper/filesystem.squashfs
    cp "${source_filesystem}" new_iso/casper/filesystem.squashfs
fi

rm new_iso/casper/installer.squashfs
mksquashfs new_installer new_iso/casper/installer.squashfs

if [ -e new_iso/boot/grub/efi.img ]; then
    xorriso -as mkisofs -r -checksum_algorithm_iso md5,sha1 \
	    -V Ubuntu\ custom\ amd64 \
	    -o "${NEW_ISO}" \
	    -cache-inodes -J -l \
	    -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot \
	    -boot-load-size 4 -boot-info-table \
	    -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
	    -isohybrid-gpt-basdat -isohybrid-apm-hfsplus \
	    -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin  \
	    new_iso/boot new_iso
fi

if [ -e new_iso/boot/ubuntu.ikr ]; then
    xorriso -as mkisofs -r -checksum_algorithm_iso md5,sha1 \
	    -V Ubuntu\ custom\ s390x \
	    -o "${NEW_ISO}" \
	    -cache-inodes -J -l \
	    -b boot/ubuntu.ikr -no-emul-boot \
	    new_iso/boot new_iso
fi
