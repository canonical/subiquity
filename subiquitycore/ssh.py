# Copyright 2020 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import pwd
from pathlib import Path

from subiquitycore.utils import run_command

log = logging.getLogger("subiquitycore.ssh")


def host_key_fingerprints():
    """Query sshd to find the host keys and then fingerprint them.

    Returns a sequence of (key-type, fingerprint) pairs.
    """
    try:
        config = run_command(["sshd", "-T"])
    except FileNotFoundError:
        log.debug("sshd not found")
        return []
    if config.returncode != 0:
        log.debug("sshd -T failed %r", config.stderr)
        return []
    keyfiles = []
    for line in config.stdout.splitlines():
        if line.startswith("hostkey "):
            keyfiles.append(line.split(None, 1)[1])
    info = []
    for keyfile in keyfiles:
        info.extend(fingerprints(keyfile))
    return info


def fingerprints(keyfile):
    info = []
    cp = run_command(["ssh-keygen", "-lf", keyfile])
    if cp.returncode != 0:
        log.debug("ssh-keygen -lf %s failed %r", keyfile, cp.stderr)
        return info
    for line in cp.stdout.splitlines():
        parts = line.strip().replace("\r", "").split()
        fingerprint = parts[1]
        keytype = parts[-1].strip("()")
        info.append((keytype, fingerprint))
    return info


host_keys_intro = _(
    """\
The host key fingerprints are:
"""
)

host_key_tmpl = """
    {keytype:{width}} {fingerprint}"""

single_host_key_tmpl = _(
    """\
The {keytype} host key fingerprint is:
    {fingerprint}
"""
)


def host_key_info(runtime_state_dir=None):
    if runtime_state_dir:
        # host fingerprints information may have already been prepared by the
        # platform glue
        host_fingerprints = Path(runtime_state_dir) / "host-fingerprints.txt"
        log.debug(
            "pre-made host finterprints %s present: %s",
            host_fingerprints,
            host_fingerprints.is_file(),
        )
        if host_fingerprints.is_file():
            with open(host_fingerprints, "r") as fp:
                return fp.read()

    return summarize_host_keys(host_key_fingerprints())


def summarize_host_keys(fingerprints):
    if len(fingerprints) == 0:
        return ""
    if len(fingerprints) == 1:
        [(keytype, fingerprint)] = fingerprints
        return _(single_host_key_tmpl).format(keytype=keytype, fingerprint=fingerprint)
    lines = [_(host_keys_intro)]
    longest_type = max([len(keytype) for keytype, _ in fingerprints])
    for keytype, fingerprint in fingerprints:
        lines.append(
            host_key_tmpl.format(
                keytype=keytype, fingerprint=fingerprint, width=longest_type
            )
        )
    return "".join(lines)


def user_key_fingerprints(username):
    try:
        user_info = pwd.getpwnam(username)
    except KeyError:
        log.exception("getpwnam(%s) failed", username)
        return []
    user_key_file = "{}/.ssh/authorized_keys".format(user_info.pw_dir)
    if os.path.exists(user_key_file):
        return fingerprints(user_key_file)
    else:
        return []


def get_ips_standalone():
    from probert.prober import Prober

    from subiquitycore.models.network import NETDEV_IGNORED_IFACE_TYPES

    prober = Prober()
    prober.probe_network(with_wlan_listener=False)
    links = prober.get_results()["network"]["links"]
    ips = []
    for link in sorted(links, key=lambda link: link["netlink_data"]["name"]):
        if link["type"] in NETDEV_IGNORED_IFACE_TYPES:
            continue
        for addr in link["addresses"]:
            if addr["scope"] == "global":
                ips.append(addr["address"].split("/")[0])
    return ips
