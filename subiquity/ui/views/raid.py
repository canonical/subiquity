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
    CheckBox,
    connect_signal,
    Padding as UrwidPadding,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import (
    cancel_btn,
    menu_btn,
    ok_btn,
    )
from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    simple_field,
    StringField,
    WantsToKnowFormField,
    )
from subiquitycore.ui.selector import (
    Option,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )
from subiquitycore.ui.utils import (
    button_pile,
    Color,
    )

from .filesystem.partition import FSTypeField
from ..mount import MountField
from subiquity.models.filesystem import (
    get_raid_size,
    humanize_size,
    )

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

class BlockDevicePicker(Stretchy):

    def __init__(self, chooser, parent, devices):
        self.parent = parent
        self.chooser = chooser
        self.devices = devices
        device_widgets = []
        max_label_width = max([40] + [len(device.label) for device, checked in devices])
        for device, checked in devices:
            disk_sz = humanize_size(device.size)
            disk_string = "{:{}} {}".format(device.label, max_label_width, disk_sz)
            device_widgets.append(CheckBox(disk_string, state=checked))
            if device.fs() is not None:
                fs = device.fs()
                text = _("    formatted as: {}").format(fs.fstype)
                if fs.mount():
                    text += _(", mounted at: {}").format(fs.mount().path)
                device_widgets.append(Color.info_minor(Text(text)))
        self.pile = Pile(device_widgets)
        widgets = [
            self.pile,
            Text(""),
            button_pile([
                ok_btn(label=_("OK"), on_press=self.ok),
                cancel_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
            ]
        super().__init__(
            _("Select block devices"),
            widgets,
            stretchy_index=0,
            focus_index=0)


    def ok(self, sender):
        selected_devs = []
        for i in range(len(self.devices)):
            dev, was_checked = self.devices[i]
            w, o = self.pile.contents[i]
            if isinstance(w, CheckBox) and w.state:
                selected_devs.append(dev)
        self.chooser._emit('select', selected_devs)
        self.chooser.value = selected_devs
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()


class MultiDeviceChooser(WidgetWrap, WantsToKnowFormField):
    signals = ['select']
    def __init__(self):
        self.button = menu_btn(label="", on_press=self.click)
        self.button_padding = UrwidPadding(self.button, width=4)
        self.pile = Pile([self.button])
        self.value = []
        super().__init__(self.pile)
    @property
    def value(self):
        return self.devices
    @value.setter
    def value(self, value):
        self.devices = value
        w = []
        for dev in self.devices:
            w.append((Text(dev.label), self.pile.options('pack')))
        if len(w) > 0:
            label = _("Edit")
        else:
            label = _("Select")
        self.button.base_widget.set_label(label)
        self.button_padding.width = len(label) + 4
        b = Color.body(self.button_padding)
        w.append((b, self.pile.options('pack')))
        self.pile.contents[:] = w
        self.pile.focus_item = b
    def set_bound_form_field(self, bff):
        super().set_bound_form_field(bff)
        connect_signal(bff, 'enable', self.enable)
        connect_signal(bff, 'disable', self.disable)
    def enable(self, sender):
        self.button.set_attr_map({None:'menu'})
    def disable(self, sender):
        self.button.set_attr_map({None:'info_minor'})
    def click(self, sender):
        devs = []
        for device in self.bff.form.all_devices:
            devs.append((device, device in self.devices))
        self.bff.view.parent.show_stretchy_overlay(BlockDevicePicker(self, self.bff.view.parent, devs), 70)


MultiDeviceField = simple_field(MultiDeviceChooser)

class RaidForm(Form):

    def __init__(self, mountpoint_to_devpath_mapping, all_devices, view, initial={}):
        self.mountpoint_to_devpath_mapping = mountpoint_to_devpath_mapping
        self.all_devices = all_devices
        super().__init__(initial)
        self.devices.view = view
        connect_signal(self.fstype.widget, 'select', self.select_fstype)
        self.select_fstype(None, self.fstype.widget.value)

    devices = MultiDeviceField(_("Devices:"))
    name = StringField(_("Name:"))
    level = ChoiceField(_("RAID Level:"), choices=["dummy"])
    size = StringField(_("Size:"))

    def select_fstype(self, sender, fs):
        self.mount.enabled = fs.is_mounted

    fstype = FSTypeField(_("Format:"))
    mount = MountField(_("Mount:"))

    def clean_mount(self, val):
        if self.fstype.value.is_mounted:
            return val
        else:
            return None

    def validate_devices(self):
        if len(self.devices.value) < 2:
            return _("At least two devices must be selected")

    def validate_mount(self):
        mount = self.mount.value
        if mount is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mount) > 4095:
            return _('Path exceeds PATH_MAX')
        dev = self.mountpoint_to_devpath_mapping.get(mount)
        if dev is not None:
            return _("%s is already mounted at %s")%(dev, mount)


class RaidStretchy(Stretchy):
    def __init__(self, parent, devices):
        self.parent = parent
        mountpoint_to_devpath_mapping = self.parent.model.get_mountpoint_to_devpath_mapping()
        if isinstance(devices, list):
            title = _('Create software RAID ("MD") disk')
            self.existing = None
            initial = {
                'devices': devices,
                'name': 'dm-0',
                }
            i = 0
        else:
            title = _('Edit software RAID disk "{}"').format(devices.name)
            self.existing = devices
            raid = devices
            f = raid.fs()
            if f is None:
                m = None
            else:
                fs = parent.model.fs_by_name[f.fstype]
                m = f.mount()
                if m:
                    m = m.path
                    if m in mountpoint_to_devpath_mapping:
                        del mountpoint_to_devpath_mapping[m]
            initial = {
                'devices': raid.devices,
                'fstype': fs,
                'mount': m,
                'name': raid.name,
                }
            i = [i for i, l in enumerate(levels) if l.value == raid.raidlevel][0]

        all_devices = list(initial['devices'])
        for dev in self.parent.model.all_devices():
            if dev.ok_for_raid:
                all_devices.append(dev)
            else:
                for p in dev.partitions():
                    if p.ok_for_raid:
                        all_devices.append(p)

        self.form = RaidForm(mountpoint_to_devpath_mapping, all_devices, self, initial)

        connect_signal(self.form.level.widget, 'select', self._select_level)
        connect_signal(self.form.devices.widget, 'select', self._select_devices)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        opts = []
        for level in levels:
            enabled = len(self.form.devices.value) >= level.min_devices
            opts.append(Option((_(level.name), enabled, level)))
        self.form.level.widget._options = opts
        self.form.level.widget.index = i

        self.form.size.enabled = False

        super().__init__(title, [Pile(self.form.as_rows()), Text(""), self.form.buttons], 0, 0)

    def _select_level(self, sender, new_level):
        self.form.size.value = humanize_size(get_raid_size(new_level.value, self.form.devices.value))

    def _select_devices(self, sender, new_devices):
        self.form.size.value = humanize_size(get_raid_size(self.form.level.value.value, new_devices))
        opts = []
        for level in levels:
            enabled = len(new_devices) >= level.min_devices
            opts.append(Option((_(level.name), enabled, level)))
        self.form.level.widget._options = opts

    def done(self, sender):
        result = self.form.as_data()
        log.debug('raid_done: result = {}'.format(result))
        if self.existing:
            self.existing.raidlevel = result['level'].value
            self.parent.controller.manual()
        else:
            self.parent.controller.add_raid(result)

    def cancel(self, sender):
        self.parent.remove_overlay()
