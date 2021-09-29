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
from subiquity.common.types import KeyboardSetting
from subiquity.ui.views import KeyboardView

log = logging.getLogger('subiquity.client.controllers.keyboard')


class KeyboardController(SubiquityTuiController):

    endpoint_name = 'keyboard'

    async def make_ui(self):
        setup = await self.endpoint1.GET()
        return KeyboardView(self, setup)

    async def run_answers(self):
        if 'layout' in self.answers:
            layout = self.answers['layout']
            variant = self.answers.get('variant', '')
            await self.apply(KeyboardSetting(layout=layout, variant=variant))
            self.done()

    async def get_step(self, index):
        return await self.endpoint.steps.GET(index)

    async def needs_toggle(self, setting):
        return await self.endpoint.needs_toggle.GET(
            layout_code=setting.layout, variant_code=setting.variant)

    async def apply(self, setting):
        await self.endpoint.POST(setting)

    def done(self):
        self.app.next_screen()

    def cancel(self):
        self.app.prev_screen()
