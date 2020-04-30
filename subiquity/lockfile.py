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

import fcntl
import logging

from subiquitycore.async_helpers import run_in_thread

log = logging.getLogger('subiquity.lockfile')


class _LockContext:

    def __init__(self, lockfile, flags):
        self.lockfile = lockfile
        self.flags = flags
        self._kind = "???"
        if flags & fcntl.LOCK_EX:
            self._kind = "exclusive"
        elif flags & fcntl.LOCK_SH:
            self._kind = "shared"

    def __enter__(self):
        log.debug("locking %s %s", self._kind, self.lockfile.path)
        fcntl.flock(self.lockfile.fp, self.flags)
        return self

    async def __aenter__(self):
        return await run_in_thread(self.__enter__)

    def __exit__(self, etype, evalue, etb):
        log.debug("unlocking %s %s", self._kind, self.lockfile.path)
        fcntl.flock(self.lockfile.fp, fcntl.LOCK_UN)

    async def __aexit__(self, etype, evalue, etb):
        self.__exit__(etype, evalue, etb)


class Lockfile:

    def __init__(self, path):
        self.path = path
        self.fp = open(path, 'w')

    def exclusive(self):
        return _LockContext(self, fcntl.LOCK_EX)

    def shared(self):
        return _LockContext(self, fcntl.LOCK_SH)
