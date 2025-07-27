#!/bin/bash
set -eux

# The purpose of this script is to separate out the actions needed to setup
# LXD on the GitHub Actions CI runners from the actual test setup and 
# execution. This way, test scripts can be mostly run locally without making
# too many changes to the local system.

# The runner images don't have lxd enabled by default.
lxd init --auto

# If the runner image uses docker, then work around a known connectivity issue
# when using lxd and docker at the same time.
# https://discuss.linuxcontainers.org/t/containers-do-not-have-outgoing-internet-access/10844/7
# https://documentation.ubuntu.com/lxd/en/latest/howto/network_bridge_firewalld/#prevent-connectivity-issues-with-lxd-and-docker
if [ "active" == "$(systemctl is-active docker)" ]
then
    iptables  -I DOCKER-USER -i lxdbr0 -j ACCEPT
    iptables  -I DOCKER-USER -o lxdbr0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    # GitHub doesn't use IPV6 (yet?)
    # ip6tables -I DOCKER-USER -i lxdbr0 -j ACCEPT
    # ip6tables -I DOCKER-USER -o lxdbr0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
fi
