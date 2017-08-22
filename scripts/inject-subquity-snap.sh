#!/bin/bash

set -eux

# inject-subquity-snap.sh $old_iso $subiquity_snap $new_iso

OLD_ISO=$(readlink -f $1)
SUBIQUITY_SNAP_PATH=$(readlink -f $2)
SUBIQUITY_SNAP=$(basename $SUBIQUITY_SNAP_PATH)
NEW_ISO=$(readlink -f $3)

tmpdir=$(mktemp -d)
cd $tmpdir

MOUNTS=()

add_mount() {
    MOUNTS=($1 ${MOUNTS[@]+"${MOUNTS[@]}"})
}

cleanup () {
    for m in ${MOUNTS[@]+"${MOUNTS[@]}"}; do
        umount $m
    done
    rm -rf $tmpdir
}

trap cleanup EXIT

add_overlay() {
    lower=$1
    mountpoint=$2
    work=$(mktemp -dp $tmpdir)
    upper=$(mktemp -dp $tmpdir)
    mount -t overlay overlay -o lowerdir=$lower,upperdir=$upper,workdir=$work $mountpoint
    add_mount $mountpoint
}

mkdir old_iso

mount -t iso9660 -o loop $OLD_ISO old_iso
add_mount old_iso

mkdir old_installer

mount -t squashfs old_iso/casper/installer.squashfs old_installer
add_mount old_installer

mkdir new_installer
add_overlay old_installer new_installer


CORE_SNAP=$(cd old_installer/var/lib/snapd/seed/snaps/; ls -1 core*.snap)

cat <<EOF > new_installer/var/lib/snapd/seed/seed.yaml
snaps:
 - name: core
   channel: stable
   file: ${CORE_SNAP}
 - name: subiquity
   unasserted: true
   classic: true
   file: ${SUBIQUITY_SNAP}
EOF

rm -f new_installer/var/lib/snapd/seed/assertions/subiquity*.assert
rm -f new_installer/var/lib/snapd/seed/snaps/subiquity*.snap
cp $SUBIQUITY_SNAP_PATH new_installer/var/lib/snapd/seed/snaps/

mkdir new_iso
add_overlay old_iso new_iso
rm new_iso/casper/installer.squashfs
mksquashfs new_installer new_iso/casper/installer.squashfs

xorriso -as mkisofs -r -checksum_algorithm_iso md5,sha1 \
	-V Ubuntu\ custom\ amd64 \
	-o $NEW_ISO \
	-cache-inodes -J -l \
	-b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot \
	-boot-load-size 4 -boot-info-table \
	-eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
	-isohybrid-gpt-basdat -isohybrid-apm-hfsplus \
	-isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin  \
	new_iso/boot new_iso


