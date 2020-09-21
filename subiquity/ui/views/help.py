# Copyright 2019 Canonical, Ltd.
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
import os
import io

from urwid import (
    connect_signal,
    Divider,
    Filler,
    PopUpLauncher,
    Text,
    )

from subiquitycore.lsb_release import lsb_release
from subiquitycore.ssh import host_key_info
from subiquitycore.ui.buttons import (
    header_btn,
    other_btn,
    )
from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    Color,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    rewrap,
    )
from subiquitycore.ui.width import (
    widget_width,
    )

from subiquity.ui.views.error import ErrorReportListStretchy

log = logging.getLogger('subiquity.ui.help')


def close_btn(app, stretchy):
    return other_btn(
        _("Close"),
        on_press=lambda sender: app.remove_global_overlay(stretchy))


ABOUT_INSTALLER = _("""
Welcome to the Ubuntu Server Installer!

The most popular server Linux in the cloud and data centre, this
release of Ubuntu will receive updates for 9 months from release.

The installer will guide you through installing Ubuntu Server
{release}.

The installer only requires the up and down arrow keys, space (or
return) and the occasional bit of typing.

This is version {snap_version} of the installer.
""")


ABOUT_INSTALLER_LTS = _("""
Welcome to the Ubuntu Server Installer!

The most popular server Linux in the cloud and data centre, you can
rely on Ubuntu Server and its five years of guaranteed free upgrades.

The installer will guide you through installing Ubuntu Server
{release} LTS.

The installer only requires the up and down arrow keys, space (or
return) and the occasional bit of typing.

This is version {snap_version} of the installer.
""")


SSH_HELP_PROLOGUE = _("""
It is possible to connect to the installer over the network, which
might allow the use of a more capable terminal and can offer more languages
than can be rendered in the Linux console.""")

SSH_HELP_MULTIPLE_ADDRESSES = _("""
To connect, SSH to any of these addresses:
""")

SSH_HELP_ONE_ADDRESSES = _("""
To connect, SSH to installer@{ip}.
""")

SSH_HELP_EPILOGUE = _("""
The password you should use is "{password}".
""")

SSH_HELP_NO_ADDRESSES = _("""
Unfortunately this system seems to have no global IP addresses at this
time.
""")

SSH_HELP_NO_PASSWORD = _("""
Unfortunately the installer was unable to detect the password that has
been set.
""")


def ssh_help_texts(ips, password):

    texts = [_(SSH_HELP_PROLOGUE), ""]

    if len(ips) > 0:
        if len(ips) > 1:
            texts.append(rewrap(_(SSH_HELP_MULTIPLE_ADDRESSES)))
            texts.append("")
            for ip in ips:
                texts.append(Text(
                    "installer@" + str(ip), align='center'))
        else:
            texts.append(_(SSH_HELP_ONE_ADDRESSES).format(
                ip=str(ips[0])))
        texts.append("")
        texts.append(
            rewrap(_(SSH_HELP_EPILOGUE).format(
                password=password)))
        texts.append("")
        texts.append(Text(host_key_info()))
    else:
        texts.append("")
        texts.append(_(SSH_HELP_NO_ADDRESSES))

    return texts


class SimpleTextStretchy(Stretchy):

    def __init__(self, app, title, *texts):
        widgets = []

        for text in texts:
            if isinstance(text, str):
                text = Text(rewrap(text))
            widgets.append(text)

        widgets.extend([
            Text(""),
            button_pile([close_btn(app, self)]),
            ])
        super().__init__(title, widgets, 0, len(widgets)-1)


GLOBAL_KEY_HELP = _("""\
The following keys can be used at any time:""")

GLOBAL_KEYS = (
    (_("ESC"),           _('go back')),
    (_('F1'),            _('open help menu')),
    (_('Control-Z, F2'), _('switch to shell')),
    (_('Control-L, F3'), _('redraw screen')),
    )

SERIAL_GLOBAL_HELP_KEYS = (
    (_('Control-T, F4'), _('toggle rich mode (colour, unicode) on and off')),
    )

DRY_RUN_KEYS = (
    (_('Control-X'), _('quit')),
    (_('Control-E'), _('generate noisy error report')),
    (_('Control-R'), _('generate quiet error report')),
    (_('Control-G'), _('pretend to run an install')),
    (_('Control-U'), _('crash the ui')),
    )


class GlobalKeyStretchy(Stretchy):

    def __init__(self, app):
        rows = []
        keys = GLOBAL_KEYS
        if app.opts.run_on_serial:
            keys += SERIAL_GLOBAL_HELP_KEYS
        for key, text in keys:
            rows.append(TableRow([Text(_(key)), Text(_(text))]))
        if app.opts.dry_run:
            dro = _('(dry-run only)')
            for key, text in DRY_RUN_KEYS:
                rows.append(TableRow([
                    Text(_(key)),
                    Text(_(text) + ' ' + dro)]))
        table = TablePile(
            rows, spacing=2, colspecs={1: ColSpec(can_shrink=True)})
        widgets = [
            Pile([
                ('pack', Text(rewrap(GLOBAL_KEY_HELP))),
                ('pack', Text("")),
                ('pack', table),
                ]),
            Text(""),
            button_pile([close_btn(app, self)]),
            ]
        super().__init__(_("Shortcut Keys"), widgets, 0, 2)


hline = Divider('─')
vline = Text('│')
tlcorner = Text('┌')
trcorner = Text('┐')
blcorner = Text('└')
brcorner = Text('┘')
rtee = Text('┤')
ltee = Text('├')


def menu_item(text, on_press=None):
    icon = ClickableIcon(" " + text + " ")
    if on_press is not None:
        connect_signal(icon, 'click', on_press)
    return Color.frame_button(icon)


def get_global_addresses(app):
    ips = []
    net_model = app.base_model.network
    for dev in net_model.get_all_netdevs():
        ips.extend(dev.actual_global_ip_addresses)
    return ips


def get_installer_password(dry_run=False):
    if dry_run:
        fp = io.StringIO('installer:rAnd0Mpass')
    else:
        try:
            fp = open("/var/log/cloud-init-output.log")
        except FileNotFoundError:
            fp = io.StringIO('')

    with fp:
        for line in fp:
            if line.startswith("installer:"):
                return line[len("installer:"):].strip()

    return None


class OpenHelpMenu(WidgetWrap):

    def __init__(self, parent):
        self.parent = parent
        close = header_btn(parent.base_widget.label)
        about = menu_item(
            _("About this installer"), on_press=self.parent.about)
        keys = menu_item(
            _("Keyboard shortcuts"), on_press=self.parent.shortcuts)
        drop_to_shell = menu_item(
            _("Enter shell"), on_press=self.parent.debug_shell)
        buttons = {
            about,
            close,
            drop_to_shell,
            keys,
            }
        if self.parent.ssh_password is not None:
            ssh_help = menu_item(
                _("Help on SSH access"), on_press=self.parent.ssh_help)
            buttons.add(ssh_help)
        if self.parent.app.opts.run_on_serial:
            rich = menu_item(
                _("Toggle rich mode"), on_press=self.parent.toggle_rich)
            buttons.add(rich)
        local_title = None
        if hasattr(parent.app.ui.body, 'local_help'):
            local_title, local_doc = parent.app.ui.body.local_help()
        if local_title is not None:
            local = menu_item(
                local_title,
                on_press=self.parent.show_local(local_title, local_doc))
            buttons.add(local)
        else:
            local = Text(
                ('info_minor header', " " + _("Help on this screen") + " "))

        self.parent.app.error_reporter.load_reports()
        if self.parent.app.error_reporter.reports:
            view_errors = menu_item(
                _("View error reports").format(local_title),
                on_press=self.parent.show_errors)
            buttons.add(view_errors)
        else:
            view_errors = Text(
                ('info_minor header', " " + _("View error reports") + " "))

        for button in buttons:
            connect_signal(button.base_widget, 'click', self._close)

        entries = [
            local,
            keys,
            drop_to_shell,
            view_errors,
            hline,
            about,
            ]

        if self.parent.ssh_password is not None:
            entries.append(ssh_help)

        if self.parent.app.opts.run_on_serial:
            entries.extend([
                hline,
                rich,
                ])

        rows = [
            Columns([
                ('fixed', 1, tlcorner),
                hline,
                (widget_width(close), close),
                ('fixed', 1, trcorner),
                ]),
            ]
        for entry in entries:
            if isinstance(entry, Divider):
                left, right = ltee, rtee
            else:
                left = right = vline
            rows.append(Columns([
                ('fixed', 1, left),
                entry,
                ('fixed', 1, right),
                ]))
        rows.append(
            Columns([
                (1, blcorner),
                hline,
                (1, brcorner),
                ]))
        self.width = max([
            widget_width(b) for b in entries
            if not isinstance(b, Divider)
            ]) + 2
        self.height = len(entries) + 2
        super().__init__(Color.frame_header(Filler(Pile(rows))))

    def keypress(self, size, key):
        if key == 'esc':
            self.parent.close_pop_up()
        else:
            return super().keypress(size, key)

    def _close(self, sender):
        self.parent.close_pop_up()


class HelpMenu(PopUpLauncher):

    def __init__(self, app):
        self.app = app
        self.btn = header_btn(_("Help"), on_press=self._open)
        self.ssh_password = None
        self.current_help = None
        super().__init__(self.btn)

    def _open(self, sender):
        log.debug("open help menu")
        self.open_pop_up()

    def create_pop_up(self):
        if self.ssh_password is None:
            self.ssh_password = get_installer_password(self.app.opts.dry_run)
        self._menu = OpenHelpMenu(self)
        return self._menu

    def get_pop_up_parameters(self):
        return {
            'left': widget_width(self.btn) - self._menu.width + 1,
            'top': 0,
            'overlay_width': self._menu.width,
            'overlay_height': self._menu.height,
            }

    def _show_overlay(self, stretchy):
        ui = self.app.ui

        # We don't let help dialogs pile up: if one is already
        # showing, remove it before showing the new one.
        if self.current_help:
            self.app.remove_global_overlay(self.current_help)
        self.current_help = stretchy
        fp, ui.pile.focus_position = ui.pile.focus_position, 1

        def on_close():
            self.current_help = None
            ui.pile.focus_position = fp

        connect_signal(stretchy, 'closed', on_close)

        self.app.add_global_overlay(stretchy)

    def about(self, sender=None):
        info = lsb_release()
        if 'LTS' in info['description']:
            template = _(ABOUT_INSTALLER_LTS)
        else:
            template = _(ABOUT_INSTALLER)
        info.update({
            'snap_version': os.environ.get("SNAP_VERSION", "SNAP_VERSION"),
            'snap_revision': os.environ.get("SNAP_REVISION", "SNAP_REVISION"),
            })
        self._show_overlay(
            SimpleTextStretchy(
                self.app,
                _("About the installer"),
                template.format(**info)))

    def ssh_help(self, sender=None):
        texts = ssh_help_texts(
            get_global_addresses(self.app),
            self.ssh_password)

        self._show_overlay(
            SimpleTextStretchy(
                self.app,
                _("Help on SSH access"),
                *texts,
                ))

    def show_local(self, local_title, local_doc):

        def cb(sender=None):
            self._show_overlay(
                SimpleTextStretchy(
                    self.app,
                    local_title,
                    local_doc))
        return cb

    def shortcuts(self, sender):
        self._show_overlay(GlobalKeyStretchy(self.app))

    def debug_shell(self, sender):
        self.app.debug_shell()

    def toggle_rich(self, sender):
        self.app.toggle_rich()

    def show_errors(self, sender):
        self._show_overlay(ErrorReportListStretchy(self.app))
