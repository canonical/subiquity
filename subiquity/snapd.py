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
from urllib.parse import (
    quote_plus,
    urlencode,
    )

import requests_unixsocket


log = logging.getLogger('subiquity.snapd')


class SnapdConnection:
    def __init__(self, sock):
        self.url_base = "http+unix://{}/".format(quote_plus(sock))
        self.session = requests_unixsocket.Session()

    def get(self, path, **args):
        if args:
            path += '?' + urlencode(args)
        return self.session.get(self.url_base + path, timeout=60)


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

    def get(self, path, **args):
        filename = path.replace('/', '-')
        if args:
            filename += '-' + urlencode(sorted(args.items()))
        filepath = os.path.join(self.snap_data_dir, filename + '.json')
        if os.path.exists(filepath):
            return FakeResponse(filepath)
        raise Exception(
            "Don't know how to fake response to {}".format((path, args)))
