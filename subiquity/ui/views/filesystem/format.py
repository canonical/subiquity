# Copyright 2026 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from urwid import Text, connect_signal

from subiquity.common.filesystem import boot, labels
from subiquity.models.filesystem import Disk
from subiquity.ui.mount import (
    MountField,
    common_mountpoints,
    suitable_mountpoints_for_existing_fs,
)
from subiquitycore.ui.container import Pile
from subiquitycore.ui.form import BooleanField, Form, FormField
from subiquitycore.ui.selector import Selector
from subiquitycore.ui.stretchy import Stretchy

log = logging.getLogger("subiquity.ui.views.filesystem.format")


class FSTypeField(FormField):
    takes_default_style = False

    def _make_widget(self, form):
        # This will need to do something different for editing an
        # existing partition that is already formatted.
        options = [
            ("ext4", True),
            ("xfs", True),
            ("btrfs", True),
            ("---", False),
            ("swap", True),
        ]
        if form.existing_fs_type is None:
            options = options + [
                ("---", False),
                (_("Leave unformatted"), True, None),
            ]
        else:
            label = _("Leave formatted as {fstype}").format(
                fstype=form.existing_fs_type
            )
            options = [
                (label, True, None),
                ("---", False),
            ] + options
        sel = Selector(opts=options)
        sel.value = None
        return sel


class FormatForm(Form):
    """Form for formatting (and optionally mounting) a device without partitioning."""

    def __init__(
        self,
        model,
        initial,
        device,
        remote_storage: bool,
    ):
        self.model = model
        self.device = device
        self.existing_fs_type = None
        self.remote_storage: bool = remote_storage
        if device:
            ofstype = device.original_fstype()
            if ofstype:
                self.existing_fs_type = ofstype
        initial_path = initial.get("mount")
        self.mountpoints = {
            m.path: m.device.volume
            for m in self.model.all_mounts()
            if m.path != initial_path
        }
        super().__init__(initial)
        connect_signal(self.fstype.widget, "select", self.select_fstype)
        self.form_pile = None
        self.select_fstype(None, self.fstype.widget.value)

    fstype = FSTypeField(_("Format:"))
    mount = MountField(_("Mount:"))
    use_swap = BooleanField(
        _("Use as swap"), help=_("Use this swap partition in the installed system.")
    )

    def select_fstype(self, sender, fstype):
        show_use = False
        if fstype is None and self.existing_fs_type is not None:
            self.mount.widget.disable_unsuitable_mountpoints_for_existing_fs()
            self.mount.value = self.mount.value
        else:
            self.mount.widget.enable_common_mountpoints()
            self.mount.value = self.mount.value
        if self.remote_storage:
            self.mount.widget.disable_boot_boot_efi_mountpoints()
            self.mount.value = self.mount.value
        if fstype is None:
            if self.existing_fs_type == "swap":
                show_use = True
        if self.form_pile is not None:
            for i, (w, o) in enumerate(self.form_pile.contents):
                if w is self.mount._table and show_use:
                    self.form_pile.contents[i] = (self.use_swap._table, o)
                elif w is self.use_swap._table and not show_use:
                    self.form_pile.contents[i] = (self.mount._table, o)
        if not boot.is_esp(self.device):
            fstype_for_check = fstype
            if fstype_for_check is None:
                fstype_for_check = self.existing_fs_type
            self.mount.enabled = self.model.is_mounted_filesystem(fstype_for_check)
        self.fstype.value = fstype
        self.mount.showing_extra = False
        self.mount.validate()

    def clean_mount(self, val):
        if self.model.is_mounted_filesystem(self.fstype):
            return val
        else:
            return None

    def validate_mount(self):
        mount = self.mount.value
        if mount is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mount) > 4095:
            return _("Path exceeds PATH_MAX")
        dev = self.mountpoints.get(mount)
        if dev is not None:
            return _("{device} is already mounted at {path}.").format(
                device=labels.label(dev).title(), path=mount
            )
        if self.existing_fs_type is not None:
            if self.fstype.value is None:
                if mount in common_mountpoints:
                    if mount not in suitable_mountpoints_for_existing_fs:
                        self.mount.show_extra(
                            (
                                "info_error",
                                _(
                                    "Mounting an existing filesystem at "
                                    "{mountpoint} is usually a bad idea, "
                                    "proceed only with caution."
                                ).format(mountpoint=mount),
                            )
                        )
        if self.remote_storage and mount in ("/boot", "/boot/efi"):
            self.mount.show_extra(
                (
                    "info_error",
                    _(
                        f"The filesystem for {mount} should be stored on local"
                        " storage. Storing it on remote storage will likely"
                        " prevent the system from booting."
                    ),
                )
            )

    def as_rows(self):
        r = super().as_rows()
        if self.existing_fs_type == "swap":
            exclude = self.mount._table
        else:
            exclude = self.use_swap._table
        i = r.index(exclude)
        del r[i - 1 : i + 1]
        return r


def initial_data_for_fs(fs):
    r = {}
    if fs is not None:
        if fs.preserve:
            r["fstype"] = None
            if fs.fstype == "swap":
                r["use_swap"] = fs.mount() is not None
        else:
            r["fstype"] = fs.fstype
        if fs._m.is_mounted_filesystem(fs.fstype):
            mount = fs.mount()
            if mount is not None:
                r["mount"] = mount.path
            else:
                r["mount"] = None
    return r


class FormatEntireStretchy(Stretchy):
    def __init__(self, parent, device):
        self.device = device
        self.model = parent.model
        self.controller = parent.controller
        self.parent = parent

        initial = {}
        fs = device.fs()
        if fs is not None:
            initial.update(initial_data_for_fs(fs))
        elif not isinstance(device, Disk):
            initial["fstype"] = "ext4"
        self.form = FormatForm(
            self.model,
            initial,
            device,
            remote_storage=device.on_remote_storage(),
        )

        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)

        rows = []
        if isinstance(device, Disk):
            rows = [
                Text(
                    _(
                        "Formatting and mounting a disk directly is unusual. "
                        "You probably want to add a partition instead."
                    )
                ),
                Text(""),
            ]
        rows.extend(self.form.as_rows())
        self.form.form_pile = Pile(rows)
        widgets = [
            self.form.form_pile,
            Text(""),
            self.form.buttons,
        ]

        title = _("Format and/or mount {device}").format(device=labels.label(device))

        super().__init__(title, widgets, 0, 0)

    def cancel(self, button=None):
        self.parent.remove_overlay()

    def done(self, form):
        log.debug("Format Entire Result: {}".format(form.as_data()))
        self.controller.add_format_handler(self.device, form.as_data())
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()
