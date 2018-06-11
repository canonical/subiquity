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
from collections import defaultdict
import logging

import attr
from urwid import (
    AttrMap,
    connect_signal,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.actionmenu import (
    ActionMenu,
    ActionMenuButton,
    )
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    danger_btn,
    done_btn,
    reset_btn,
    )
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import ColSpec, Table, TableRow
from subiquitycore.ui.utils import button_pile, Color, Padding
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    DeviceAction,
    Disk,
    humanize_size,
    )

from .delete import ConfirmDeleteStretchy
from .disk_info import DiskInfoStretchy
from .partition import PartitionStretchy, FormatEntireStretchy

log = logging.getLogger('subiquity.ui.filesystem.filesystem')


confirmation_text = _("""\
Selecting Continue below will begin the installation process and \
result in the loss of data on the disks selected to be formatted.

You will not be able to return to this or a previous screen once \
the installation has started.

Are you sure you want to continue?""")


class FilesystemConfirmation(Stretchy):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        widgets = [
            Text(_(confirmation_text)),
            Text(""),
            button_pile([
                cancel_btn(_("No"), on_press=self.cancel),
                danger_btn(_("Continue"), on_press=self.ok)]),
            ]
        super().__init__(
            _("Confirm destructive action"),
            widgets,
            stretchy_index=0,
            focus_index=2)

    def ok(self, sender):
        self.controller.finish()

    def cancel(self, sender):
        self.parent.remove_overlay()


def _wire_menu_to_row(menu, row):
    assert isinstance(row, AttrMap)
    close_map = row.attr_map.copy()
    open_map = row.focus_map.copy()
    def _open(menu):
        row.set_attr_map(open_map)
    def _close(menu):
        row.set_attr_map(close_map)
    connect_signal(menu, 'open', _open)
    connect_signal(menu, 'close', _close)


@attr.s
class MountInfo:
    mount = attr.ib(default=None)

    @property
    def path(self):
        return self.mount.path

    @property
    def split_path(self):
        return self.mount.path.split('/')

    @property
    def size(self):
        return humanize_size(self.mount.device.volume.size)

    @property
    def fstype(self):
        return self.mount.device.fstype

    @property
    def desc(self):
        return self.mount.device.volume.desc()

    def startswith(self, other):
        i = 0
        for a, b in zip(self.split_path, other.split_path):
            if a != b:
                break
            i += 1
        return i >= len(other.split_path)


class MountList(WidgetWrap):

    def _select_first_selectable(self):
        self._w._select_first_selectable()

    def _select_last_selectable(self):
        self._w._select_last_selectable()

    def __init__(self, parent):
        self.parent = parent
        self.table = Table([], spacing=2, colspecs={
            0:ColSpec(can_scale=True),
            1:ColSpec(min_width=9),
        })
        self._no_mounts_content = Color.info_minor(
            Text(_("No disks or partitions mounted.")))
        super().__init__(self.table)
        self.refresh_model_inputs()

    def _mount_action(self, sender, action, mount):
        log.debug('_mount_action %s %s', action, mount)
        if action == 'unmount':
            self.parent.controller.delete_mount(mount)
            self.parent.refresh_model_inputs()

    def refresh_model_inputs(self):
        mountinfos = [
            MountInfo(mount=m)
            for m in sorted(
                self.parent.model.all_mounts(), key=lambda m: m.path)
        ]
        if len(mountinfos) == 0:
            self._w = self._no_mounts_content
            return
        self._w = self.table
        log.debug('FileSystemView: building mount list')

        rows = [TableRow([
            Text(_("MOUNT POINT")),
            Text(_("SIZE"), align='center'),
            Text(_("TYPE")),
            Text(_("DEVICE TYPE")),
            ])]

        for i, mi in enumerate(mountinfos):
            path_markup = mi.path
            for j in range(i-1, -1, -1):
                mi2 = mountinfos[j]
                if mi.startswith(mi2):
                    part1 = "/".join(mi.split_path[:len(mi2.split_path)])
                    part2 = "/".join(
                        [''] + mi.split_path[len(mi2.split_path):])
                    path_markup = [('grey', part1), part2]
                    break
                if j == 0 and mi2.split_path == ['', '']:
                    path_markup = [
                        ('grey', "/"),
                        "/".join(mi.split_path[1:]),
                        ]
            actions = [(_("Unmount"), mi.mount.can_delete(), 'unmount')]
            menu = ActionMenu(actions)
            connect_signal(menu, 'action', self._mount_action, mi.mount)
            am = AttrMap(
                    TableRow([
                        Text(path_markup),
                        Text(mi.size, align='right'),
                        Text(mi.fstype),
                        Text(mi.desc),
                        menu,
                    ]),
                    {None: 'menu_button', 'grey': 'info_minor'},
                    {None: 'menu_button focus', 'grey': 'menu_button focus'})

            _wire_menu_to_row(menu, am)
            rows.append(am)
        self.table.set_contents(rows)
        if self.table._w.focus_position >= len(rows):
            self.table._w.focus_position = len(rows) - 1


class DeviceList(WidgetWrap):

    def _select_first_selectable(self):
        self._w._select_first_selectable()

    def _select_last_selectable(self):
        self._w._select_last_selectable()

    def __init__(self, parent, show_available):
        self.parent = parent
        self.show_available = show_available
        self.table = Table([],  spacing=2, colspecs={
            0:ColSpec(can_scale=True),
            1:ColSpec(min_width=9),
        })
        if show_available:
            text = _("No available devices")
        else:
            text = _("No used devices")
        self._no_devices_content = Color.info_minor(Text(text))
        super().__init__(self.table)
        self.refresh_model_inputs()
        # I don't really know why this is required:
        self.table._select_first_selectable()

    def _device_action(self, sender, action, device):
        log.debug('_device_action %s %s', action, device)
        overlay = None
        if action == DeviceAction.INFO:
            if isinstance(device, Disk):
                overlay = DiskInfoStretchy(self.parent, device)
        if action == DeviceAction.PARTITION:
                overlay = PartitionStretchy(self.parent, device)
        if action == DeviceAction.FORMAT:
            overlay = FormatEntireStretchy(self.parent, device)
        if overlay is not None:
            self.parent.show_stretchy_overlay(overlay)
        else:
            raise Exception("unexpected action on device")

    def _partition_action(self, sender, action, part):
        log.debug('_partition_action %s %s', action, part)
        overlay = None
        if action == DeviceAction.EDIT:
            overlay = PartitionStretchy(self.parent, part.device, part)
        if action == DeviceAction.DELETE:
            overlay = ConfirmDeleteStretchy(
                self.parent,
                part,
                self.parent.controller.delete_partition)
        if action == DeviceAction.FORMAT:
            overlay = FormatEntireStretchy(self.parent, part)
        if overlay is not None:
            self.parent.show_stretchy_overlay(overlay)
        else:
            raise Exception("unexpected action on partition")

    def _action_menu_for_device(self, device, cb):
        delete_btn = Color.danger_button(ActionMenuButton(_("Delete")))
        device_actions = [
            (_("Information"),    DeviceAction.INFO),
            (_("Edit"),           DeviceAction.EDIT),
            (_("Add Partition"),  DeviceAction.PARTITION),
            (_("Format / Mount"), DeviceAction.FORMAT),
            (delete_btn,          DeviceAction.DELETE),
        ]
        menu = ActionMenu([
            (label, device.supports_action(action), action)
            for label, action in device_actions])
        connect_signal(menu, 'action', cb, device)
        return menu

    def refresh_model_inputs(self):
        devices = [
            d for d in self.parent.model.all_devices()
            if (d.available() == self.show_available
                or (not self.show_available and d.has_unavailable_partition()))
        ]
        if len(devices) == 0:
            self._w = self._no_devices_content
            self.table.table_rows = []
            return
        self._w = self.table
        log.debug('FileSystemView: building device list')
        rows = []

        def _fmt_fs(label, fs):
            r = _("{} {}").format(label, fs.fstype)
            if not self.parent.model.fs_by_name[fs.fstype].is_mounted:
                return r
            m = fs.mount()
            if m:
                r += _(", {}").format(m.path)
            else:
                r += _(", not mounted")
            return r

        def _fmt_constructed(label, device):
            return _("{} part of {} ({})").format(
                label, device.label, device.desc())

        rows.append(TableRow([
            Text(_("DEVICE")),
            Text(_("SIZE"), align="center"),
            Text(_("TYPE")),
        ]))
        for device in devices:
            menu = self._action_menu_for_device(device, self._device_action)
            am = Color.menu_button(TableRow([
                Text(device.label),
                Text("{:>9}".format(humanize_size(device.size))),
                Text(device.desc()),
                menu,
            ]))
            _wire_menu_to_row(menu, am)
            rows.append(am)

            entire_label = None
            if device.fs():
                entire_label = _fmt_fs(
                    _("  entire device formatted as"),
                    device.fs())
            elif device.constructed_device():
                entire_label = _fmt_constructed(
                    _("  entire device"),
                    device.constructed_device())
            if entire_label is not None:
                rows.append(TableRow([
                    Text(entire_label),
                ]))
            else:
                for part in device.partitions():
                    if part.available() != self.show_available:
                        continue
                    prefix = _("  partition {},").format(part._number)
                    if part.flag == "bios_grub":
                        label = prefix + " bios_grub"
                    elif part.fs():
                        label = _fmt_fs(prefix, part.fs())
                    elif part.constructed_device():
                        label = _fmt_constructed(prefix, part)
                    else:
                        label = _("{} not formatted").format(prefix)
                    part_size = "{:>9} ({}%)".format(
                        humanize_size(part.size),
                        int(100 * part.size / device.size))
                    menu = self._action_menu_for_device(
                        part, self._partition_action)
                    am = Color.menu_button(TableRow([
                        Text(label),
                        (2, Text(part_size)),
                        menu,
                    ]))
                    _wire_menu_to_row(menu, am)
                    rows.append(am)
                if self.show_available and 0 < device.used < device.size:
                    size = device.size
                    free = device.free
                    percent = str(int(100 * free / size))
                    if percent == "0":
                        percent = "%.2f" % (100 * free / size,)
                    size_text = "{:>9} ({}%)".format(
                        humanize_size(free), percent)
                    rows.append(TableRow([Text(_("  free space")), (2, Text(size_text))]))
        self.table.set_contents(rows)
        if self.table._w.focus_position >= len(rows):
            self.table._w.focus_position = len(rows) - 1


class FilesystemView(BaseView):
    title = _("Filesystem setup")
    footer = _("Select available disks to format and mount")

    def __init__(self, model, controller):
        log.debug('FileSystemView init start()')
        self.model = model
        self.controller = controller
        self.items = []
        self.mount_list = MountList(self)
        self.avail_list = DeviceList(self, True)
        self.used_list = DeviceList(self, False)
        self.avail_list.table.bind(self.used_list.table)
        body = [
            Text(_("FILE SYSTEM SUMMARY")),
            Text(""),
            self.mount_list,
            Text(""),
            Text(_("AVAILABLE DEVICES")),
            Text(""),
            self.avail_list,
            Text(""),
            Text(_("USED DEVICES")),
            Text(""),
            self.used_list,
            Text("")
            ]

        self.lb = Padding.center_95(ListBox(body))
        bottom = Pile([
                Text(""),
                self._build_buttons(),
                Text(""),
                ])
        self.frame = Pile([
            ('pack', Text("")),
            self.lb,
            ('pack', bottom)])
        if self.model.can_install():
            self.frame.focus_position = 2
        super().__init__(self.frame)
        log.debug('FileSystemView init complete()')

    def refresh_model_inputs(self):
        self.mount_list.refresh_model_inputs()
        self.avail_list.refresh_model_inputs()
        self.used_list.refresh_model_inputs()
        # If refreshing the view has left the focus widget with no
        # selectable widgets, simulate a tab to move to the next
        # selectable widget.
        while not self.lb.base_widget.focus.selectable():
            self.lb.base_widget.keypress((10, 10), 'tab')
        if self.model.can_install():
            self.done.enable()
        else:
            self.done.disable()

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        self.done = Toggleable(done_btn(_("Done"), on_press=self.done))
        if not self.model.can_install():
            self.done.disable()

        return button_pile([
            self.done,
            reset_btn(_("Reset"), on_press=self.reset),
            back_btn(_("Back"), on_press=self.cancel),
            ])

    def cancel(self, button=None):
        self.controller.default()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_stretchy_overlay(FilesystemConfirmation(self,
                                                          self.controller))
