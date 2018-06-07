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
    menu_btn,
    reset_btn,
    )
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile, Color, Padding
from subiquitycore.view import BaseView

from subiquity.models.filesystem import DeviceAction, humanize_size


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

    def _select_first_selectable(self):
        self._w._select_first_selectable()

    def _select_last_selectable(self):
        self._w._select_last_selectable()

    def __init__(self, parent):
        self.parent = parent
        self.pile = Pile([])
        self._no_mounts_content = (
            Color.info_minor(Text(_("No disks or partitions mounted."))),
            self.pile.options('pack'))
        super().__init__(self.pile)
        self.refresh_model_inputs()

    def _mount_action(self, sender, action, mount):
        log.debug('_mount_action %s %s', action, mount)
        if action == 'unmount':
            self.parent.controller.delete_mount(mount)
            self.parent.refresh_model_inputs()

    def refresh_model_inputs(self):
        mountinfos = [
            MountInfo(mount=m)
            for m in sorted(self.parent.model._mounts, key=lambda m: m.path)
        ]
        if len(mountinfos) == 0:
            self.pile.contents[:] = [self._no_mounts_content]
            return
        log.debug('FileSystemView: building mount list')
        mount_point_text = _("MOUNT POINT")
        device_type_text = _("DEVICE TYPE")
        longest_path = max(
            [len(mount_point_text)] +
            [len(m.mount.path) for m in mountinfos])
        longest_type = max(
            [len(device_type_text)] +
            [len(m.desc) for m in mountinfos])
        cols = []

        def col(action_menu, path, size, fstype, desc):
            c = Columns([
                (3,            action_menu),
                (longest_path, Text(path)),
                (size_width,   size),
                (type_width,   Text(fstype)),
                (longest_type, Text(desc)),
                Color.body(Text("")),
            ], dividechars=1)
            if isinstance(action_menu, ActionMenu):
                c = AttrMap(
                    c,
                    {None: 'menu_button', 'grey': 'info_minor'},
                    {None: 'menu_button focus', 'grey': 'menu_button focus'})
            cols.append((c, self.pile.options('pack')))

        size_text = _("SIZE")
        type_text = _("TYPE")
        size_width = max(len(size_text), 9)
        type_width = max(len(type_text), self.parent.model.longest_fs_name)
        col(
            Text(""),
            mount_point_text,
            Text(size_text, align='center'),
            type_text,
            device_type_text)

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
            col(
                menu,
                path_markup,
                Text(mi.size, align='right'),
                mi.fstype,
                mi.desc)
        self.pile.contents[:] = cols
        if self.pile.focus_position >= len(cols):
            self.pile.focus_position = len(cols) - 1


class DeviceList(WidgetWrap):

    def _select_first_selectable(self):
        self._w._select_first_selectable()

    def _select_last_selectable(self):
        self._w._select_last_selectable()

    def __init__(self, parent, show_available):
        self.parent = parent
        self.show_available = show_available
        self.pile = Pile([])
        if show_available:
            text = _("No available devices")
        else:
            text = _("No used devices")
        self._no_devices_content = (
            Color.info_minor(Text(text)),
            self.pile.options('pack'))
        super().__init__(self.pile)
        self.refresh_model_inputs()

    def _device_action(self, sender, action, device):
        log.debug('_device_action %s %s', action, device)

    def _action_menu_for_device(self, device):
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
        connect_signal(menu, 'action', self._device_action, device)
        return menu

    def refresh_model_inputs(self):
        devices = [
            d for d in self.parent.model.all_devices()
            if (d.available() == self.show_available
                or (not self.show_available and d.has_unavailable_partition()))
        ]
        if len(devices) == 0:
            self.pile.contents[:] = [self._no_devices_content]
            return
        log.debug('FileSystemView: building device list')
        rows = []
        def row3(menu, device, size, typ):
            rows.append([menu, device, size, typ])

        def row2(menu, label, size):
            rows.append([menu, label, size, Text("")])

        def row1(label):
            rows.append([Text(""), label])

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

        def _maybe_fmt_entire(label, device):
            if device.fs():
                return _fmt_fs(label, device.fs())
            elif device.constructed_device():
                return _fmt_constructed(
                    label, device.constructed_device())
            else:
                return None

        row3(Text(""), Text(_("DEVICE")), Text(_("SIZE"), align="center"),
             Text(_("TYPE")))
        for device in devices:
            row3(
                self._action_menu_for_device(device),
                Text(device.label),
                Text(humanize_size(device.size)),
                Text(device.desc()))
            entire_label = _maybe_fmt_entire(_("  entire device"), device)
            if entire_label is not None:
                row1(Text(entire_label))
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
                        label = _("{}, not formatted").format(prefix)
                    part_size = "{:>9} ({}%)".format(
                        humanize_size(part.size),
                        int(100 * part.size / device.size))
                    row2(
                        self._action_menu_for_device(part),
                        Text(label),
                        Text(part_size),
                        )
                if self.show_available and 0 < device.used < device.size:
                    size = device.size
                    free = device.free
                    percent = str(int(100 * free / size))
                    if percent == "0":
                        percent = "%.2f" % (100 * free / size,)
                    row2([
                        Text(""),
                        Text(_("free space")),
                        Text("{:>9} ({}%)".format(humanize_size(free), percent)),
                    ])
        widths = defaultdict(int)
        widths[0] = 3
        for row in rows:
            log.debug("%s", row)
            if len(row) == 4:
                for i in 1, 2, 3:
                    widths[i] = max(widths[i], len(row[i].text))
        cols = []
        for row in rows:
            if len(row) == 4:
                ws = [(widths[i], w) for i, w in enumerate(row)]
                ws.append(Color.body(Text("")))
                c = Columns(ws, 1)
                if c.selectable():
                    c = Color.menu_button(c)
                cols.append((c, self.pile.options('pack')))
            elif len(row) == 2:
                c = Columns([(widths[0], row[0]), row[1]], 1)
                if c.selectable():
                    raise Exception("unexpectedly selectable row")
                cols.append((c, self.pile.options('pack')))
            else:
                raise Exception("unexpected row length {}".format(row))
        self.pile.contents[:] = cols
        if self.pile.focus_position >= len(cols):
            self.pile.focus_position = len(cols) - 1


class FilesystemView(BaseView):
    title = _("Filesystem setup")
    footer = _("Select available disks to format and mount")

    def __init__(self, model, controller):
        log.debug('FileSystemView init start()')
        self.model = model
        self.controller = controller
        self.items = []
        self.mount_list = MountList(self)
        body = [
            Text(_("FILE SYSTEM SUMMARY")),
            Text(""),
            self.mount_list,
            Text(""),
            Text(_("AVAILABLE DEVICES")),
            Text(""),
            DeviceList(self, True),
            Text(""),
            Text(_("USED DEVICES")),
            Text(""),
            DeviceList(self, False),
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
        # If refreshing the view has left the focus widget with no
        # selectable widgets, simulate a tab to move to the next
        # selectable widget.
        if not self.lb.base_widget.focus.selectable():
            self.lb.base_widget.keypress((10, 10), 'tab')

    def _build_used_disks(self):
        log.debug('FileSystemView: building used disks')
        return Color.info_minor(
            Text("No disks have been used to create a constructed disk."))

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        buttons = []

        # don't enable done botton if we can't install
        # XXX should enable/disable button rather than having it
        # appear/disappear I think
        if self.model.can_install():
            buttons.append(
                done_btn(_("Done"), on_press=self.done))

        buttons.append(reset_btn(_("Reset"), on_press=self.reset))
        buttons.append(back_btn(_("Back"), on_press=self.cancel))

        return button_pile(buttons)

    def _build_available_inputs(self):
        r = []

        def col3(col1, col2, col3):
            inputs.append(Columns([(42, col1), (10, col2), col3], 2))

        def col2(col1, col2):
            inputs.append(Columns([(42, col1), col2], 2))

        def col1(col1):
            inputs.append(Columns([(42, col1)], 1))

        inputs = []
        col3(Text(_("DEVICE")), Text(_("SIZE"), align="center"),
             Text(_("TYPE")))
        r.append(Pile(inputs))

        for disk in self.model.all_disks():
            inputs = []
            disk_label = Text(disk.label)
            size = Text(humanize_size(disk.size).rjust(9))
            typ = Text(disk.desc())
            col3(disk_label, size, typ)
            if disk.size < self.model.lower_size_limit:
                r.append(Color.info_minor(Pile(inputs)))
                continue
            fs = disk.fs()
            if fs is not None:
                label = _("entire device, ")
                fs_obj = self.model.fs_by_name[fs.fstype]
                if fs.mount():
                    label += "%-*s" % (self.model.longest_fs_name+2,
                                       fs.fstype+',') + fs.mount().path
                else:
                    label += fs.fstype
                if fs_obj.label and fs_obj.is_mounted and not fs.mount():
                    disk_btn = menu_btn(label=label, on_press=self.click_disk,
                                        user_arg=disk)
                    disk_btn = disk_btn
                else:
                    disk_btn = Color.info_minor(Text("  " + label))
                col1(disk_btn)
            for partition in disk.partitions():
                label = _("partition {}, ").format(partition._number)
                fs = partition.fs()
                if fs is not None:
                    if fs.mount():
                        label += "%-*s" % (self.model.longest_fs_name+2,
                                           fs.fstype+',') + fs.mount().path
                    else:
                        label += fs.fstype
                elif partition.flag == "bios_grub":
                    label += "bios_grub"
                else:
                    label += _("unformatted")
                size = Text("{:>9} ({}%)".format(
                            humanize_size(partition.size),
                            int(100 * partition.size/disk.size)))
                if partition.available:
                    part_btn = menu_btn(label=label,
                                        on_press=self.click_partition,
                                        user_arg=partition)
                    col2(part_btn, size)
                else:
                    part_btn = Color.info_minor(Text("  " + label))
                    size = Color.info_minor(size)
                    col2(part_btn, size)
            size = disk.size
            free = disk.free
            percent = str(int(100*free/size))
            if percent == "0":
                percent = "%.2f" % (100 * free / size,)
            if disk.available and disk.used > 0:
                label = _("Add/Edit Partitions")
                size = "{:>9} ({}%) free".format(humanize_size(free), percent)
            elif disk.available and disk.used == 0:
                label = _("Add First Partition")
                size = ""
            else:
                label = _("Edit Partitions")
                size = ""
            col2(menu_btn(label=label, on_press=self.click_disk,
                          user_arg=disk), Text(size))
            r.append(Pile(inputs))

        if len(r) == 1:
            return [Color.info_minor(Text(_("No disks available.")))]

        return r

    def click_disk(self, sender, disk):
        self.controller.partition_disk(disk)

    def click_partition(self, sender, partition):
        self.controller.format_mount_partition(partition)

    def cancel(self, button=None):
        self.controller.default()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_stretchy_overlay(FilesystemConfirmation(self,
                                                          self.controller))
