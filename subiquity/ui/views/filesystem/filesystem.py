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
from urwid import CheckBox, connect_signal, Text

from subiquitycore.ui.actionmenu import ActionMenu
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    danger_btn,
    done_btn,
    menu_btn,
    reset_btn,
    )
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile, Color, Padding
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size, Disk, Partition, Raid


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


class NarrowCheckBox(CheckBox):
    reserve_columns = 3

device_actions = [
    (_("Information"), 'info'),
    (_("Edit"), 'edit'),
    (_("Add Partition"), 'partition'),
    (_("Format / Mount"), 'format'),
    (_("Delete"), 'delete'),
    ]

class FilesystemView(BaseView):
    title = _("Filesystem setup")
    footer = _("Select available disks to format and mount")

    def __init__(self, model, controller):
        log.debug('FileSystemView init start()')
        self.model = model
        self.controller = controller
        self.items = []

        self.raid_btn = Toggleable(menu_btn(label=_("Create software RAID (MD)"), on_press=self._click_raid))
        self._buttons = [self.raid_btn]
        #self._disable(self.raid_btn)

        body = [
            Text(_("FILE SYSTEM SUMMARY")),
            Text(""),
            Padding.push_3(self._build_filesystem_list()),
            Text(""),
            Text(_("AVAILABLE DEVICES")),
            Text(""),
            ] + self._build_available_inputs() + [
            Text(""),
            Text(_("USED DEVICES")),
            Text(""),
            ] + self._build_used_inputs()

        #+ [
            #self._build_menu(),
            #Text(""),
            #Text("USED DISKS"),
            #Text(""),
            #self._build_used_disks(),
            #Text(""),
        #]

        self._selected_devices = set()

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

    def _build_used_disks(self):
        log.debug('FileSystemView: building used disks')
        return Color.info_minor(Text("No disks have been used to create a constructed disk."))

    def _build_filesystem_list(self):
        log.debug('FileSystemView: building part list')
        cols = []
        mount_point_text = _("MOUNT POINT")
        longest_path = len(mount_point_text)
        for m in sorted(self.model._mounts, key=lambda m:m.path):
            path = m.path
            longest_path = max(longest_path, len(path))
            for p, *dummy in reversed(cols):
                if path.startswith(p):
                    path = [('info_minor', p), path[len(p):]]
                    break
            cols.append((m.path, path, humanize_size(m.device.volume.size), m.device.fstype, m.device.volume.desc()))
        for fs in self.model._filesystems:
            if fs.fstype == 'swap':
                cols.append((None, _('SWAP'), humanize_size(fs.volume.size), fs.fstype, fs.volume.desc()))

        if len(cols) == 0:
            return Pile([Color.info_minor(
                Text(_("No disks or partitions mounted.")))])
        size_text = _("SIZE")
        type_text = _("TYPE")
        size_width = max(len(size_text), 9)
        type_width = max(len(type_text), self.model.longest_fs_name)
        cols.insert(0, (None, mount_point_text, size_text, type_text, _("DEVICE TYPE")))
        pl = []
        for dummy, a, b, c, d in cols:
            if b == "SIZE":
                b = Text(b, align='center')
            else:
                b = Text(b, align='right')
            pl.append(Columns([(longest_path, Text(a)), (size_width, b), (type_width, Text(c)), Text(d)], 4))
        return Pile(pl)

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        buttons = []

        # don't enable done botton if we can't install
        # XXX should enable/disable button rather than having it appear/disappear I think
        if self.model.can_install():
            buttons.append(
                done_btn(_("Done"), on_press=self.done))

        buttons.append(reset_btn(_("Reset"), on_press=self.reset))
        buttons.append(back_btn(_("Back"), on_press=self.cancel))

        return button_pile(buttons)

    def _enable(self, btn):
        btn.enable()
        btn._original_widget.set_attr_map({None: 'menu'})

    def _disable(self, btn):
        btn.disable()
        btn._original_widget._original_widget.set_attr_map({None: 'info_minor'})

    def _action(self, sender, action, obj):
        log.debug("_action %r %r", action, obj)
        if isinstance(obj, Disk):
            if action == 'info':
                from .disk_info import DiskInfoStretchy
                self.show_stretchy_overlay(DiskInfoStretchy(self, obj))
            elif action == 'partition':
                from .partition import PartitionStretchy
                self.show_stretchy_overlay(PartitionStretchy(self, obj))
            elif action == 'format':
                pass
        elif isinstance(obj, Partition):
            if action == 'edit':
                from .partition import PartitionStretchy
                self.show_stretchy_overlay(PartitionStretchy(self, obj.device, obj))
            elif action == 'delete':
                pass
        elif isinstance(obj, Raid):
            if action == 'edit':
                from ..raid import RaidStretchy
                self.show_stretchy_overlay(RaidStretchy(self, obj))

    def _build_device_rows(self, dev, available):
        label = Text(dev.label)
        size = Text(humanize_size(dev.size).rjust(9))
        typ = Text(dev.desc())
        action_menu = ActionMenu([(_(label), dev.supports_action(action), action) for label, action in device_actions])
        connect_signal(action_menu, 'action', self._action, dev)
        r = [Columns([
            (3, action_menu),
            (42, label),
            (10, size),
            typ,
            ], 1)]
        if dev.fs() is not None or dev.raid() is not None:
            label = _("entire device")
            fs = dev.fs()
            if fs is not None:
                label += _(", formatted as: {}").format(fs.fstype)
                m = fs.mount()
                if m:
                    if available:
                        return []
                    label += _(", mounted at: {}").format(m.path)
                else:
                    label += _(", not mounted")
            if dev.raid() is not None:
                if available:
                    return []
                label += _(" is part of {} ({})").format(dev.raid().name, dev.raid().desc())
            r.append(Columns([
                (3, Text("")),
                Text(label),
                ], 1))
            return r
        has_unavailable_partition = False
        for partition in dev.partitions():
            if not partition.available:
                has_unavailable_partition = True
            if available != partition.available:
                continue
            part_label = _("  partition {}, ").format(partition._number)
            fs = partition.fs()
            if fs is not None:
                if fs.mount():
                    part_label += "%-*s"%(self.model.longest_fs_name+2, fs.fstype+',') + fs.mount().path
                else:
                    part_label += fs.fstype
            elif partition.raid() is not None:
                part_label += _("part of {}").format(partition.raid().name)
            elif partition.flag == "bios_grub":
                part_label += "bios_grub"
            else:
                part_label += _("unformatted")
            part_label = Text(part_label)
            part_size = Text("{:>9} ({}%)".format(humanize_size(partition.size), int(100*partition.size/dev.size)))
            action_menu = ActionMenu([(_(label), partition.supports_action(action), action) for label, action in device_actions])
            connect_signal(action_menu, 'action', self._action, partition)
            r.append(Columns([
                (3, action_menu),
                (42, part_label),
                part_size,
                ], 1))
        if not available and not has_unavailable_partition:
            return []
        if available and 0 < dev.used < dev.size:
            size = dev.size
            free = dev.free
            percent = str(int(100*free/size))
            if percent == "0":
                percent = "%.2f"%(100*free/size,)
            r.append(Columns([
                (3, Text("")),
                (42, Text(_("  free space"))),
                Text("{:>9} ({}%)".format(humanize_size(free), percent)),
                ], 1))
        return r

    def _build_available_inputs(self):
        r = []

        def col3(col1, col2, col3):
            col0 = Text("")
            inputs.append(Columns([(3, col0), (42, col1), (10, col2), col3], 1))
        def col2(col1, col2):
            inputs.append(Columns([(42, col1), col2], 1))
        def col1(col1):
            inputs.append(Columns([(42, col1)], 1))

        inputs = []
        col3(Text(_("DEVICE")), Text(_("SIZE"), align="center"), Text(_("TYPE")))
        r.append(Pile(inputs))

        for disk in self.model.all_devices():
            if disk.size < self.model.lower_size_limit:
                disk_label = Text(disk.label)
                size = Text(humanize_size(disk.size).rjust(9))
                typ = Text(disk.desc())
                col3(disk_label, size, typ)
                r.append(Color.info_minor(Pile(inputs)))
                continue
            r.extend(self._build_device_rows(disk, True))

        if len(r) == 1:
            return [Color.info_minor(Text(_("No disks available.")))]

        r.append(Text(""))

        bp = button_pile(self._buttons)
        bp.align = 'left'
        r.append(bp)

        return r
 
    def _build_used_inputs(self):
        r = []

        def col3(col1, col2, col3):
            col0 = Text("")
            inputs.append(Columns([(3, col0), (42, col1), (10, col2), col3], 1))
        def col2(col1, col2):
            inputs.append(Columns([(42, col1), col2], 1))
        def col1(col1):
            inputs.append(Columns([(42, col1)], 1))

        inputs = []
        col3(Text(_("DEVICE")), Text(_("SIZE"), align="center"), Text(_("TYPE")))
        r.append(Pile(inputs))

        for disk in self.model.all_devices():
            if disk.size < self.model.lower_size_limit:
                disk_label = Text(disk.label)
                size = Text(humanize_size(disk.size).rjust(9))
                typ = Text(disk.desc())
                col3(disk_label, size, typ)
                r.append(Color.info_minor(Pile(inputs)))
                continue
            r.extend(self._build_device_rows(disk, False))

        if len(r) == 1:
            return [Color.info_minor(Text(_("No disks used yet.")))]

        r.append(Text(""))

        return r

    def _click_raid(self, sender):
        from ..raid import RaidStretchy
        self.show_stretchy_overlay(RaidStretchy(self, []))

    def _build_menu(self):
        log.debug('FileSystemView: building menu')
        opts = []
        #avail_disks = self.model.get_available_disk_names()

        fs_menu = [
            # ('Connect iSCSI network disk',         'filesystem:connect-iscsi-disk'),
            # ('Connect Ceph network disk',          'filesystem:connect-ceph-disk'),
            # ('Create volume group (LVM2)',           'menu:filesystem:main:create-volume-group'),
            # ('Create software RAID (MD)',            'menu:filesystem:main:create-raid'),
            # ('Setup hierarchichal storage (bcache)', 'menu:filesystem:main:setup-bcache'),
        ]

        for opt, sig in fs_menu:
            if len(avail_disks) > 1:
                opts.append(menu_btn(label=opt,
                                     on_press=self.on_fs_menu_press,
                                     user_data=sig))
        return Pile(opts)

    def cancel(self, button=None):
        self.controller.default()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_stretchy_overlay(FilesystemConfirmation(self, self.controller))
