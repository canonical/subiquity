#!/bin/bash
set -eux
apt-get update
apt-get -y dist-upgrade
apt-get install -y --no-install-recommends libnl-3-dev libnl-genl-3-dev libnl-route-3-dev libsystemd-dev python3-distutils-extra pkg-config python3.5 python3-pip git lsb-release python3-setuptools gcc python3-dev python3-wheel curtin
pip3 install -r requirements.txt
python3 setup.py build

python3 -m unittest discover
# The --foreground is important to avoid subiquity getting SIGTTOU-ed.
timeout --foreground 60 sh -c 'LANG=C.UTF-8 PYTHONPATH=. python3 bin/subiquity-tui --answers examples/answers.yaml --dry-run --machine-config examples/mwhudson.json'
