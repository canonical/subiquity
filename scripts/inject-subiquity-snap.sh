#!/bin/bash

set -eux

cmds=
interactive=no
edit_filesystem=no
source_installer=old_iso/casper/installer.squashfs
source_filesystem=
while getopts ":ifc:s:n:" opt; do
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
    local upper="$(mktemp -dp "${tmpdir}")"
    chmod go+rx "${work}" "${upper}"
    do_mount -t overlay overlay -o lowerdir="${lower}",upperdir="${upper}",workdir="${work}" "${mountpoint}"
}

do_mount -t iso9660 -o loop,ro "${OLD_ISO}" old_iso
do_mount -t squashfs "${source_installer}" old_installer
add_overlay old_installer new_installer

CORE_SNAP="$(cd old_installer/var/lib/snapd/seed/snaps/; ls -1 core*.snap)"

cat <<EOF > new_installer/var/lib/snapd/seed/seed.yaml
snaps:
 - name: core
   channel: stable
   file: "${CORE_SNAP}"
 - name: subiquity
   unasserted: true
   classic: true
   file: "${SUBIQUITY_SNAP}"
EOF

rm -f new_installer/var/lib/snapd/seed/assertions/subiquity*.assert
rm -f new_installer/var/lib/snapd/seed/snaps/subiquity*.snap
cp "${SUBIQUITY_SNAP_PATH}" new_installer/var/lib/snapd/seed/snaps/

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

xorriso -as mkisofs -r -checksum_algorithm_iso md5,sha1 \
	-V Ubuntu\ custom\ amd64 \
	-o "${NEW_ISO}" \
	-cache-inodes -l \
	-b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot \
	-boot-load-size 4 -boot-info-table \
	-eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
	-isohybrid-gpt-basdat -isohybrid-apm-hfsplus \
	-isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin  \
	new_iso/boot new_iso
