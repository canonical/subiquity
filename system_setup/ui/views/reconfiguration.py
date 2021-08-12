""" Reconfiguration View

Integration provides user with options to set up integration configurations.

"""
import re

from urwid import (
    connect_signal,
)

from subiquitycore.ui.form import (
    Form,
    BooleanField,
    ChoiceField,
    simple_field,
    WantsToKnowFormField
)
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView
from subiquity.common.types import WSLConfiguration2Data


class MountEditor(StringEditor, WantsToKnowFormField):
    def keypress(self, size, key):
        ''' restrict what chars we allow for mountpoints '''

        mountpoint = r'[a-zA-Z0-9_/\.\-]'
        if re.match(mountpoint, key) is None:
            return False

        return super().keypress(size, key)


MountField = simple_field(MountEditor)
StringField = simple_field(StringEditor)


class ReconfigurationForm(Form):
    def __init__(self, initial):
        super().__init__(initial=initial)

    # TODO: placholder settings UI; should be dynamically generated using
    #  ubuntu-wsl-integration
    automount = BooleanField(_("Enable Auto-Mount"),
                             help=_("Whether the Auto-Mount freature is"
                                    " enabled. This feature allows you "
                                    "to mount Windows drive in WSL"))
    mountfstab = BooleanField(_("Mount `/etc/fstab`"),
                              help=_("Whether `/etc/fstab` will be mounted."
                                     " The configuration file `/etc/fstab` "
                                     "contains the necessary information to"
                                     " automate the process of mounting "
                                     "partitions. "))
    custom_path = MountField(_("Auto-Mount Location"),
                             help=_("Location for the automount"))
    custom_mount_opt = StringField(_("Auto-Mount Option"),
                                   help=_("Mount option passed for "
                                          "the automount"))
    gen_host = BooleanField(_("Enable Host Generation"), help=_(
        "Selecting enables /etc/host re-generation at every start"))
    gen_resolvconf = BooleanField(_("Enable resolv.conf Generation"), help=_(
        "Selecting enables /etc/resolv.conf re-generation at every start"))
    interop_enabled = BooleanField(_("Enable Interop"),
                                   help=_("Whether the interoperability is"
                                          " enabled"))
    interop_appendwindowspath = BooleanField(_("Append Windows Path"),
                                             help=_("Whether Windows Path "
                                                    "will be append in the"
                                                    " PATH environment "
                                                    "variable in WSL."))
    gui_theme = ChoiceField(_("GUI Theme"),
                            help=_("This option changes the Ubuntu theme."),
                            choices=["default", "light", "dark"])
    gui_followwintheme = BooleanField(_("Follow Windows Theme"),
                                      help=_("This option manages whether the"
                                             " Ubuntu theme follows the "
                                             "Windows theme; that is, when "
                                             "Windows uses dark theme, "
                                             "Ubuntu also uses dark theme."
                                             " Requires WSL interoperability"
                                             " enabled. "))
    legacy_gui = BooleanField(_("Legacy GUI Integration"),
                              help=_("This option enables the Legacy GUI "
                                     "Integration on Windows 10. Requires"
                                     " a Third-party X Server."))
    legacy_audio = BooleanField(_("Legacy Audio Integration"),
                                help=_("This option enables the Legacy "
                                       "Audio Integration on Windows 10. "
                                       "Requires PulseAudio for "
                                       "Windows Installed."))
    adv_ip_detect = BooleanField(_("Advanced IP Detection"),
                                 help=_("This option enables advanced "
                                        "detection of IP by Windows "
                                        "IPv4 Address which is more "
                                        "reliable to use with WSL2. "
                                        "Requires WSL interoperability"
                                        " enabled."))
    wsl_motd_news = BooleanField(_("Enable WSL News"),
                                 help=_("This options allows you to control"
                                        " your MOTD News. Toggling it on "
                                        "allows you to see the MOTD."))

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


class ReconfigurationView(BaseView):
    title = _("Configuration")
    excerpt = _("In this page, you can tweak Ubuntu WSL to your needs. \n")

    def __init__(self, controller, integration_data):
        self.controller = controller

        initial = {
            'custom_path': integration_data.custom_path,
            'custom_mount_opt': integration_data.custom_mount_opt,
            'gen_host': integration_data.gen_host,
            'gen_resolvconf': integration_data.gen_resolvconf,
            'interop_enabled': integration_data.interop_enabled,
            'interop_appendwindowspath':
                integration_data.interop_appendwindowspath,
            'gui_theme': integration_data.gui_theme,
            'gui_followwintheme': integration_data.gui_followwintheme,
            'legacy_gui': integration_data.legacy_gui,
            'legacy_audio': integration_data.legacy_audio,
            'adv_ip_detect': integration_data.adv_ip_detect,
            'wsl_motd_news': integration_data.wsl_motd_news,
            'automount': integration_data.automount,
            'mountfstab': integration_data.mountfstab,
        }
        self.form = ReconfigurationForm(initial=initial)

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
        self.controller.done(WSLConfiguration2Data(
            custom_path=self.form.custom_path.value,
            custom_mount_opt=self.form.custom_mount_opt.value,
            gen_host=self.form.gen_host.value,
            gen_resolvconf=self.form.gen_resolvconf.value,
            interop_enabled=self.form.interop_enabled.value,
            interop_appendwindowspath=self.form
            .interop_appendwindowspath.value,
            gui_theme=self.form.gui_theme.value,
            gui_followwintheme=self.form.gui_followwintheme.value,
            legacy_gui=self.form.legacy_gui.value,
            legacy_audio=self.form.legacy_audio.value,
            adv_ip_detect=self.form.adv_ip_detect.value,
            wsl_motd_news=self.form.wsl_motd_news.value,
            automount=self.form.automount.value,
            mountfstab=self.form.mountfstab.value,
            ))
