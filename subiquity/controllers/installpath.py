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

import logging

import lsb_release

from subiquitycore.controller import BaseController
from subiquitycore.ui.dummy import DummyView

from subiquity.models import InstallpathModel
from subiquity.ui.views import InstallpathView

log = logging.getLogger('subiquity.controller.installpath')


class InstallpathController(BaseController):
    signals = [
        ('menu:installpath:main',           'installpath'),
        ('installpath:install-ubuntu',      'install_ubuntu'),
        # ('installpath:maas-region-server',  'install_maas_region_server'),
        # ('installpath:maas-cluster-server', 'install_maas_cluster_server'),
        # ('installpath:test-media',        'test_media'),
        # ('installpath:test-memory',       'test_memory')
    ]

    def __init__(self, common):
        super().__init__(common)
        self.model = InstallpathModel()

    def installpath(self):
        title = "Ubuntu %s"%(lsb_release.get_distro_information()['RELEASE'],)
        excerpt = ("Welcome to Ubuntu! The world's favorite platform "
                   "for clouds, clusters, and amazing internet things. "
                   "This is the installer for Ubuntu on servers and "
                   "internet devices.")
        footer = ("Use UP, DOWN arrow keys, and ENTER, to "
                  "navigate options")

        self.ui.set_header(title, excerpt)
        self.ui.set_body(InstallpathView(self.model, self.signal), footer, 10)

    default = installpath

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def install_ubuntu(self):
        log.debug("Installing Ubuntu path chosen.")
        self.signal.emit_signal('next-screen')

    def install_maas_region_server(self):
        self.ui.set_body(DummyView(self.signal))

    def install_maas_cluster_server(self):
        self.ui.set_body(DummyView(self.signal))

    def test_media(self):
        self.ui.set_body(DummyView(self.signal))

    def test_memory(self):
        self.ui.set_body(DummyView(self.signal))
