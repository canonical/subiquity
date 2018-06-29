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

import attr

from urwid import (
    AttrMap,
    connect_signal,
    Text,
    )

from subiquitycore.ui.actionmenu import (
    Action,
    ActionMenu,
    ActionMenuButton,
    )
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    danger_btn,
    done_btn,
    menu_btn,
    reset_btn,
    )
from subiquitycore.ui.container import (
    ListBox,
    WidgetWrap,
    )
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    Color,
    CursorOverride,
    Padding,
    screen,
    )
from subiquitycore.view import BaseView

from subiquity.models.filesystem import DeviceAction, humanize_size

from .delete import can_delete, ConfirmDeleteStretchy
from .disk_info import DiskInfoStretchy
from .partition import PartitionStretchy, FormatEntireStretchy
from .raid import RaidStretchy

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


def add_menu_row_focus_behaviour(menu, row, attr_map, focus_map, cursor_x=2):
    """Configure focus behaviour of row (which contains menu)

    The desired behaviour is that:

    1) The cursor appears at the left of the row rather than where the
       menu is.
    2) The row is highlighted when focused and retains that focus even
       when the popup is open.
    """
    if not isinstance(attr_map, dict):
        attr_map = {None: attr_map}
    if not isinstance(focus_map, dict):
        focus_map = {None: focus_map}
    am = AttrMap(CursorOverride(row, cursor_x=cursor_x), attr_map, focus_map)
    connect_signal(menu, 'open', lambda menu: am.set_attr_map(focus_map))
    connect_signal(menu, 'close', lambda menu: am.set_attr_map(attr_map))
    return am


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

    def __init__(self, parent):
        self.parent = parent
        self.table = TablePile([], spacing=2, colspecs={
            0: ColSpec(rpad=1),
            1: ColSpec(can_shrink=True),
            2: ColSpec(min_width=9),
            4: ColSpec(rpad=1),
            5: ColSpec(rpad=1),
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
                self.parent.model.all_mounts(),
                key=lambda m: (m.path == "", m.path))
        ]
        if len(mountinfos) == 0:
            self.table.set_contents([])
            self._w = self._no_mounts_content
            return
        self._w = self.table
        log.debug('FileSystemView: building mount list')

        rows = [TableRow([
            Color.info_minor(heading) for heading in [
                Text(" "),
                Text(_("MOUNT POINT")),
                Text(_("SIZE"), align='center'),
                Text(_("TYPE")),
                Text(_("DEVICE TYPE")),
                Text(" "),
                Text(" "),
            ]])]

        for i, mi in enumerate(mountinfos):
            path_markup = mi.path
            if path_markup == "":
                path_markup = ('info_minor', "SWAP")
            else:
                for j in range(i-1, -1, -1):
                    mi2 = mountinfos[j]
                    if mi.startswith(mi2):
                        part1 = "/".join(mi.split_path[:len(mi2.split_path)])
                        part2 = "/".join(
                            [''] + mi.split_path[len(mi2.split_path):])
                        path_markup = [('info_minor', part1), part2]
                        break
                    if j == 0 and mi2.split_path == ['', '']:
                        path_markup = [
                            ('info_minor', "/"),
                            "/".join(mi.split_path[1:]),
                            ]
            actions = [(_("Unmount"), mi.mount.can_delete(), 'unmount')]
            menu = ActionMenu(
                actions, "\N{BLACK RIGHT-POINTING SMALL TRIANGLE}")
            connect_signal(menu, 'action', self._mount_action, mi.mount)
            row = TableRow([
                Text("["),
                Text(path_markup),
                Text(mi.size, align='right'),
                Text(mi.fstype),
                Text(mi.desc),
                menu,
                Text("]"),
            ])
            row = add_menu_row_focus_behaviour(
                menu,
                row,
                'menu_button',
                {None: 'menu_button focus', 'info_minor': 'menu_button focus'})
            rows.append(row)
        self.table.set_contents(rows)
        if self.table._w.focus_position >= len(rows):
            self.table._w.focus_position = len(rows) - 1


def _stretchy_shower(cls):
    def impl(self, device):
        self.parent.show_stretchy_overlay(cls(self.parent, device))
    return impl


class DeviceList(WidgetWrap):

    def __init__(self, parent, show_available):
        self.parent = parent
        self.show_available = show_available
        self.table = TablePile([],  spacing=2, colspecs={
            0: ColSpec(rpad=1),
            1: ColSpec(can_shrink=False),
            2: ColSpec(min_width=9),
            3: ColSpec(rpad=1),
            4: ColSpec(rpad=1),
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

    _disk_INFO = _stretchy_shower(DiskInfoStretchy)
    _disk_PARTITION = _stretchy_shower(PartitionStretchy)
    _disk_FORMAT = _stretchy_shower(FormatEntireStretchy)

    def _disk_MAKE_BOOT(self, disk):
        self.parent.controller.make_boot_disk(disk)
        self.parent.refresh_model_inputs()

    _partition_EDIT = _stretchy_shower(
        lambda parent, part: PartitionStretchy(parent, part.device, part))
    _partition_DELETE = _stretchy_shower(ConfirmDeleteStretchy)
    _partition_FORMAT = _disk_FORMAT

    _raid_EDIT = _stretchy_shower(RaidStretchy)
    _raid_PARTITION = _disk_PARTITION
    _raid_FORMAT = _disk_FORMAT
    _raid_DELETE = _partition_DELETE

    def _action(self, sender, action, device):
        log.debug('_action %s %s', action, device)
        meth_name = '_{}_{}'.format(device.type, action.name)
        getattr(self, meth_name)(device)

    def _action_menu_for_device(self, device):
        if can_delete(device)[0]:
            delete_btn = Color.danger_button(ActionMenuButton(_("Delete")))
        else:
            delete_btn = _("Delete *")
        device_actions = [
            (_("Information"),      DeviceAction.INFO),
            (_("Edit"),             DeviceAction.EDIT),
            (_("Add Partition"),    DeviceAction.PARTITION),
            (_("Format / Mount"),   DeviceAction.FORMAT),
            (delete_btn,            DeviceAction.DELETE),
            (_("Make boot device"), DeviceAction.MAKE_BOOT),
        ]
        actions = []
        for label, action in device_actions:
            actions.append(Action(
                label=label,
                enabled=device.supports_action(action),
                value=action,
                opens_dialog=action != DeviceAction.MAKE_BOOT))
        menu = ActionMenu(actions, "\N{BLACK RIGHT-POINTING SMALL TRIANGLE}")
        connect_signal(menu, 'action', self._action, device)
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

        rows.append(TableRow([Color.info_minor(heading) for heading in [
            Text(" "),
            Text(_("DEVICE")),
            Text(_("SIZE"), align="center"),
            Text(_("TYPE")),
            Text(" "),
            Text(" "),
        ]]))
        for device in devices:
            menu = self._action_menu_for_device(device)
            row = TableRow([
                Text("["),
                Text(device.label),
                Text("{:>9}".format(humanize_size(device.size))),
                Text(device.desc()),
                menu,
                Text("]"),
            ])
            row = add_menu_row_focus_behaviour(
                menu, row, 'menu_button', 'menu_button focus')
            rows.append(row)

            entire_label = None
            if device.fs():
                entire_label = _fmt_fs(
                    "    " + _("entire device formatted as"),
                    device.fs())
            elif device.constructed_device():
                entire_label = _fmt_constructed(
                    "    " + _("entire device"),
                    device.constructed_device())
            if entire_label is not None:
                rows.append(TableRow([
                    Text(""),
                    (3, Text(entire_label)),
                    Text(""),
                    Text(""),
                ]))
            else:
                for part in device.partitions():
                    if part.available() != self.show_available:
                        continue
                    prefix = _("partition {},").format(part._number)
                    if part.flag == "bios_grub":
                        label = prefix + " bios_grub"
                    elif part.fs():
                        label = _fmt_fs(prefix, part.fs())
                    elif part.constructed_device():
                        label = _fmt_constructed(
                            prefix, part.constructed_device())
                    else:
                        label = _("{} not formatted").format(prefix)
                    part_size = "{:>9} ({}%)".format(
                        humanize_size(part.size),
                        int(100 * part.size / device.size))
                    menu = self._action_menu_for_device(part)
                    row = TableRow([
                        Text("["),
                        Text("  " + label),
                        (2, Text(part_size)),
                        menu,
                        Text("]"),
                    ])
                    row = add_menu_row_focus_behaviour(
                        menu, row, 'menu_button', 'menu_button focus',
                        cursor_x=4)
                    rows.append(row)
                if (self.show_available
                        and device.used > 0
                        and device.free_for_partitions > 0):
                    size = device.size
                    free = device.free_for_partitions
                    percent = str(int(100 * free / size))
                    if percent == "0":
                        percent = "%.2f" % (100 * free / size,)
                    size_text = "{:>9} ({}%)".format(
                        humanize_size(free), percent)
                    rows.append(TableRow([
                        Text(""),
                        Text("  " + _("free space")),
                        (2, Text(size_text)),
                        Text(""),
                        Text(""),
                    ]))
        self.table.set_contents(rows)
        if self.table._w.focus_position >= len(rows):
            self.table._w.focus_position = len(rows) - 1
        while not self.table._w.focus.selectable():
            self.table._w.focus_position -= 1


class FilesystemView(BaseView):
    title = _("Filesystem setup")
    footer = _("Select available disks to format and mount")

    def __init__(self, model, controller):
        log.debug('FileSystemView init start()')
        self.model = model
        self.controller = controller

        self.mount_list = MountList(self)
        self.avail_list = DeviceList(self, True)
        self.used_list = DeviceList(self, False)
        self.avail_list.table.bind(self.used_list.table)
        self._create_raid_btn = menu_btn(
            label=_("Create software RAID (md)"),
            on_press=self.create_raid)

        bp = button_pile([self._create_raid_btn])
        bp.align = 'left'

        body = [
            Text(_("FILE SYSTEM SUMMARY")),
            Text(""),
            Padding.push_2(self.mount_list),
            Text(""),
            Text(""),
            Text(_("AVAILABLE DEVICES")),
            Text(""),
            Padding.push_2(self.avail_list),
            Text(""),
            Padding.push_2(bp),
            Text(""),
            Text(""),
            Text(_("USED DEVICES")),
            Text(""),
            Padding.push_2(self.used_list),
            Text(""),
            ]

        self.lb = ListBox(body)
        frame = screen(
            self.lb, self._build_buttons(),
            focus_buttons=self.model.can_install())
        frame.width = ('relative', 95)
        super().__init__(frame)
        log.debug('FileSystemView init complete()')

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        self.done = Toggleable(done_btn(_("Done"), on_press=self.done))
        if not self.model.can_install():
            self.done.disable()

        return [
            self.done,
            reset_btn(_("Reset"), on_press=self.reset),
            back_btn(_("Back"), on_press=self.cancel),
            ]

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

    def create_raid(self, button=None):
        self.show_stretchy_overlay(RaidStretchy(self))

    def cancel(self, button=None):
        self.controller.default()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_stretchy_overlay(FilesystemConfirmation(self,
                                                          self.controller))
