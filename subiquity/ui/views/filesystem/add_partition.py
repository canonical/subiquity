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
from urwid import connect_signal, Text, Padding as UrwidPadding, WidgetDisable

from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.interactive import StringEditor, IntegerEditor, Selector
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (_humanize_size,
                                         _dehumanize_size,
                                         HUMAN_UNITS)
from subiquity.ui.mount import MountSelector

INVALID_PARTITION_SIZE = 'Invalid Partition Size'
PARTITION_SIZE_TOO_BIG = 'Requested size too big'
PARTITION_ERRORS = [
    INVALID_PARTITION_SIZE,
    PARTITION_SIZE_TOO_BIG,
]


log = logging.getLogger('subiquity.ui.filesystem.add_partition')

def _col(caption, input, active=True, padding=0):
    text = Text(caption, align="right")
    if active:
        input = Color.string_input(input, focus_map="string_input focus")
    else:
        input = Color.info_minor(WidgetDisable(input))
        text = Color.info_minor(text)
    if padding:
        input = UrwidPadding(input, left=padding)
    return Columns(
            [
                ("weight", 0.2, text),
                ("weight", 0.3, input)
            ],
        dividechars=4)

class AddPartitionView(BaseView):

    def __init__(self, model, controller, selected_disk):
        log.debug('AddPartitionView: selected_disk=[{}]'.format(selected_disk))
        self.model = model
        self.controller = controller
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(selected_disk)

        self.partnum = IntegerEditor(
            caption="",
            default=self.disk_obj.lastpartnumber + 1)
        self.size_str = _humanize_size(self.disk_obj.freespace)
        self.size = StringEditor(
            caption="".format(self.size_str))
        self.mountpoint = MountSelector()
        self.fstype = Selector(opts=self.model.supported_filesystems)
        connect_signal(self.fstype, 'select', self.select_fstype)
        self.pile = self._container()
        body = [
            Columns(
                [
                    ("weight", 0.2, Text("Adding partition to {}".format(
                        self.disk_obj.devpath), align="right")),
                    ("weight", 0.3, Text(""))
                ]
            ),
            Padding.line_break(""),
            self.pile,
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        partition_box = Padding.center_50(ListBox(body))
        super().__init__(partition_box)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def _container(self):
        total_items = [
            _col("Partition number", self.partnum),
            _col("Size (max {})".format(self.size_str), self.size),
            _col("Format", self.fstype),
            _col("Mount", self.mountpoint),
        ]
        return Pile(total_items)

    def _enable_disable_mount(self, enabled):
        self.pile.contents[-1] = (
            _col("Mount", self.mountpoint, enabled),
            self.pile.options('pack'))

    def select_fstype(self, sender, fs):
        if fs.is_mounted != sender.value.is_mounted:
            self._enable_disable_mount(fs.is_mounted)

    def cancel(self, button):
        self.controller.prev_view()

    def done(self, result):
        """ partition spec

        { 'partition_number': Int,
          'size': Int(M|G),
          'format' Str(ext4|btrfs..,
          'mountpoint': Str
        }
        """
        def __get_valid_size(size_str):
            r = '(\d*)(\d+[\.]?\d*)[{}]*$'.format(''.join(HUMAN_UNITS))
            match = re.match(r, size_str)
            log.debug('valid_size: input:{} match:{}'.format(size_str, match))
            if match:
                return match.group(0)

            return ''

        def __append_unit(input_size):
            ''' examine the input for a unit string.
                if not present, use the unit string from
                the displayed maximum size

                returns: number string with unit size
                '''
            unit_regex = '[{}]$'.format(''.join(HUMAN_UNITS))
            input_has_unit = re.findall(unit_regex, input_size)
            log.debug('input:{} re:{}'.format(input_size, input_has_unit))
            if len(input_has_unit) == 0:
                # input does not have unit string
                displayed_unit = re.search(unit_regex, self.size_str)
                log.debug('input:{} re:{}'.format(self.size_str,
                                                  displayed_unit))
                input_size += displayed_unit.group(0)

            return input_size

        def __get_size():
            log.debug('Getting partition size')
            log.debug('size.value={} size_str={} freespace={}'.format(
                      self.size.value, self.size_str,
                      self.disk_obj.freespace))
            if self.size.value == '' or \
               self.size.value == self.size_str:
                log.debug('Using default value: {}'.format(
                          self.disk_obj.freespace))
                return int(self.disk_obj.freespace)
            else:
                # 120B 120
                valid_size = __get_valid_size(self.size.value)
                if len(valid_size) == 0:
                    return INVALID_PARTITION_SIZE

                self.size.value = __append_unit(valid_size)
                log.debug('dehumanize_size({})'.format(self.size.value))
                sz = _dehumanize_size(self.size.value)
                if sz > self.disk_obj.freespace:
                    log.debug(
                        'Input size too big for device: ({} > {})'.format(
                            sz, self.disk_obj.freespace))
                    log.warn('Capping size @ max freespace: {}'.format(
                        self.disk_obj.freespace))
                    sz = self.disk_obj.freespace
                return sz

        fstype = self.fstype.value

        if fstype.is_mounted:
            mount = self.mountpoint.value
        else:
            mount = None

        result = {
            "partnum": self.partnum.value,
            "raw_size": self.size.value,
            "bytes": __get_size(),
            "fstype": fstype.label,
            "mountpoint": mount,
        }

        # Validate size (bytes) input
        if result['bytes'] in PARTITION_ERRORS:
            log.error(result['bytes'])
            self.size.set_error('ERROR: {}'.format(result['bytes']))
            return
        # Validate mountpoint input
        if mount is not None:
            try:
                self.model.valid_mount(result)
            except ValueError as e:
                log.exception('Invalid mount point')
                self.mountpoint.set_error('Error: {}'.format(str(e)))
                log.debug("Invalid mountpoint, try again")
                return

        log.debug("Add Partition Result: {}".format(result))
        self.controller.add_disk_partition_handler(self.disk_obj.devpath, result)
