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

import attr

from urwid import (
    connect_signal,
    )

from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    IntegerField,
    StringField,
    )
from subiquitycore.ui.selector import (
    Option,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )

from subiquity.models.filesystem import humanize_size

log = logging.getLogger('subiquity.ui.raid')

@attr.s
class RaidLevel:
    name = attr.ib()
    value = attr.ib()
    min_devices = attr.ib()


levels = [
    RaidLevel(_("0 (striped)"), 0, 2),
    RaidLevel(_("1 (mirrored)"), 1, 2),
    RaidLevel(_("5"), 5, 3),
    RaidLevel(_("6"), 6, 4),
    RaidLevel(_("10"), 10, 72),
    ]


class RaidForm(Form):

    name = StringField(_("Name:"))
    level = ChoiceField(_("RAID Level:"), choices=["dummy"])
    size = IntegerField(_("Size:"))


class RaidStretchy(Stretchy):
    def __init__(self, parent, model, controller, devices):
        self.model = model
        self.controller = controller
        self.devices = devices

        self.form = RaidForm()

        connect_signal(self.form.level.widget, 'select', self._select_level)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        opts = []
        for level in levels:
            enabled = len(devices) >= level.min_devices
            opts.append(Option((_(level.name), enabled, level)))
        self.form.level.widget._options = opts
        self.form.level.widget.index = 0

        self.form.size.enabled = False

        super().__init__(self.form.as_screen(self, focus_buttons=False))


    def _select_level(self, sender, new_level):
        self.form.size.value = humanize_size(self.devices[0].size)

    def done(self, result):
        log.debug('raid_done: result = {}'.format(result))
        result = self.form.as_data()
        result['devices'] = self.devices
        self.controller.add_raid()

    def cancel(self, button):
        self.parent.remove_overlay()
