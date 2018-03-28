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

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.installpath
        self.answers = self.all_answers.get("Installpath", {})

    def installpath(self):
        title = "Ubuntu %s"%(lsb_release.get_distro_information()['RELEASE'],)
        excerpt = _("Welcome to Ubuntu! The world's favourite platform "
                   "for clouds, clusters, and amazing internet things. "
                   "This is the installer for Ubuntu on servers and "
                   "internet devices.")
        footer = _("Use UP, DOWN arrow keys, and ENTER, to "
                  "navigate options")

        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(InstallpathView(self.model, self))
        if 'path' in self.answers:
            path = self.answers['path']
            self.model.path = path
            if path == 'ubuntu':
                self.install_ubuntu()
            else:
                self.model.update(self.answers)
                self.signal.emit_signal('next-screen')

    default = installpath

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def choose_path(self, path):
        self.model.path = path
        getattr(self, 'install_' + path)()

    def install_ubuntu(self):
        log.debug("Installing Ubuntu path chosen.")
        self.signal.emit_signal('next-screen')

    def install_maas_region(self):
        # show region questions, seed model
        title = "MAAS Region Controller Setup"
        excerpt = _(
            "MAAS is Metal As A Service. Running on Ubuntu, it lets you "
            "treat physical servers like virtual machines (instances) "
            "in the cloud. Rather than having to manage each server "
            "individually, MAAS turns your bare metal into an elastic "
            "cloud-like resource. \n\nFor further details, see https://maas.io/."
            )
        self.ui.set_header(title, excerpt)
        self.ui.set_footer("")
        self.ui.set_body(MAASView(self.model, self))

    def install_maas_rack(self):
        # show cack questions, seed model
        title = "MAAS Rack Controller Setup"
        excerpt = _(
            "A MAAS rack controller provides services to machines provisioned "
            "by MAAS in the fabric (group of trunked switches) it is attached "
            "to. The rack controller requires the accessible URL of a MAAS "
            "region controller."
            )

        self.ui.set_header(title, excerpt)
        self.ui.set_footer("")
        self.ui.set_body(MAASView(self.model, self))

    def setup_maas(self, result):
        self.model.update(result)
        self.signal.emit_signal('next-screen')
