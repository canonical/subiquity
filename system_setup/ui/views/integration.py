""" Integration

Integration provides user with options to set up integration configurations.

"""
import re

from urwid import (
    connect_signal,
)

from subiquitycore.ui.form import (
    Form,
    BooleanField,
    simple_field,
    WantsToKnowFormField
)
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView
from subiquity.common.types import WSLConfiguration1Data


class MountEditor(StringEditor, WantsToKnowFormField):
    def keypress(self, size, key):
        ''' restrict what chars we allow for mountpoints '''

        mountpoint = r'[a-zA-Z0-9_/\.\-]'
        if re.match(mountpoint, key) is None:
            return False

        return super().keypress(size, key)


MountField = simple_field(MountEditor)
StringField = simple_field(StringEditor)


class IntegrationForm(Form):
    def __init__(self, initial):
        super().__init__(initial=initial)

    custom_path = MountField(_("Mount Location"),
                             help=_("Location for the automount"))
    custom_mount_opt = StringField(_("Mount Option"),
                                   help=_("Mount option passed "
                                          "for the automount"))
    gen_host = BooleanField(_("Enable Host Generation"), help=_(
        "Selecting enables /etc/host re-generation at every start"))
    gen_resolvconf = BooleanField(_("Enable resolv.conf Generation"), help=_(
        "Selecting enables /etc/resolv.conf re-generation at every start"))

    def validate_custom_path(self):
        p = self.custom_path.value
        if p != "" and (re.fullmatch(r"(/[^/ ]*)+/?", p) is None):
            return _("Mount location must be a absolute UNIX path"
                     " without space.")

    def validate_custom_mount_opt(self):
        o = self.custom_mount_opt.value
        # filesystem independent mount option
        fsimo = [r"async", r"(no)?atime", r"(no)?auto",
                 r"(fs|def|root)?context=\w+", r"(no)?dev", r"(no)?diratime",
                 r"dirsync", r"(no)?exec", r"group", r"(no)?iversion",
                 r"(no)?mand", r"_netdev", r"nofail", r"(no)?relatime",
                 r"(no)?strictatime", r"(no)?suid", r"owner", r"remount",
                 r"ro", r"rw", r"_rnetdev", r"sync", r"(no)?user", r"users"]
        # DrvFs filesystem mount option
        drvfsmo = r"case=(dir|force|off)|metadata|(u|g)id=\d+|(u|f|d)mask=\d+|"
        fso = "{0}{1}".format(drvfsmo, '|'.join(fsimo))

        if o != "":
            e_t = ""
            p = o.split(',')
            x = True
            for i in p:
                if i == "":
                    e_t += _("an empty entry detected; ")
                    x = x and False
                elif re.fullmatch(fso, i) is not None:
                    x = x and True
                else:
                    e_t += _("{} is not a valid mount option; ").format(i)
                    x = x and False
            if not x:
                return _("Invalid Input: {}Please check "
                         "https://docs.microsoft.com/en-us/windows/wsl/"
                         "wsl-config#mount-options "
                         "for correct valid input").format(e_t)


class IntegrationView(BaseView):
    title = _("Tweaks")
    excerpt = _("In this page, you can tweak Ubuntu WSL to your needs. \n")

    def __init__(self, controller, integration_data):
        self.controller = controller

        initial = {
            'custom_path': integration_data.custom_path,
            'custom_mount_opt': integration_data.custom_mount_opt,
            'gen_host': integration_data.gen_host,
            'gen_resolvconf': integration_data.gen_resolvconf,
        }
        self.form = IntegrationForm(initial=initial)

        connect_signal(self.form, 'submit', self.done)
        super().__init__(
            screen(
                self.form.as_rows(),
                [self.form.done_btn],
                focus_buttons=True,
                excerpt=self.excerpt,
            )
        )

    def done(self, result):
        self.controller.done(WSLConfiguration1Data(
            custom_path=self.form.custom_path.value,
            custom_mount_opt=self.form.custom_mount_opt.value,
            gen_host=self.form.gen_host.value,
            gen_resolvconf=self.form.gen_resolvconf.value
            ))
