# Copyright 2018 Canonical, Ltd.
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

log = logging.getLogger('subiquity.models.proxy')

dropin_template = '''\
[Service]
Environment="HTTP_PROXY={proxy}"
Environment="HTTPS_PROXY={proxy}"
'''


class ProxyModel(object):

    def __init__(self):
        self.proxy = ""

    def proxy_systemd_dropin(self):
        return dropin_template.format(proxy=self.proxy)

    def get_apt_config(self):
        if self.proxy:
            return {
                'http_proxy': self.proxy,
                'https_proxy': self.proxy,
            }
        else:
            return {}

    def render(self):
        if self.proxy:
            return {
                'proxy': {
                    'http_proxy': self.proxy,
                    'https_proxy': self.proxy,
                    },
                'write_files': {
                    'snapd_dropin': {
                        'path': ('etc/systemd/system/'
                                 'snapd.service.d/snap_proxy.conf'),
                        'content': self.proxy_systemd_dropin(),
                        'permissions': 0o644,
                        },
                    },
                }
        else:
            return {}
