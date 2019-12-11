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

from urwid import (
    connect_signal,
    Divider,
    Filler,
    PopUpLauncher,
    Text,
    )

from subiquitycore.lsb_release import lsb_release
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


def close_btn(parent):
    return other_btn(
        _("Close"), on_press=lambda sender: parent.remove_overlay())


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


class SimpleTextStretchy(Stretchy):

    def __init__(self, parent, title, text):
        widgets = [
            Text(rewrap(text)),
            Text(""),
            button_pile([close_btn(parent)]),
            ]
        super().__init__(title, widgets, 0, 2)


GLOBAL_KEY_HELP = _("""\
The following keys can be used at any time:""")

GLOBAL_KEYS = (
    (_("ESC"),           _('go back')),
    (_('F1'),            _('open help menu')),
    (_('Control-Z, F2'), _('switch to shell')),
    (_('Control-L, F3'), _('redraw screen')),
    (_('Control-T, F4'), _('toggle color on and off')),
    )

DRY_RUN_KEYS = (
    (_('Control-X'), _('quit (dry-run only)')),
    (_('Control-E'), _('generate noisy error report (dry-run only)')),
    (_('Control-R'), _('generate quiet error report (dry-run only)')),
    (_('Control-U'), _('crash the ui (dry-run only)')),
    )


class GlobalKeyStretchy(Stretchy):

    def __init__(self, app, parent):
        rows = []
        for key, text in GLOBAL_KEYS:
            rows.append(TableRow([Text(_(key)), Text(_(text))]))
        if app.opts.dry_run:
            for key, text in DRY_RUN_KEYS:
                rows.append(TableRow([Text(_(key)), Text(_(text))]))
        table = TablePile(
            rows, spacing=2, colspecs={1: ColSpec(can_shrink=True)})
        widgets = [
            Pile([
                ('pack', Text(rewrap(GLOBAL_KEY_HELP))),
                ('pack', Text("")),
                ('pack', table),
                ]),
            Text(""),
            button_pile([close_btn(parent)]),
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


class HelpMenu(WidgetWrap):

    def __init__(self, parent):
        self.parent = parent
        close = header_btn(parent.base_widget.label)
        about = menu_item(_("About this installer"), on_press=self._about)
        keys = menu_item(
            _("Keyboard shortcuts"), on_press=self._shortcuts)
        drop_to_shell = menu_item(
            _("Enter shell"), on_press=self._debug_shell)
        color = menu_item(
            _("Toggle color on/off"), on_press=self._toggle_color)
        buttons = {
            close,
            about,
            keys,
            drop_to_shell,
            color,
            }
        local_title, local_doc = parent.app.ui.body.local_help()
        if local_title is not None:
            local = menu_item(
                local_title,
                on_press=self._show_local(local_title, local_doc))
            buttons.add(local)
        else:
            local = Text(
                ('info_minor header', " " + _("Help on this screen") + " "))

        if self.parent.app.controllers.Error.reports:
            view_errors = menu_item(
                _("View error reports").format(local_title),
                on_press=self._show_errors)
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
            hline,
            color,
            ]

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

    def _show_overlay(self, stretchy):
        ui = self.parent.app.ui

        # We don't let help dialogs pile up: if one is already
        # showing, remove it before showing the new one.
        if self.parent.showing_something:
            ui.body.remove_overlay()
        self.parent.showing_something = True
        fp, ui.pile.focus_position = ui.pile.focus_position, 1

        def on_close():
            self.parent.showing_something = False
            ui.pile.focus_position = fp

        connect_signal(stretchy, 'closed', on_close)

        ui.body.show_stretchy_overlay(stretchy)

    def _about(self, sender=None):
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
                self.parent.app.ui.body,
                _("About the installer"),
                template.format(**info)))

    def _show_local(self, local_title, local_doc):

        def cb(sender=None):
            self._show_overlay(
                SimpleTextStretchy(
                    self.parent.app.ui.body,
                    local_title,
                    local_doc))
        return cb

    def _shortcuts(self, sender):
        self._show_overlay(
            GlobalKeyStretchy(
                self.parent.app,
                self.parent.app.ui.body))

    def _debug_shell(self, sender):
        self.parent.app.debug_shell()

    def _toggle_color(self, sender):
        self.parent.app.toggle_color()

    def _show_errors(self, sender):
        self._show_overlay(
            ErrorReportListStretchy(
                self.parent.app,
                self.parent.app.ui.body))


class HelpButton(PopUpLauncher):

    def __init__(self, app):
        self.app = app
        self.btn = header_btn(_("Help"), on_press=self._open)
        self.showing_something = False
        super().__init__(self.btn)

    def _open(self, sender):
        log.debug("open help menu")
        self.open_pop_up()

    def create_pop_up(self):
        self._menu = HelpMenu(self)
        return self._menu

    def get_pop_up_parameters(self):
        return {
            'left': widget_width(self.btn) - self._menu.width + 1,
            'top': 0,
            'overlay_width': self._menu.width,
            'overlay_height': self._menu.height,
            }
