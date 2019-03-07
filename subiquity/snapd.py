# Copyright 2019 Canonical, Ltd.
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

import json
import logging
import os
import time
from urllib.parse import (
    quote_plus,
    urlencode,
    )

from subiquitycore.utils import run_command

import requests_unixsocket


log = logging.getLogger('subiquity.snapd')

# Every method in this module blocks. Do not call them from the main thread!


class SnapdConnection:
    def __init__(self, root, sock):
        self.root = root
        self.url_base = "http+unix://{}/".format(quote_plus(sock))
        self.session = requests_unixsocket.Session()

    def get(self, path, **args):
        if args:
            path += '?' + urlencode(args)
        return self.session.get(self.url_base + path, timeout=60)

    def configure_proxy(self, proxy):
        log.debug("restarting snapd to pick up proxy config")
        dropin_dir = os.path.join(
            self.root, 'etc/systemd/system/snapd.service.d')
        os.makedirs(dropin_dir, exist_ok=True)
        with open(os.path.join(dropin_dir, 'snap_proxy.conf'), 'w') as fp:
            fp.write(proxy.proxy_systemd_dropin())
        if self.root == '/':
            cmds = [
                ['systemctl', 'daemon-reload'],
                ['systemctl', 'restart', 'snapd.service'],
                ]
        else:
            cmds = [['sleep', '2']]
        for cmd in cmds:
            run_command(cmd)


class FakeResponse:

    def __init__(self, path):
        self.path = path

    def raise_for_status(self):
        pass

    def json(self):
        with open(self.path) as fp:
            return json.load(fp)


class FakeSnapdConnection:
    def __init__(self, snap_data_dir):
        self.snap_data_dir = snap_data_dir

    def configure_proxy(self, proxy):
        log.debug("pretending to restart snapd to pick up proxy config")
        time.sleep(2)

    def get(self, path, **args):
        log.debug("snapd get %s %s", path, args)
        filename = path.replace('/', '-')
        if args:
            filename += '-' + urlencode(sorted(args.items()))
        filepath = os.path.join(self.snap_data_dir, filename + '.json')
        if os.path.exists(filepath):
            return FakeResponse(filepath)
        raise Exception(
            "Don't know how to fake response to {}".format((path, args)))
