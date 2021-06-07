#!/bin/bash
set -eux
IMAGE=$1
SCRIPT=$2

lxd init --auto

lxc launch $IMAGE tester
lxc config device add tester code disk source=`pwd` path=/subiquity
# copy is allowed to fail, in case the subiquity directory being tested
# includes some uncopyable stuff
lxc exec tester -- sh -ec "
    cd ~
    sudo cp -a /subiquity . || true
    [ -d ~/subiquity ]
    "

attempts=0
while ! lxc file pull tester/etc/resolv.conf - 2> /dev/null | grep -q ^nameserver; do
    sleep 1
    attempts=$((attempts+1))
    if [ $attempts -gt 30 ]; then
        lxc file pull tester/etc/resolv.conf
        lxc exec tester -- ps aux
        echo "Network failed to come up after 30 seconds"
        exit 1
    fi
done
if ! lxc file pull tester/etc/resolv.conf - 2> /dev/null | grep ^nameserver | grep -qv 127.0.0.53
then
    echo "systemd-resolved"
    while ! lxc file pull tester/run/systemd/resolve/resolv.conf - 2> /dev/null | grep -v fe80 | grep -q ^nameserver; do
        sleep 1
        attempts=$((attempts+1))
        if [ $attempts -gt 30 ]; then
            echo "Network failed to come up after 30 seconds"
            exit 1
        fi
    done
fi

lxc exec tester -- sh -ec "
    cd ~/subiquity
    ./scripts/installdeps.sh
    $SCRIPT"
