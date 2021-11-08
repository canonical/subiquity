#!/bin/bash
set -eux
IMAGE=$1
SCRIPT=$2
TESTER=${IMAGE##*:}

lxd init --auto

if [ -z "$(lxc list -f csv | grep $TESTER)" ]
then
    lxc launch $IMAGE $TESTER
    lxc config device add $TESTER code disk source=`pwd` path=/subiquity
else
    lxc start $TESTER
fi
# copy is allowed to fail, in case the subiquity directory being tested
# includes some uncopyable stuff
lxc exec $TESTER -- sh -ec "
    cd ~
    sudo cp -a /subiquity . || true
    [ -d ~/subiquity ]
    "

attempts=0
while ! lxc file pull $TESTER/etc/resolv.conf - 2> /dev/null | grep -q ^nameserver; do
    sleep 1
    attempts=$((attempts+1))
    if [ $attempts -gt 30 ]; then
        lxc file pull $TESTER/etc/resolv.conf
        lxc exec $TESTER -- ps aux
        echo "Network failed to come up after 30 seconds"
        exit 1
    fi
done
if ! lxc file pull $TESTER/etc/resolv.conf - 2> /dev/null | grep ^nameserver | grep -qv 127.0.0.53
then
    echo "systemd-resolved"
    while ! lxc file pull $TESTER/run/systemd/resolve/resolv.conf - 2> /dev/null | grep -v fe80 | grep -q ^nameserver; do
        sleep 1
        attempts=$((attempts+1))
        if [ $attempts -gt 30 ]; then
            echo "Network failed to come up after 30 seconds"
            exit 1
        fi
    done
fi

lxc exec $TESTER -- cloud-init status --wait

lxc exec $TESTER -- sh -ec "
    cd ~/subiquity
    ./scripts/installdeps.sh
    $SCRIPT"

lxc stop $TESTER