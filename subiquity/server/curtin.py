# Copyright 2021 Canonical, Ltd.
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
import sys

from curtin.commands.install import (
    INSTALL_LOG,
    )

from subiquitycore.context import Status

from subiquity.journald import (
    journald_listen,
    )

log = logging.getLogger('subiquity.server.curtin')


class CurtinCommandRunner:

    _count = 0

    def __init__(self, runner, config_location=None):
        self.runner = runner
        self._event_syslog_id = 'curtin_event.%s.%s' % (
            os.getpid(), CurtinCommandRunner._count)
        CurtinCommandRunner._count += 1
        self.config_location = config_location
        self._event_contexts = {}
        journald_listen(
            asyncio.get_event_loop(), [self._event_syslog_id], self._event)

    def _event(self, event):
        e = {
            "EVENT_TYPE": "???",
            "MESSAGE": "???",
            "NAME": "???",
            "RESULT": "???",
            }
        prefix = "CURTIN_"
        for k, v in event.items():
            if k.startswith(prefix):
                e[k[len(prefix):]] = v
        event_type = e["EVENT_TYPE"]
        if event_type == 'start':
            def p(name):
                parts = name.split('/')
                for i in range(len(parts), -1, -1):
                    yield '/'.join(parts[:i]), '/'.join(parts[i:])

            curtin_ctx = None
            for pre, post in p(e["NAME"]):
                if pre in self._event_contexts:
                    parent = self._event_contexts[pre]
                    curtin_ctx = parent.child(post, e["MESSAGE"])
                    self._event_contexts[e["NAME"]] = curtin_ctx
                    break
            if curtin_ctx:
                curtin_ctx.enter()
        if event_type == 'finish':
            status = getattr(Status, e["RESULT"], Status.WARN)
            curtin_ctx = self._event_contexts.pop(e["NAME"], None)
            if curtin_ctx is not None:
                curtin_ctx.exit(result=status)

    def make_command(self, command, *args, **conf):
        cmd = [
            sys.executable, '-m', 'curtin', '--showtrace',
            ]
        if self.config_location is not None:
            cmd.extend([
                '-c', self.config_location,
                ])
        conf.setdefault('reporting', {})['subiquity'] = {
            'type': 'journald',
            'identifier': self._event_syslog_id,
            }
        conf['verbosity'] = 3
        for k, v in conf.items():
            cmd.extend(['--set', 'json:' + k + '=' + json.dumps(v)])
        cmd.append(command)
        cmd.extend(args)
        return cmd

    async def run(self, context, command, *args, **conf):
        self._event_contexts[''] = context
        await self.runner.run(self.make_command(command, *args, **conf))
        waited = 0.0
        while len(self._event_contexts) > 1 and waited < 5.0:
            await asyncio.sleep(0.1)
            waited += 0.1
            log.debug("waited %s seconds for events to drain", waited)
        self._event_contexts.pop('', None)


class DryRunCurtinCommandRunner(CurtinCommandRunner):

    event_file = 'examples/curtin-events.json'

    def make_command(self, command, *args, **conf):
        if command == 'install':
            return [
                sys.executable, "scripts/replay-curtin-log.py",
                self.event_file, self._event_syslog_id,
                '.subiquity' + INSTALL_LOG,
                ]
        else:
            return super().make_command(command, *args, **conf)


class FailingDryRunCurtinCommandRunner(DryRunCurtinCommandRunner):

    event_file = 'examples/curtin-events-fail.json'


def get_curtin_command_runner(app, config_location=None):
    if app.opts.dry_run:
        if 'install-fail' in app.debug_flags:
            cls = FailingDryRunCurtinCommandRunner
        else:
            cls = DryRunCurtinCommandRunner
    else:
        cls = CurtinCommandRunner
    return cls(app.command_runner, config_location)
