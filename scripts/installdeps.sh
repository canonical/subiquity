#!/bin/bash
set -eux
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade
add-apt-repository -u ppa:mwhudson/devirt < /dev/null
apt-get install -y --no-install-recommends libnl-3-dev libnl-genl-3-dev libnl-route-3-dev libsystemd-dev python3-distutils-extra pkg-config python3.5 python3-pip git lsb-release python3-setuptools gcc python3-dev python3-wheel curtin pep8 python3-pyflakes
pip3 install -r requirements.txt
python3 setup.py build
