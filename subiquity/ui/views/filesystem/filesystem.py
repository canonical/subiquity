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
    connect_signal,
    Text,
    )

from subiquitycore.ui.actionmenu import (
    Action,
    ActionMenu,
    ActionMenuOpenButton,
    )
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    danger_btn,
    done_btn,
    menu_btn,
    other_btn,
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
    make_action_menu_row,
    Padding,
    screen,
    )
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    DeviceAction,
    humanize_size,
    )

from .delete import ConfirmDeleteStretchy
from .disk_info import DiskInfoStretchy
from .lvm import VolGroupStretchy
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
                path_markup = "SWAP"
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
            menu = ActionMenu(actions)
            connect_signal(menu, 'action', self._mount_action, mi.mount)
            cells = [
                Text("["),
                Text(path_markup),
                Text(mi.size, align='right'),
                Text(mi.fstype),
                Text(mi.desc),
                menu,
                Text("]"),
            ]
            row = make_action_menu_row(
                cells,
                menu,
                attr_map='menu_button',
                focus_map={
                    None: 'menu_button focus',
                    'info_minor': 'menu_button focus',
                })
            rows.append(row)
        self.table.set_contents(rows)
        if self.table._w.focus_position >= len(rows):
            self.table._w.focus_position = len(rows) - 1


def _stretchy_shower(cls):
    def impl(self, device):
        self.parent.show_stretchy_overlay(cls(self.parent, device))
    impl.opens_dialog = True
    return impl


class WhyNotStretchy(Stretchy):

    def __init__(self, parent, obj, action, whynot):
        self.parent = parent
        self.obj = obj

        title = "Cannot {action} {type}".format(
            action=_(action.value).lower(),
            type=obj.desc())
        widgets = [
            Text(whynot),
            Text(""),
            button_pile([
                other_btn(label=_("Close"), on_press=self.close),
                ]),
        ]
        super().__init__(title, widgets, 0, 2)

    def close(self, sender=None):
        self.parent.remove_overlay()


def _whynot_shower(view, action, whynot):
    def impl(obj):
        view.show_stretchy_overlay(WhyNotStretchy(view, obj, action, whynot))
    impl.opens_dialog = True
    return impl


class DeviceList(WidgetWrap):

    def __init__(self, parent, show_available):
        self.parent = parent
        self.show_available = show_available
        self.table = TablePile([],  spacing=2, colspecs={
            0: ColSpec(rpad=1),
            2: ColSpec(can_shrink=True),
            4: ColSpec(min_width=9),
            5: ColSpec(rpad=1),
        })
        if show_available:
            text = _("No available devices")
        else:
            text = _("No used devices")
        self._no_devices_content = Color.info_minor(Text(text))
        super().__init__(self.table)

    _disk_INFO = _stretchy_shower(DiskInfoStretchy)
    _disk_PARTITION = _stretchy_shower(PartitionStretchy)
    _disk_FORMAT = _stretchy_shower(FormatEntireStretchy)

    def _disk_REMOVE(self, disk):
        cd = disk.constructed_device(skip_dm_crypt=False)
        if cd.type == "dm_crypt":
            self.parent.model.remove_dm_crypt(cd)
            disk, cd = cd, cd.constructed_device()
        if cd.type == "raid":
            if disk in cd.devices:
                cd.devices.remove(disk)
            else:
                cd.spare_devices.remove(disk)
        elif cd.type == "lvm_volgroup":
            cd.devices.remove(disk)
        else:
            1/0
        disk._constructed_device = None
        self.parent.refresh_model_inputs()

    def _disk_MAKE_BOOT(self, disk):
        self.parent.controller.make_boot_disk(disk)
        self.parent.refresh_model_inputs()

    _partition_EDIT = _stretchy_shower(
        lambda parent, part: PartitionStretchy(parent, part.device, part))
    _partition_REMOVE = _disk_REMOVE
    _partition_DELETE = _stretchy_shower(ConfirmDeleteStretchy)

    _raid_EDIT = _stretchy_shower(RaidStretchy)
    _raid_PARTITION = _disk_PARTITION
    _raid_FORMAT = _disk_FORMAT
    _raid_REMOVE = _disk_REMOVE
    _raid_DELETE = _partition_DELETE

    _lvm_volgroup_EDIT = _stretchy_shower(VolGroupStretchy)
    _lvm_volgroup_CREATE_LV = _disk_PARTITION
    _lvm_volgroup_DELETE = _partition_DELETE

    _lvm_partition_EDIT = _stretchy_shower(
        lambda parent, part: PartitionStretchy(parent, part.volgroup, part))
    _lvm_partition_DELETE = _partition_DELETE

    def _action(self, sender, value, device):
        action, meth = value
        log.debug('_action %s %s', action, device.id)
        meth(device)

    def _action_menu_for_device(self, device):
        device_actions = []
        for action in device.supported_actions:
            label = _(action.value)
            if action == DeviceAction.REMOVE and device.constructed_device():
                cd = device.constructed_device()
                label = _("Remove from {}").format(cd.desc())
            enabled, whynot = device.action_possible(action)
            if whynot:
                assert not enabled
                enabled = True
                label += " *"
                meth = _whynot_shower(self.parent, action, whynot)
            else:
                meth_name = '_{}_{}'.format(device.type, action.name)
                meth = getattr(self, meth_name)
            if not whynot and action == DeviceAction.DELETE:
                label = Color.danger_button(ActionMenuOpenButton(label))
            device_actions.append(Action(
                label=label,
                enabled=enabled,
                value=(action, meth),
                opens_dialog=getattr(meth, 'opens_dialog', False)))
        menu = ActionMenu(device_actions)
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

        rows.append(Color.info_minor(TableRow([
            Text(" "),
            (2, Text(_("DEVICE"))),
            Text(_("TYPE")),
            Text(_("SIZE"), align="center"),
            Text(" "),
            Text(" "),
        ])))
        for device in devices:
            menu = self._action_menu_for_device(device)
            label = device.label
            if device.annotations:
                label = "{} ({})".format(label, ", ".join(device.annotations))
            cells = [
                Text("["),
                (2, Text(label)),
                Text(device.desc()),
                Text("{:>9}".format(humanize_size(device.size))),
                menu,
                Text("]"),
            ]
            row = make_action_menu_row(cells, menu)
            rows.append(row)

            if not device.partitions():
                rows.append(TableRow([
                    Text(""),
                    (3, Color.info_minor(
                        Text(", ".join(device.usage_labels())))),
                    Text(""),
                    Text(""),
                ]))
            else:
                for part in device.partitions():
                    if part.available() != self.show_available:
                        continue
                    menu = self._action_menu_for_device(part)
                    details = ", ".join(part.annotations + part.usage_labels())
                    cells = [
                        Text(""),
                        Text(part.short_label),
                        (2, Text(details)),
                        Text(humanize_size(part.size), align="right"),
                        menu,
                        Text(""),
                    ]
                    row = make_action_menu_row(cells, menu, cursor_x=2)
                    rows.append(row)
                if (self.show_available
                        and device.used > 0
                        and device.free_for_partitions > 0):
                    free = device.free_for_partitions
                    rows.append(TableRow([
                        Text(""),
                        (3, Color.info_minor(Text(_("free space")))),
                        Text(humanize_size(free), align="right"),
                        Text(""),
                        Text(""),
                    ]))
            rows.append(TableRow([Text("")]))
        self.table.set_contents(rows[:-1])
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
        self._create_raid_btn = Toggleable(menu_btn(
            label=_("Create software RAID (md)"),
            on_press=self.create_raid))
        self._create_vg_btn = Toggleable(menu_btn(
            label=_("Create volume group (LVM)"),
            on_press=self.create_vg))

        bp = button_pile([self._create_raid_btn, self._create_vg_btn])
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
        self.lb.base_widget.offset_rows = 2
        frame = screen(
            self.lb, self._build_buttons(),
            focus_buttons=self.model.can_install())
        super().__init__(frame)
        self.refresh_model_inputs()
        log.debug('FileSystemView init complete()')

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        self.done = Toggleable(done_btn(_("Done"), on_press=self.done))

        return [
            self.done,
            reset_btn(_("Reset"), on_press=self.reset),
            back_btn(_("Back"), on_press=self.cancel),
            ]

    def refresh_model_inputs(self):
        lvm_devices = set()
        raid_devices = set()
        for d in self.model.all_devices():
            if d.ok_for_raid:
                raid_devices.add(d)
            if d.ok_for_lvm_vg:
                lvm_devices.add(d)
            for p in d.partitions():
                if p.ok_for_raid:
                    raid_devices.add(p)
                if p.ok_for_lvm_vg:
                    lvm_devices.add(p)
            self._create_raid_btn.enabled = len(raid_devices) > 1
            self._create_vg_btn.enabled = len(lvm_devices) > 0
        self.mount_list.refresh_model_inputs()
        self.avail_list.refresh_model_inputs()
        self.used_list.refresh_model_inputs()
        # This is an awful hack, actual thinking required:
        self.lb.base_widget._select_first_selectable()
        can_install = self.model.can_install()
        self.done.enabled = can_install
        if can_install:
            self.controller.ui.set_footer(
                _("Select Done to begin the installation."))
        else:
            if self.model.needs_bootloader_partition():
                self.controller.ui.set_footer(self.footer)
            elif not self.model.is_root_mounted():
                self.controller.ui.set_footer(
                    _("You need to mount a device at / to continue."))

    def create_raid(self, button=None):
        self.show_stretchy_overlay(RaidStretchy(self))

    def create_vg(self, button=None):
        self.show_stretchy_overlay(VolGroupStretchy(self))

    def cancel(self, button=None):
        self.controller.default()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_stretchy_overlay(FilesystemConfirmation(self,
                                                          self.controller))
