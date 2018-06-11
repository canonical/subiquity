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
    CompositeCanvas,
    connect_signal,
    Text,
    WidgetDecoration,
    )

from subiquitycore.ui.actionmenu import (
    ActionMenu,
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
    Columns,
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import ColSpec, Table, TableRow
from subiquitycore.ui.utils import button_pile, Color, Padding
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size


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


class CursorOverride(WidgetDecoration):
    """Decoration to override where the cursor goes when a widget is focused.
    """

    def __init__(self, w, cursor_x=0):
        super().__init__(w)
        self.cursor_x = cursor_x

    def get_cursor_coords(self, size):
        return self.cursor_x, 0

    def rows(self, size, focus):
        return self._original_widget.rows(size, focus)

    def keypress(self, size, focus):
        return self._original_widget.keypress(size, focus)

    def render(self, size, focus=False):
        c = self._original_widget.render(size, focus)
        if focus:
            # create a new canvas so we can add a cursor
            c = CompositeCanvas(c)
            c.cursor = self.get_cursor_coords(size)
        return c


def add_menu_row_focus_behaviour(menu, row, attr_map, focus_map, cursor_x=0):
    """Configure focus behaviour of row (which contains menu)

    The desired behaviour is that:

    1) The cursor appears at the left of the row rather than where the
       menu is.
    2) The row is highlighted when focused and retains that focus even
       when the popup is open.
    """
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
        self.table = Table([], spacing=2, colspecs={
            0: ColSpec(can_shrink=True),
            1: ColSpec(min_width=9),
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
            self.table.set_contents([])
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
            row = TableRow([
                Text(path_markup),
                Text(mi.size, align='right'),
                Text(mi.fstype),
                Text(mi.desc),
                menu,
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
            ] + [Padding.push_4(p) for p in self._build_available_inputs()]

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

    def refresh_model_inputs(self):
        self.mount_list.refresh_model_inputs()

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
