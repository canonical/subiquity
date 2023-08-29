#!/bin/bash
set -eux
cd "$(dirname ${BASH_SOURCE:0})/.."

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get \
    -o Dpkg::Options::=--force-confnew \
    -o APT::Get::Always-Include-Phased-Updates=true \
    -y dist-upgrade
mkdir -p /etc/systemd/system/zfs-mount.service.d/
cat >/etc/systemd/system/zfs-mount.service.d/override.conf <<EOF
[Unit]
After=zfs-load-module.service
ConditionPathExists=/dev/zfs

EOF
cp -r /etc/systemd/system/zfs-mount.service.d/ /etc/systemd/system/zfs-share.service.d/
systemctl daemon-reload
apt-get install \
    -o APT::Get::Always-Include-Phased-Updates=true \
    -y --no-install-recommends \
    $(cat apt-deps.txt)

make gitdeps

PYTHONPATH=.:./curtin:./probert python3 setup.py build
