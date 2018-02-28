#!/bin/bash
set -eux
IMAGE=$1

apt-get -qq update
apt -t trusty-backports install -y lxd

sed -i 's/LXD_IPV4_ADDR=".*"/LXD_IPV4_ADDR="192.168.123.1"/' /etc/default/lxd-bridge
sed -i 's/LXD_IPV4_NETMASK=".*"/LXD_IPV4_NETMASK="255.255.255.0"/' /etc/default/lxd-bridge
sed -i 's/LXD_IPV4_NETWORK=".*"/LXD_IPV4_NETWORK="192.168.123.0\/24"/' /etc/default/lxd-bridge
sed -i 's/LXD_IPV4_DHCP_RANGE=".*"/LXD_IPV4_DHCP_RANGE="192.168.123.2,192.168.123.12"/' /etc/default/lxd-bridge
sed -i 's/LXD_IPV4_DHCP_MAX=".*"/LXD_IPV4_DHCP_MAX="10"/' /etc/default/lxd-bridge
sed -i 's/LXD_IPV6_PROXY=".*"/LXD_IPV6_PROXY="false"/' /etc/default/lxd-bridge

lxd init --auto
service lxd restart

lxc launch $IMAGE tester -c security.privileged=true
lxc config device add tester code disk source=`pwd` path=/subiquity

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

lxc exec tester -- sh -c "cd /subiquity && ./scripts/runtests.sh"
