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

log = logging.getLogger('subiquitycore.models.proxy')


class ProxyModel(object):

    def __init__(self):
        self.proxy = ""

    def etc_environment_content(self):
        env_lines = []
        with open("/etc/environment") as fp:
            for line in fp:
                if line.startswith('http_proxy=') or line.startswith('https_proxy='):
                    continue
                if not line.endswith('\n'):
                    line += '\n'
                env_lines.append(line)
        env_lines.append("http_proxy={}\n".format(self.proxy))
        env_lines.append("https_proxy={}\n".format(self.proxy))
        return ''.join(env_lines)
