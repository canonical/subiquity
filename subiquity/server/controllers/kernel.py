# Copyright 2021 Canonical, Ltd.
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

import os

from subiquitycore.lsb_release import lsb_release

from subiquity.server.controller import NonInteractiveController


class KernelController(NonInteractiveController):

    model_name = autoinstall_key = "kernel"
    autoinstall_default = None
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "package": {"type": "string"},
            "flavor": {"type": "string"},
        },
        "oneOf": [
            {
                "type": "object",
                "required": ["package"],
            },
            {
                "type": "object",
                "required": ["flavor"],
            }
        ],
    }

    def start(self):
        mp_file = os.path.join(
            self.app.base_model.root,
            "run/kernel-meta-package")
        if os.path.exists(mp_file):
            with open(mp_file) as fp:
                kernel_package = fp.read().strip()
            self.model.metapkg_name = kernel_package
        elif self.model.metapkg_name is None:
            self.model.metapkg_name = 'linux-generic'

    def load_autoinstall_data(self, data):
        if data is None:
            return
        package = data.get('package')
        flavor = data.get('flavor')
        if package is None:
            if flavor is None or flavor == 'generic':
                package = 'linux-generic'
            else:
                if flavor is None:
                    package = 'generic'
                else:
                    if flavor == 'hwe':
                        flavor = 'generic-hwe'
                    # Should check this package exists really but
                    # that's a bit tricky until we get cleverer about
                    # the apt config in general.
                    package = 'linux-{flavor}-{release}'.format(
                        flavor=flavor, release=lsb_release()['release'])
        self.model.metapkg_name = package

    def make_autoinstall(self):
        return {'package': self.model.metapkg_name}
