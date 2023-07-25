""" WSLConfigurationAdvanced View

WSLConfigurationAdvanced provides user with options with additional settings
for advanced configuration.

"""
import re

from urwid import connect_signal

from subiquity.common.types import WSLConfigurationAdvanced
from subiquitycore.ui.form import BooleanField, Form, WantsToKnowFormField, simple_field
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView


class MountEditor(StringEditor, WantsToKnowFormField):
    def keypress(self, size, key):
        """restrict what chars we allow for mountpoints"""

        mountpoint = r"[a-zA-Z0-9_/\.\-]"
        if re.match(mountpoint, key) is None:
            return False

        return super().keypress(size, key)


MountField = simple_field(MountEditor)
StringField = simple_field(StringEditor)


class WSLConfigurationAdvancedForm(Form):
    def __init__(self, initial):
        super().__init__(initial=initial)

    automount_enabled = BooleanField(
        _("Enable Auto-Mount"),
        help=_(
            "Whether the Auto-Mount feature is enabled. "
            "This feature allows you to mount Windows drive"
            " in WSL."
        ),
    )
    automount_mountfstab = BooleanField(
        _("Mount `/etc/fstab`"),
        help=_(
            "Whether `/etc/fstab` will be mounted. The "
            "configuration file `/etc/fstab` contains "
            "the necessary information to automate the"
            " process of mounting partitions. "
        ),
    )
    interop_enabled = BooleanField(
        _("Enable Interop"), help=_("Whether the interoperability is enabled")
    )
    interop_appendwindowspath = BooleanField(
        _("Append Windows Path"),
        help=_(
            "Whether Windows Path will be append in the"
            " PATH environment variable in WSL."
        ),
    )
    # systemd_enabled = \
    #     BooleanField(_("Enable Systemd"),
    #                  help=_("EXPERIMENTAL - Whether systemd should be"
    #                         " activated at boot time."))


class WSLConfigurationAdvancedView(BaseView):
    title = _("WSL Configuration - Advanced options")
    excerpt = _(
        "In this page, you can configure Ubuntu WSL advanced options your needs. \n"
    )

    def __init__(self, controller, configuration_data):
        self.controller = controller

        initial = {
            "interop_enabled": configuration_data.interop_enabled,
            "interop_appendwindowspath": configuration_data.interop_appendwindowspath,
            "automount_enabled": configuration_data.automount_enabled,
            "automount_mountfstab": configuration_data.automount_mountfstab,
            # 'systemd_enabled':
            #    configuration_data.systemd_enabled,
        }
        self.form = WSLConfigurationAdvancedForm(initial=initial)

        connect_signal(self.form, "submit", self.done)
        super().__init__(
            screen(
                self.form.as_rows(),
                [self.form.done_btn],
                focus_buttons=True,
                excerpt=self.excerpt,
            )
        )

    def done(self, result):
        self.controller.done(
            WSLConfigurationAdvanced(
                interop_enabled=self.form.interop_enabled.value,
                interop_appendwindowspath=self.form.interop_appendwindowspath.value,
                automount_enabled=self.form.automount_enabled.value,
                automount_mountfstab=self.form.automount_mountfstab.value,
                # systemd_enabled=self.form
                # .systemd_enabled.value,
            )
        )
