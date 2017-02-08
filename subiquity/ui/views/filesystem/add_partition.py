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

""" Filesystem

Provides storage device selection and additional storage
configuration.

"""
import logging
import re
from urwid import AttrMap, connect_signal, Text, WidgetDisable, WidgetWrap

from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.interactive import StringEditor, IntegerEditor, Selector
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (_humanize_size,
                                         _dehumanize_size,
                                         HUMAN_UNITS)
from subiquity.ui.mount import MountSelector


log = logging.getLogger('subiquity.ui.filesystem.add_partition')


class Toggleable(WidgetWrap):

    def __init__(self, original, active_color):
        self.original = original
        self.active_color = active_color
        self.enabled = False
        self.enable()

    def enable(self):
        if not self.enabled:
            self._w = AttrMap(self.original, self.active_color, self.active_color + ' focus')
            self.enabled = True

    def disable(self):
        if self.enabled:
            self._w = WidgetDisable(Color.info_minor(self.original))
            self.enabled = False


class ValidatingWidgetSet(WidgetWrap):

    signals = ['validated']

    def __init__(self, captioned, decorated, input, validator):
        self.captioned = captioned
        self.decorated = decorated
        self.input = input
        self.validator = validator
        self.in_error = False
        super().__init__(Pile([captioned]))

    def disable(self):
        self.decorated.disable()
        self.hide_error()

    def enable(self):
        self.decorated.enable()
        self.validate()

    def set_error(self, err_msg):
        in_error = True
        if isinstance(err_msg, tuple):
            if len(err_msg) == 3:
                color, err_msg, in_error = err_msg
            else:
                color, err_msg = err_msg
        else:
            color = 'info_error'
        e = AttrMap(Text(err_msg, align="center"), color)
        t = (e, self._w.options('pack'))
        if len(self._w.contents) > 1:
            self._w.contents[1] = t
        else:
            self._w.contents.append(t)
        self.in_error = in_error

    def hide_error(self):
        if len(self._w.contents) > 1:
            self._w.contents = self._w.contents[:1]
        self.in_error = False

    def has_error(self):
        return self.in_error

    def validate(self):
        if self.validator is not None:
            err = self.validator()
            if err is None:
                self.hide_error()
            else:
                self.set_error(err)
            self._emit('validated')

    def lost_focus(self):
        self.validate()


def vws(caption, input, validator=None):
    text = Text(caption, align="right")
    decorated = Toggleable(input, 'string_input')
    captioned = Columns(
            [
                ("weight", 0.2, text),
                ("weight", 0.3, decorated)
            ],
        dividechars=4)
    return ValidatingWidgetSet(captioned, decorated, input, validator)


class AddPartitionView(BaseView):

    def __init__(self, model, controller, selected_disk):
        log.debug('AddPartitionView: selected_disk=[{}]'.format(selected_disk))
        self.model = model
        self.controller = controller
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(selected_disk)

        self.size_str = _humanize_size(self.disk_obj.freespace)

        self.partnum = IntegerEditor(caption="", default=self.disk_obj.lastpartnumber + 1)
        self.size = StringEditor(caption="")
        self.fstype = Selector(opts=self.model.supported_filesystems)
        self.mountpoint = MountSelector(self.model)

        self.buttons = self._build_buttons()
        body = [
            Columns(
                [
                    ("weight", 0.2, Text("Adding partition to {}".format(
                        self.disk_obj.devpath), align="right")),
                    ("weight", 0.3, Text(""))
                ]
            ),
            Padding.line_break(""),
            self._build_container(),
            Padding.line_break(""),
            Padding.fixed_10(self.buttons),
        ]
        partition_box = Padding.center_50(ListBox(body))
        super().__init__(partition_box)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Toggleable(done, 'button'),
            Color.button(cancel)
        ]
        return Pile(buttons)

    def _validate_size(self):
        v = self.size.value
        if not v:
            return
        r = '(\d+[\.]?\d*)([{}])?$'.format(''.join(HUMAN_UNITS))
        match = re.match(r, v)
        if not match:
            return "Invalid partition size"
        unit = match.group(2)
        if unit is None:
            unit = self.size_str[-1]
            v += unit
            self.size.value = v
        sz = _dehumanize_size(v)
        if sz > self.disk_obj.freespace:
            self.size.value = self.size_str
            return ("info_minor", "Capped partition size at %s"%(self.size_str,), False)

    def _validate_mount(self):
        mnts = self.model.get_mounts2()
        dev = mnts.get(self.mountpoint.value)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, self.mountpoint.value)

    def _build_container(self):

        self.partnum_vws = vws("Partition number", self.partnum)
        self.size_vws = vws("Size (max {})".format(self.size_str), self.size, validator=self._validate_size)
        self.fstype_vws = vws("Format", self.fstype)
        self.mountpoint_vws = vws("Mount", self.mountpoint, validator=self._validate_mount)

        self.all_vws = [
            self.partnum_vws,
            self.size_vws,
            self.fstype_vws,
            self.mountpoint_vws,
        ]
        for vw in self.all_vws:
            connect_signal(vw, 'validated', self._validated)
        return Pile(self.all_vws)

    def _enable_disable_mount(self, enabled):
        if enabled:
            self.mountpoint_vws.enable()
        else:
            self.mountpoint_vws.disable()

    def _validated(self, sender):
        error = False
        for w in self.all_vws:
            if w.has_error():
                error = True
                break
        if error:
            self.buttons[0].disable()
            self.buttons.focus_position = 1
        else:
            self.buttons[0].enable()

    def select_fstype(self, sender, fs):
        if fs.is_mounted != sender.value.is_mounted:
            self._enable_disable_mount(fs.is_mounted)

    def cancel(self, button):
        self.controller.prev_view()

    def done(self, result):

        fstype = self.fstype.value

        if fstype.is_mounted:
            mount = self.mountpoint.value
        else:
            mount = None

        if self.size.value:
            size = _dehumanize_size(self.size.value)
            if size > self.disk_obj.freespace:
                size = self.disk_obj.freespace
        else:
            size = self.disk_obj.freespace

        result = {
            "partnum": self.partnum.value,
            "raw_size": self.size.value,
            "bytes": size,
            "fstype": fstype.label,
            "mountpoint": mount,
        }

        log.debug("Add Partition Result: {}".format(result))
        self.controller.add_disk_partition_handler(self.disk_obj.devpath, result)
