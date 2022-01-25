#!/bin/bash
set -eux
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -o APT::Get::Always-Include-Phased-Updates=true -y dist-upgrade
mkdir -p /etc/systemd/system/zfs-mount.service.d/
cat >/etc/systemd/system/zfs-mount.service.d/override.conf <<EOF
[Unit]
After=zfs-load-module.service
ConditionPathExists=/dev/zfs

EOF
cp -r /etc/systemd/system/zfs-mount.service.d/ /etc/systemd/system/zfs-share.service.d/
systemctl daemon-reload
apt-get install -o APT::Get::Always-Include-Phased-Updates=true -y --no-install-recommends libnl-3-dev libnl-genl-3-dev libnl-route-3-dev libsystemd-dev python3-distutils-extra pkg-config python3.5 python3-pip git lsb-release python3-setuptools gcc python3-dev python3-wheel pep8 python3-pyflakes python3-bson make curl jq build-essential python3-pytest python3-async-timeout language-selector-common python3-pytest-xdist
pip3 install -r requirements.txt

make gitdeps

PYTHONPATH=.:./curtin:./probert python3 setup.py build
