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
from urwid import (WidgetWrap, ListBox, Pile, BoxAdapter,
                   Text, Columns)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import (done_btn,
                                  reset_btn,
                                  cancel_btn,
                                  menu_btn)
from subiquity.ui.utils import Padding, Color
from subiquity.ui.interactive import (StringEditor, IntegerEditor, Selector)
from subiquity.models.filesystem import (_humanize_size,
                                         _dehumanize_size,
                                         HUMAN_UNITS)
from subiquity.view import ViewPolicy

INVALID_PARTITION_SIZE = 'Invalid Partition Size'
PARTITION_SIZE_TOO_BIG = 'Requested size too big'
PARTITION_ERRORS = [
    INVALID_PARTITION_SIZE,
    PARTITION_SIZE_TOO_BIG,
]


log = logging.getLogger('subiquity.filesystem')


class DiskInfoView(WidgetWrap):
    def __init__(self, model, signal, hdparm):
        self.model = model
        self.signal = signal
        hdparm = hdparm.split("\n")
        body = []
        for h in hdparm:
            body.append(Text(h))
        body.append(Padding.center_20(self._build_buttons()))
        super().__init__(Padding.center_79(SimpleList(body)))

    def _build_buttons(self):
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
        ]
        return Pile(buttons)

    def done(self, result):
        ''' Return to FilesystemView '''
        self.signal.emit_signal('filesystem:show')

    def cancel(self, button):
        self.signal.emit_signal('filesystem:show')


class AddPartitionView(WidgetWrap):

    def __init__(self, model, signal, selected_disk):
        self.model = model
        self.signal = signal
        self.selected_disk = self.model.get_disk(selected_disk)

        self.partnum = IntegerEditor(
            caption="",
            default=self.selected_disk.lastpartnumber + 1)
        self.size_str = _humanize_size(self.selected_disk.freespace)
        self.size = StringEditor(
            caption="".format(self.size_str))
        self.mountpoint = StringEditor(caption="", edit_text="/")
        self.fstype = Selector(opts=self.model.supported_filesystems)
        body = [
            Columns(
                [
                    ("weight", 0.2, Text("Adding partition to {}".format(
                        self.selected_disk.devpath), align="right")),
                    ("weight", 0.3, Text(""))
                ]
            ),
            Padding.line_break(""),
            self._container(),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons())
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

    def _format_edit(self):
        return Pile(self.fstype.group)

    def _container(self):
        total_items = [
            Columns(
                [
                    ("weight", 0.2, Text("Partition number", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.partnum,
                                        focus_map="string_input focus"))
                ], dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2,
                     Text("Size (max {})".format(self.size_str),
                          align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.size,
                                        focus_map="string_input focus")),
                ], dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Format", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self._format_edit(),
                                        focus_map="string_input focus"))
                ], dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Mount", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.mountpoint,
                                        focus_map="string_input focs"))
                ], dividechars=4
            )
        ]
        return Pile(total_items)

    def cancel(self, button):
        self.signal.emit_signal('filesystem:show')

    def done(self, result):
        """ partition spec

        { 'partition_number': Int,
          'size': Int(M|G),
          'format' Str(ext4|btrfs..,
          'mount_point': Str
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
                      self.selected_disk.freespace))
            if self.size.value == '' or \
               self.size.value == self.size_str:
                log.debug('Using default value: {}'.format(
                          self.selected_disk.freespace))
                return int(self.selected_disk.freespace)
            else:
                # 120B 120
                valid_size = __get_valid_size(self.size.value)
                if len(valid_size) == 0:
                    return INVALID_PARTITION_SIZE

                self.size.value = __append_unit(valid_size)
                log.debug('dehumanize_size({})'.format(self.size.value))
                sz = _dehumanize_size(self.size.value)
                if sz > self.selected_disk.freespace:
                    log.debug(
                        'Input size too big for device: ({} > {})'.format(
                            sz, self.selected_disk.freespace))
                    log.warn('Capping size @ max freespace: {}'.format(
                        self.selected_disk.freespace))
                    sz = self.selected_disk.freespace
                return sz

        result = {
            "partnum": self.partnum.value,
            "raw_size": self.size.value,
            "bytes": __get_size(),
            "fstype": self.fstype.value,
            "mountpoint": self.mountpoint.value
        }

        # Validate size (bytes) input
        if result['bytes'] in PARTITION_ERRORS:
            log.error(result['bytes'])
            self.size.set_error('ERROR: {}'.format(result['bytes']))
            self.signal.emit_signal(
                'filesystem:add-disk-partiion',
                self.selected_disk)
            return
        # Validate mountpoint input
        all_mounts = self.model.get_mounts()
        if self.mountpoint.value in all_mounts:
            log.error('provided mountpoint already allocated'
                      ' ({})'.format(self.mountpoint.value))
            # FIXME: update the error message widget instead
            self.mountpoint.set_error('ERROR: already mounted')
            self.signal.emit_signal(
                'filesystem:add-disk-partiion',
                self.selected_disk)
            return
        log.debug("Add Partition Result: {}".format(result))
        self.signal.emit_signal(
            'filesystem:finish-add-disk-partition',
            self.selected_disk.devpath, result)


class DiskPartitionView(WidgetWrap):
    def __init__(self, model, signal, selected_disk):
        self.model = model
        self.signal = signal
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(self.selected_disk)

        self.body = [
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_menu()),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        partitioned_disks = []

        for mnt, size, fstype, path in self.disk_obj.get_fs_table():
            mnt = Text(mnt)
            size = Text("{}".format(_humanize_size(size)))
            fstype = Text(fstype) if fstype else '-'
            path = Text(path) if path else '-'
            partition_column = Columns([
                (15, path),
                size,
                fstype,
                mnt
            ], 4)
            partitioned_disks.append(partition_column)
        free_space = _humanize_size(self.disk_obj.freespace)
        partitioned_disks.append(Columns([
            (15, Text("FREE SPACE")),
            Text(free_space),
            Text(""),
            Text("")
        ], 4))

        return BoxAdapter(SimpleList(partitioned_disks, is_selectable=False),
                          height=len(partitioned_disks))

    def _build_menu(self):
        """
        Builds the add partition menu with user visible
        changes to the button depending on if existing
        partitions exist or not.
        """
        return Pile([self.add_partition_w(),
                     self.create_swap_w(),
                     self.show_disk_info_w()])

    def show_disk_info_w(self):
        """ Runs hdparm against device and displays its output
        """
        text = ("Show disk information")
        return Color.menu_button(
            menu_btn(
                label=text,
                on_press=self.show_disk_info
            ), focus_map='menu_button focus')

    def create_swap_w(self):
        """ Handles presenting an enabled create swap on
        entire device button if no partition exists, otherwise
        it is disabled.
        """
        text = ("Format or create swap on entire "
                "device (unusual, advanced)")
        if len(self.model.get_partitions()) == 0:
            return Color.menu_button(menu_btn(label=text,
                                              on_press=self.create_swap),
                                     focus_map='menu_button focus')
        return Color.info_minor(Text(text))

    def add_partition_w(self):
        """ Handles presenting the add partition widget button
        depending on if partitions exist already or not.
        """
        text = "Add first GPT partition"
        if len(self.model.get_partitions()) > 0:
            text = "Add partition (max size {})".format(
                _humanize_size(self.disk_obj.freespace))
        return Color.menu_button(menu_btn(label=text,
                                          on_press=self.add_partition),
                                 focus_map='menu_button focus')

    def show_disk_info(self, result):
        self.signal.emit_signal('filesystem:show-disk-information',
                                self.selected_disk)

    def add_partition(self, result):
        log.debug('add_partition: result={}'.format(result))
        self.signal.emit_signal('filesystem:add-disk-partition',
                                self.selected_disk)

    def create_swap(self, result):
        self.signal.emit_signal('filesystem:create-swap-entire-device')

    def done(self, result):
        ''' Return to FilesystemView '''
        self.signal.emit_signal('filesystem:show')

    def cancel(self, button):
        self.signal.emit_signal('filesystem:show')


class FilesystemView(ViewPolicy):
    def __init__(self, model, signal):
        log.debug('FileSystemView init start()')
        self.model = model
        self.signal = signal
        self.items = []
        self.model.probe_storage()  # probe before we complete
        self.body = [
            Padding.center_79(Text("FILE SYSTEM")),
            Padding.center_79(self._build_partition_list()),
            Padding.line_break(""),
            Padding.center_79(Text("AVAILABLE DISKS")),
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_menu()),
            Padding.line_break(""),
            Padding.center_79(self._build_used_disks()),
            Padding.center_15(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))
        log.debug('FileSystemView init complete()')

    def _build_used_disks(self):
        log.debug('FileSystemView: building used disks')
        pl = []
        for disk in self.model.get_used_disk_names():
            log.debug('used disk: {}'.format(disk))
            pl.append(Text(disk))
        if len(pl):
            return Pile(
                [Text("USED DISKS"),
                 Padding.line_break("")] + pl +
                [Padding.line_break("")]
            )

        return Pile(pl)

    def _build_partition_list(self):
        log.debug('FileSystemView: building part list')
        pl = []
        if len(self.model.get_partitions()) == 0:
            pl.append(Color.info_minor(
                Text("No disks or partitions mounted")))
            log.debug('FileSystemView: no partitions')
            return Pile(pl)
        log.debug('FileSystemView: weve got partitions!')
        for dev in self.model.devices.values():
            for mnt, size, fstype, path in dev.get_fs_table():
                mnt = Text(mnt)
                size = Text("{}".format(_humanize_size(size)))
                fstype = Text(fstype) if fstype else '-'
                path = Text(path) if path else '-'
                partition_column = Columns([
                    (15, path),
                    size,
                    fstype,
                    mnt
                ], 4)
                pl.append(partition_column)
        log.debug('FileSystemView: build-part-list done')
        return Pile(pl)

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        buttons = []

        # don't enable done botton if we can't install
        if self.model.installable():
            buttons.append(
                Color.button(done_btn(on_press=self.done),
                             focus_map='button focus'))

        buttons.append(Color.button(reset_btn(on_press=self.reset),
                                    focus_map='button focus'))

        return Pile(buttons)

    def _get_percent_free(self, device):
        ''' return the device free space and percentage
            of the whole device'''
        percent = "%d" % (
            int((1.0 - (device.usedspace / device.size)) * 100))
        free = _humanize_size(device.freespace)
        rounded = "{}{}".format(int(float(free[:-1])), free[-1])
        return (rounded, percent)

    def _build_model_inputs(self):
        log.debug('FileSystemView: building model inputs')
        col_1 = []
        col_2 = []

        avail_disks = self.model.get_available_disk_names()
        if len(avail_disks) == 0:
            return Pile([Color.info_minor(Text("No available disks."))])

        for dname in avail_disks:
            disk = self.model.get_disk_info(dname)
            device = self.model.get_disk(dname)
            btn = menu_btn(label=disk.name,
                           on_press=self.show_disk_partition_view)

            col_1.append(
                Color.menu_button(btn, focus_map='menu_button focus'))
            disk_sz = _humanize_size(disk.size)
            log.debug('device partitions: {}'.format(len(device.partitions)))
            # if we've consumed some of the device, show
            # the remaining space and percentage of the whole
            if len(device.partitions) > 0:
                free, percent = self._get_percent_free(device)
                disk_sz = "{} ({}%) free".format(free, percent)
            col_2.append(Text(disk_sz))

        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))
        col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                           height=len(col_2))
        return Columns([(15, col_1), col_2], 2)

    def _build_menu(self):
        log.debug('FileSystemView: building menu')
        opts = []
        for opt, sig, _ in self.model.get_menu():
            opts.append(
                Color.menu_button(
                    menu_btn(label=opt,
                             on_press=self.on_fs_menu_press),
                    focus_map='menu_button focus'))
        return Pile(opts)

    def on_fs_menu_press(self, result):
        self.signal.emit_signal(
            self.model.get_signal_by_name(result.label))

    def cancel(self, button):
        self.signal.emit_signal(self.model.get_previous_signal)

    def reset(self, button):
        self.signal.emit_signal('filesystem:show', True)

    def done(self, button):
        actions = self.model.get_actions()
        self.signal.emit_signal('filesystem:finish', False, actions)

    def show_disk_partition_view(self, partition):
        self.signal.emit_signal('filesystem:show-disk-partition',
                                partition.label)
