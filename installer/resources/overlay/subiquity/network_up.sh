#!/bin/bash -x

SKIP_IFACE="(lo|lxcbr0)"
rm -f /etc/network/interfaces
echo -e "auto lo\niface lo inet loopback\n" > /etc/network/interfaces 
/bin/ls -1 /sys/class/net | egrep -v "^${SKIP_IFACE}$" | xargs -i bash -c 'D={}; echo -e "auto $D\niface $D inet dhcp"' | tee /etc/network/interfaces
/bin/ls -1 /sys/class/net | egrep -v "^${SKIP_IFACE}$" | xargs -i ifup {}
