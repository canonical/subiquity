# Copyright 2017 Canonical, Ltd.
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
import os
import shlex

from subiquity.utils import run_command

log = logging.getLogger("console_conf.models.proxy")

class ProxyModel:
    root = '/'

    def __init__(self, opts):
        self.opts = opts
        if self.opts.dry_run:
            self.root = os.path.abspath(".subiquity")
            os.makedirs(os.path.join(self.root, 'etc'), exist_ok=True)

    def set_proxy(self, new_proxy):
        env_file_path = os.path.join(self.root, 'etc', 'environment')
        new_env_file_path = env_file_path+'.new'
        quoted_proxy = shlex.quote(new_proxy)
        if os.path.exists(env_file_path):
            with open(env_file_path) as env_file:
                with open(new_env_file_path, 'w') as new_env_file:
                    for line in env_file:
                        l = line.strip()
                        if l.startswith("http_proxy=") or l.startswith("https_proxy="):
                            continue
                        new_env_file.write(line)
                    new_env_file.write("http_proxy=" + quoted_proxy + "\n")
                    new_env_file.write("https_proxy=" + quoted_proxy + "\n")
            os.rename(new_env_file_path, env_file_path)
        else:
            with open(env_file_path, 'w') as new_env_file:
                new_env_file.write("http_proxy=" + quoted_proxy + "\n")
                new_env_file.write("https_proxy=" + quoted_proxy + "\n")
        if not self.opts.dry_run:
            run_command(["systemctl", "restart", "snapd"])

    def get_proxy(self):
        env_file_path = os.path.join(self.root, 'etc', 'environment')
        try:
            env_file = open(env_file_path)
        except FileNotFoundError:
            return ""
        with env_file:
            for line in env_file:
                l = line.strip()
                if l.startswith("http_proxy=") or l.startswith("https_proxy="):
                    return shlex.split(l.split('=',1)[1])[0]
        return ""
