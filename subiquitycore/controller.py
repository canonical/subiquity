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


class BaseController(ABC):
    """Base class for controllers."""

    signals = []

    def __init__(self, common):
        self.ui = common['ui']
        self.signal = common['signal']
        self.opts = common['opts']
        self.loop = common['loop']
        self.prober = common['prober']
        self.controllers = common['controllers']
        self.pool = common['pool']
        self.base_model = common['base_model']
        self.all_answers = common['answers']
        self.input_filter = common['input_filter']
        self.scale_factor = common['scale_factor']
        self.run_in_bg = common['run_in_bg']
        if 'snapd_connection' in common:
            self.snapd_connection = common['snapd_connection']

    def register_signals(self):
        """Defines signals associated with controller from model."""
        signals = []
        for sig, cb in self.signals:
            signals.append((sig, getattr(self, cb)))
        self.signal.connect_signals(signals)

    def start(self):
        pass

    @abstractmethod
    def cancel(self):
        pass

    @abstractmethod
    def default(self):
        pass

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
            delay = 0.2/self.scale_factor
        try:
            next(it)
        except StopIteration:
            return
        self.loop.set_alarm_in(
            delay,
            lambda *args: self._run_iterator(it, delay/1.1))
