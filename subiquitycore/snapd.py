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
from urllib.parse import (
    quote_plus,
    urlencode,
    )

import requests_unixsocket


log = logging.getLogger('subiquitycore.snapd')

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

    def post(self, path, body, **args):
        if args:
            path += '?' + urlencode(args)
        return self.session.post(
            self.url_base + path, data=json.dumps(body),
            timeout=60)
