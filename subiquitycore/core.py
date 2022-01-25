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

import asyncio
import json
import logging
import os

from subiquitycore.context import (
    Context,
    )
from subiquitycore.controllerset import ControllerSet
from subiquitycore.pubsub import MessageHub

log = logging.getLogger('subiquitycore.core')


class Application:

    # A concrete subclass must set project and controllers attributes, e.g.:
    #
    # project = "subiquity"
    # controllers = [
    #         "Welcome",
    #         "Network",
    #         "Filesystem",
    #         "Identity",
    #         "InstallProgress",
    # ]
    # The 'next_screen' and 'prev_screen' methods move through the list of
    # controllers in order, calling the make_ui method on the controller
    # instance.

    def __init__(self, opts):
        self._exc = None
        self.debug_flags = ()
        if opts.dry_run:
            # Recognized flags are:
            #  - install-fail: makes curtin install fail by replaying curtin
            #    events from a failed installation, see
            #    subiquity/controllers/installprogress.py
            #  - bpfail-full, bpfail-restricted: makes block probing fail, see
            #    subiquitycore/prober.py
            #  - copy-logs-fail: makes post-install copying of logs fail, see
            #    subiquity/controllers/installprogress.py
            self.debug_flags = os.environ.get('SUBIQUITY_DEBUG', '').split(',')

        self.opts = opts
        opts.project = self.project

        self.root = '/'
        if opts.dry_run:
            self.root = opts.output_base
        self.state_dir = os.path.join(self.root, 'run', self.project)
        os.makedirs(self.state_path('states'), exist_ok=True)

        self.scale_factor = float(
            os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "1"))
        self.updated = os.path.exists(self.state_path('updating'))
        self.hub = MessageHub()
        self.aio_loop = asyncio.get_event_loop()
        self.aio_loop.set_exception_handler(self._exception_handler)
        self.load_controllers(self.controllers)
        self.context = Context.new(self)

    def load_controllers(self, controllers):
        """ Load the corresponding list of controllers

        Those will need to be restarted if already started """
        self.controllers = ControllerSet(
            self.controllers_mod, controllers,
            init_args=(self,))

    def _exception_handler(self, loop, context):
        exc = context.get('exception')
        if exc:
            loop.stop()
            self._exc = exc
        else:
            loop.default_exception_handler(context)

    def state_path(self, *parts):
        return os.path.join(self.state_dir, *parts)

    def save_state(self):
        cur = self.controllers.cur
        if cur is None:
            return
        with open(self.state_path('states', cur.name), 'w') as fp:
            json.dump(cur.serialize(), fp)

    def report_start_event(self, context, description):
        log = logging.getLogger(context.full_name())
        level = getattr(logging, context.level)
        log.log(level, "start: %s", description)

    def report_finish_event(self, context, description, status):
        log = logging.getLogger(context.full_name())
        level = getattr(logging, context.level)
        log.log(level, "finish: %s %s", description, status.name)

# EventLoop -------------------------------------------------------------------

    def exit(self):
        self.aio_loop.stop()

    def start_controllers(self):
        log.debug("starting controllers")
        for controller in self.controllers.instances:
            controller.start()
        log.debug("controllers started")

    async def start(self):
        self.controllers.load_all()
        self.start_controllers()

    def run(self):
        self.base_model = self.make_model()
        self.aio_loop.create_task(self.start())
        self.aio_loop.run_forever()
        if self._exc:
            exc, self._exc = self._exc, None
            raise exc
