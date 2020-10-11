# Copyright 2020 Canonical, Ltd.
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

from abc import abstractmethod
import asyncio
import logging

from subiquitycore.controller import BaseController

log = logging.getLogger("subiquitycore.tuicontroller")


class Skip(Exception):
    """Raise this from a controller's make_ui method to skip a screen."""


class TuiController(BaseController):
    """Base class for controllers."""

    def __init__(self, app):
        super().__init__(app)
        self.ui = app.ui
        self.answers = app.answers.get(self.name, {})

    @abstractmethod
    def cancel(self):
        pass

    @property
    def showing(self):
        inst = self.app.controllers.cur
        while isinstance(inst, RepeatedController):
            inst = inst.orig
        return inst is self

    @abstractmethod
    def make_ui(self):
        """Return the view for this controller's UI."""

    def end_ui(self):
        """Stop running this controller's UI.

        This method doesn't actually need to remove this controller's UI
        as the next one is about to replace it, it's more of a hook to
        stop any background tasks that can be stopped when the UI is not
        running.
        """

    # Stuff for fine grained actions, used by filesystem and network
    # controller at time of writing this comment.

    async def _enter_form_data(self, form, data, submit, clean_suffix=''):
        for k, v in data.items():
            c = getattr(
                self, '_action_clean_{}_{}'.format(k, clean_suffix), None)
            if c is None:
                c = getattr(self, '_action_clean_{}'.format(k), lambda x: x)
            field = getattr(form, k)
            from subiquitycore.ui.selector import Selector
            v = c(v)
            if isinstance(field.widget, Selector):
                field.widget._emit('select', v)
            field.value = v
            yield
        for bf in form._fields:
            bf.validate()
        form.validated()
        if submit:
            if not form.done_btn.enabled:
                raise Exception("answers left form invalid!")
            form._click_done(None)

    async def _run_actions(self, actions):
        delay = 0.2/self.app.scale_factor
        for action in actions:
            async for _ in self._answers_action(action):
                await asyncio.sleep(delay)
                delay /= 1.1


class RepeatedController(BaseController):

    def __init__(self, orig, index):
        self.name = "{}-{}".format(orig.name, index)
        self.orig = orig
        self.index = index
        self.context = orig.context

    def register_signals(self):
        pass

    def make_ui(self):
        return self.orig.make_ui(self.index)

    def run_answers(self):
        self.orig.run_answers()

    def end_ui(self):
        self.orig.end_ui()

    def cancel(self):
        self.orig.cancel()

    @property
    def answers(self):
        return self.orig.answers
