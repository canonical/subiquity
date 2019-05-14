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

from subiquitycore.controller import BaseController

from subiquity.ui.views import InstallpathView

log = logging.getLogger('subiquity.controller.installpath')


class InstallpathController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.installpath
        self.answers = self.all_answers.get("Installpath", {})
        self.release = None

    def default(self):
        self.ui.set_body(InstallpathView(self.model, self))
        if 'path' in self.answers:
            path = self.answers['path']
            self.model.path = path
            if path == 'ubuntu':
                self.install_ubuntu()
            else:
                self.model.update(self.answers)
                log.debug(
                    "InstallpathController.default next-screen answers=%s",
                    self.answers)
                self.signal.emit_signal('next-screen')

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def serialize(self):
        return {'path': self.model.path, 'results': self.model.results}

    def deserialize(self, data):
        self.model.path = data['path']
        self.model.results = data['results']

    def choose_path(self, path):
        self.model.path = path
        getattr(self, 'install_' + path)()

    def install_ubuntu(self):
        log.debug("InstallpathController.install_ubuntu next-screen")
        self.signal.emit_signal('next-screen')

    def install_cmdline(self):
        log.debug("Installing from command line sources.")
        self.signal.emit_signal('next-screen')
