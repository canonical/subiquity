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
""" Mirror View.
Select the Ubuntu archive mirror.

"""
import logging
from urwid import connect_signal

from subiquitycore.view import BaseView
from subiquitycore.ui.form import (
    Form,
    URLField,
)


log = logging.getLogger('subiquity.ui.views.mirror')

mirror_help = _(
    "You may provide an archive mirror that will be used instead "
    "of the default.")


class MirrorForm(Form):

    cancel_label = _("Back")

    url = URLField(_("Mirror address:"), help=mirror_help)


class MirrorView(BaseView):

    title = _("Configure Ubuntu archive mirror")
    excerpt = _("If you use an alternative mirror for Ubuntu, enter its "
                "details here.")

    def __init__(self, controller, mirror):
        self.controller = controller

        self.form = MirrorForm(initial={'url': mirror})

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(excerpt=_(self.excerpt)))

    def done(self, result):
        log.debug("User input: {}".format(result.as_data()))
        self.controller.done(result.url.value)

    def cancel(self, result=None):
        self.controller.cancel()
