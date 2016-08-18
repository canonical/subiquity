# Copyright 2015 Canonical, Ltd.
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

import yaml
import sys
import time

from subiquitycore.prober import Prober

# Prevent BS messages from being printed to stderr
# (Also makes debugging impossible, so should probably be smarter here!)
sys.stderr.close()

def output(action, ifname, data=None):
    msg = {'action': action, 'ifname': ifname}
    if data is not None:
        msg['data'] = data
    try:
        sys.stdout.write(yaml.safe_dump(msg)+'\0')
        sys.stdout.flush()
    except BrokenPipeError:
        sys.exit(0)

def _probe():
    NETDEV_IGNORED_IFACES = ['lo', 'bridge', 'tun', 'tap', 'dummy']
    class opts:
        machine_config = None
    prober = Prober(opts)
    network_devices = prober.get_network_devices()

    info = {}

    for iface in network_devices.keys():
        if iface in NETDEV_IGNORED_IFACES:
            continue
        ifinfo = prober.get_network_info(iface)
        del ifinfo.raw['bridge']['options']
        info[iface] = ifinfo.raw

    return info

def _run():
    info = {}
    while 1:
        new_info = _probe()
        new_ifs = set(new_info)
        old_ifs = set(info)
        for new_if in new_ifs - old_ifs:
            output('new_interface', new_if, new_info[new_if])
        for old_if in old_ifs - new_ifs:
            output('remove_interface', old_if)
        for ifname in old_ifs & new_ifs:
            if info[ifname] != new_info[ifname]:
                output('update_interface', ifname, new_info[ifname])
        info = new_info
        time.sleep(1.0)

if __name__ == '__main__':
    _run()
