#!/bin/bash -x

rm -f /etc/network/interfaces
echo -e "auto lo\niface lo inet loopback\n" > /etc/network/interfaces 
/bin/ls -1 /sys/class/net | grep -v ^lo$ | xargs -i bash -c 'D={}; echo -e "auto $D\niface $D inet dhcp"' | tee /etc/network/interfaces
/bin/ls -1 /sys/class/net | grep -v ^lo$ | xargs -i ifup {}
