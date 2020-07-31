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
import logging

from subiquitycore.controller import BaseController

log = logging.getLogger("subiquitycore.tuicontroller")


class Skip(Exception):
    """Raise this from a controller's start_ui method to skip a screen."""


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
    def start_ui(self):
        """Start running this controller's UI.

        This method should call self.ui.set_body.
        """

    def end_ui(self):
        """Stop running this controller's UI.

        This method doesn't actually need to remove this controller's UI
        as the next one is about to replace it, it's more of a hook to
        stop any background tasks that can be stopped when the UI is not
        running.
        """

    # Stuff for fine grained actions, used by filesystem and network
    # controller at time of writing this comment.

    def _enter_form_data(self, form, data, submit, clean_suffix=''):
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
        yield
        for bf in form._fields:
            bf.validate()
        form.validated()
        if submit:
            if not form.done_btn.enabled:
                raise Exception("answers left form invalid!")
            form._click_done(None)

    def _run_actions(self, actions):
        for action in actions:
            yield from self._answers_action(action)

    def _run_iterator(self, it, delay=None):
        if delay is None:
            delay = 0.2/self.app.scale_factor
        try:
            next(it)
        except StopIteration:
            return
        self.app.aio_loop.call_later(delay, self._run_iterator, it, delay/1.1)


class RepeatedController(BaseController):

    def __init__(self, orig, index):
        self.name = "{}-{}".format(orig.name, index)
        self.orig = orig
        self.index = index
        self.context = orig.context

    def register_signals(self):
        pass

    def start_ui(self):
        self.orig.start_ui(self.index)

    def end_ui(self):
        self.orig.end_ui()

    def cancel(self):
        self.orig.cancel()
