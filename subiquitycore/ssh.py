# Copyright 2020 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from subiquitycore.utils import run_command


log = logging.getLogger("subiquitycore.ssh")


def host_key_fingerprints():
    """Query sshd to find the host keys and then fingerprint them.

    Returns a sequence of (key-type, fingerprint) pairs.
    """
    config = run_command(['sshd', '-T'])
    if config.returncode != 0:
        log.debug("sshd -T failed %r", config.stderr)
        return []
    keyfiles = []
    for line in config.stdout.splitlines():
        if line.startswith('hostkey '):
            keyfiles.append(line.split(None, 1)[1])
    info = []
    for keyfile in keyfiles:
        cp = run_command(['ssh-keygen', '-lf', keyfile])
        if cp.returncode != 0:
            log.debug("ssh-keygen -lf %s failed %r", keyfile, cp.stderr)
            continue
        parts = cp.stdout.strip().split()
        length, fingerprint, host, keytype = parts
        keytype = keytype.strip('()')
        info.append((keytype, fingerprint))
    return info


host_keys_intro = _("""\
The host key fingerprints are:
""")

host_key_tmpl = """
    {keytype:{width}} {fingerprint}"""

single_host_key_tmpl = _("""\
The {keytype} host key fingerprints is:
    {fingerprint}
""")


def host_key_info():
    fingerprints = host_key_fingerprints()
    if len(fingerprints) == 0:
        return ''
    if len(fingerprints) == 1:
        [(keytype, fingerprint)] = fingerprints
        return _(single_host_key_tmpl).format(keytype=keytype,
                                              fingerprint=fingerprint)
    lines = [_(host_keys_intro)]
    longest_type = max([len(keytype) for keytype, _ in fingerprints])
    for keytype, fingerprint in fingerprints:
        lines.append(host_key_tmpl.format(keytype=keytype,
                                          fingerprint=fingerprint,
                                          width=longest_type))
    return "".join(lines)


def get_ips_standalone():
    from probert.prober import Prober
    from subiquitycore.models.network import NETDEV_IGNORED_IFACE_TYPES
    prober = Prober()
    prober.probe_network()
    links = prober.get_results()['network']['links']
    ips = []
    for link in sorted(links, key=lambda link: link['netlink_data']['name']):
        if link['type'] in NETDEV_IGNORED_IFACE_TYPES:
            continue
        for addr in link['addresses']:
            if addr['scope'] == "global":
                ips.append(addr['address'].split('/')[0])
    return ips
