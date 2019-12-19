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

from abc import ABC, abstractmethod
import logging

log = logging.getLogger("subiquitycore.controller")


class Skip(Exception):
    """Raise this from a controller's start_ui method to skip a screen."""


class BaseController(ABC):
    """Base class for controllers."""

    signals = []
    model_name = None

    def __init__(self, app):
        self.name = type(self).__name__[:-len("Controller")]
        self.ui = app.ui
        self.signal = app.signal
        self.opts = app.opts
        self.app = app
        self.context = self.app.context.child(self.name, childlevel="DEBUG")
        self.answers = app.answers.get(self.name, {})
        if self.model_name is not None:
            self.model = getattr(self.app.base_model, self.model_name)

    def register_signals(self):
        """Defines signals associated with controller from model."""
        signals = []
        for sig, cb in self.signals:
            signals.append((sig, getattr(self, cb)))
        self.signal.connect_signals(signals)

    def start(self):
        """Called just before the main loop is started.

        At the time this is called, all controllers and models and so on
        have been created. This is when the controller should start
        interacting with the outside world, e.g. probing for network
        devices or start making connections to the snap store.
        """
        pass

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

    def serialize(self):
        return None

    def deserialize(self, data):
        if data is not None:
            raise Exception("missing deserialize method on {}".format(self))

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

    def cancel(self):
        self.orig.cancel()
