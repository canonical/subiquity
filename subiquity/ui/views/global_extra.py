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

from urwid import Text

from subiquitycore.lsb_release import lsb_release
from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import Pile
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import button_pile

log = logging.getLogger('subiquity.ui.view.global_extra')


GLOBAL_KEY_HELP = _("""\
The following keys can be used at any time:""")

GLOBAL_KEYS = (
    (_('F1'),        _('help')),
    (_("ESC"),       _('go back')),
    )

DRY_RUN_KEYS = (
    (_('Control-X'), _('quit (dry-run only)')),
    )


ABOUT_INSTALLER = _("""
Welcome to the Ubuntu Server Installer!

The most popular server Linux in the cloud and data centre, you can
rely on Ubuntu Server and its five years of guaranteed free upgrades.

The installer will guide you through installing Ubuntu Server
{release}.

The installer only requires the up and down arrow keys, space (or
return) and the occasional bit of typing.""")


def rewrap(text):
    paras = text.split("\n\n")
    return "\n\n".join([p.replace('\n', ' ') for p in paras]).strip()


def close_btn(parent):
    return other_btn(
        _("Close"), on_press=lambda sender: parent.remove_overlay())


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
        super().__init__(_("Global Hot Keys"), widgets, 0, 2)


class SimpleTextStretchy(Stretchy):

    def __init__(self, parent, title, text):
        widgets = [
            Text(rewrap(text)),
            Text(""),
            button_pile([close_btn(parent)]),
            ]
        super().__init__(title, widgets, 0, 2)


class GlobalExtraStretchy(Stretchy):

    def __init__(self, app, parent):
        self.app = app
        self.parent = parent

        btns = []
        local_help = parent.local_help()
        if local_help:
            btns.append(
                other_btn(
                    _("View help on this screen"),
                    on_press=self.show_local_help))
        btns.append(
            other_btn(
                _("Read about this installer"),
                on_press=self.show_about))
        btns.append(
            other_btn(
                _("Read about global hot keys"),
                on_press=self.show_hot_keys))
        widgets = [
            button_pile(btns),
            Text(""),
            button_pile([close_btn(parent)]),
            ]

        super().__init__(_("Available Actions"), widgets, 0, 0)

    def show_local_help(self, sender):
        title, text = self.parent.local_help()
        self.parent.show_stretchy_overlay(
            SimpleTextStretchy(self.parent, title, text))

    def show_about(self, sender):
        self.parent.show_stretchy_overlay(
            SimpleTextStretchy(
                self.parent,
                _("About this installer"),
                _(ABOUT_INSTALLER).format(**lsb_release())))

    def show_hot_keys(self, sender):
        self.parent.show_stretchy_overlay(
            GlobalKeyStretchy(self.app, self.parent))
