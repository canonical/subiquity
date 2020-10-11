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

from subiquity.client.controller import SubiquityTuiController
from subiquity.client.keyboard import KeyboardList
from subiquity.common.types import KeyboardSetting
from subiquity.common.keyboard import (
    set_keyboard,
    )
from subiquity.ui.views import KeyboardView

log = logging.getLogger('subiquity.client.controllers.keyboard')


class KeyboardController(SubiquityTuiController):

    endpoint_name = 'keyboard'

    signals = [
        ('l10n:language-selected', 'language_selected'),
        ]

    def __init__(self, app):
        super().__init__(app)
        self.keyboard_list = KeyboardList()

    def language_selected(self, code):
        log.debug("language_selected %s", code)
        if not self.keyboard_list.has_language(code):
            code = code.split('_')[0]
        if not self.keyboard_list.has_language(code):
            code = 'C'
        log.debug("loading language %s", code)
        self.keyboard_list.load_language(code)

    async def make_ui(self):
        if self.keyboard_list.current_lang is None:
            self.keyboard_list.load_language('C')
        initial_setting = await self.endpoint.GET()
        view = KeyboardView(self, initial_setting)
        return view

    def run_answers(self):
        if 'layout' in self.answers:
            layout = self.answers['layout']
            variant = self.answers.get('variant', '')
            self.done(KeyboardSetting(layout=layout, variant=variant), True)

    async def set_keyboard(self, setting):
        await set_keyboard(self.app.root, setting, self.opts.dry_run)
        self.done(setting, False)

    def done(self, setting, apply):
        log.debug("KeyboardController.done %s next_screen", setting)
        if apply:
            self.app.aio_loop.create_task(self.set_keyboard(setting))
        else:
            self.app.next_screen(self.endpoint.POST(setting))

    def cancel(self):
        self.app.prev_screen()
