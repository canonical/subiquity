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

from subiquity.ui.views import InstallpathView, MAASView

log = logging.getLogger('subiquity.controller.installpath')


class InstallpathController(BaseController):
    signals = [
        ('menu:installpath:main',       'installpath'),
        ('installpath:install-ubuntu',  'install_ubuntu'),
        ('installpath:maas-region',     'install_maas_region'),
        ('installpath:maas-rack',       'install_maas_rack'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.installpath

    def installpath(self):
        title = "Ubuntu %s"%(lsb_release.get_distro_information()['RELEASE'],)
        excerpt = _("Welcome to Ubuntu! The world's favorite platform "
                   "for clouds, clusters, and amazing internet things. "
                   "This is the installer for Ubuntu on servers and "
                   "internet devices.")
        footer = _("Use UP, DOWN arrow keys, and ENTER, to "
                  "navigate options")

        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(InstallpathView(self.model, self.signal))

    default = installpath

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def install_ubuntu(self):
        self.model.path = 'ubuntu'
        log.debug("Installing Ubuntu path chosen.")
        self.signal.emit_signal('next-screen')

    def install_maas_region(self):
        # show region questions, seed model
        self.model.path = 'region'
        title = "Metal as a Service (MAAS) Regional Controller Setup"
        excerpt = _(
            "MAAS runs a software-defined data centre - it turns a "
            "collection of physical servers and switches into a bare "
            "metal cloud with full open source IP address management "
            "(IPAM) and instant provisioning on demand. By choosing "
            "to install MAAS, a MAAS Region Controller API server and "
            "PostgreSQL database will be installed."
            )
        self.ui.set_header(title, excerpt)
        self.ui.set_footer("")
        self.ui.set_body(MAASView(self.model, self))

    def install_maas_rack(self):
        # show cack questions, seed model
        self.model.path = 'rack'
        title = "Metal as a Service (MAAS) Rack Controller Setup"
        excerpt = _(
            "The MAAS rack controller (maas-rackd) provides highly available, fast "
            "and local broadcast services to the machines provisioned by MAAS. You "
            "need a MAAS rack controller attached to each fabric (which is a set of "
            "trunked switches). You can attach multiple rack controllers to these "
            "physical networks for high availability, with secondary rack controllers "
            "automatically stepping to provide these services if the primary rack "
            "controller fails. By choosing to install a MAAS Rack controller, you will "
            "have to connect it to a Region controller to service your machines."
            )

        self.ui.set_header(title, excerpt)
        self.ui.set_footer("")
        self.ui.set_body(MAASView(self.model, self))

    def setup_maas(self, result):
        self.model.update(result)
        self.signal.emit_signal('next-screen')
