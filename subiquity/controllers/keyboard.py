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


from subiquitycore.controller import BaseController

from subiquity.ui.views import KeyboardView


class KeyboardController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.keyboard
        self.model.parse("/usr/share/X11/xkb/rules/base.xml")

    def default(self):
        title = "Keyboard configuration"
        if self.opts.run_on_serial:
            excerpt = 'Please select the layout of the keyboard directly attached to the system, if any.'
        else:
            excerpt = 'Please select your keyboard layout below, or select "Identify keyboard" to detect your layout automatically.'
        footer = _("Use UP, DOWN and ENTER keys to select your keyboard.")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        view = KeyboardView(self.model, self, self.opts)
        self.ui.set_body(view)

    def done(self, layout, variant):
        self.model.set_keyboard(layout, variant)
        self.signal.emit_signal('next-screen')

    def cancel(self):
        self.signal.emit_signal('prev-screen')
