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

import asyncio
import contextlib

from systemd import journal


def journald_listen(identifiers, callback, seek=False):
    reader = journal.Reader()
    args = []
    for identifier in identifiers:
        if "=" in identifier:
            args.append(identifier)
        else:
            args.append("SYSLOG_IDENTIFIER={}".format(identifier))
    reader.add_match(*args)

    if seek:
        reader.seek_tail()

    def watch():
        if reader.process() != journal.APPEND:
            return
        for event in reader:
            callback(event)

    loop = asyncio.get_running_loop()
    loop.add_reader(reader.fileno(), watch)
    return reader.fileno()


@contextlib.contextmanager
def journald_subscriptions(ids_callbacks, seek=False):
    fds = set()
    for ids, callback in ids_callbacks:
        fds.add(journald_listen(ids, callback, seek=seek))
    try:
        yield
    finally:
        loop = asyncio.get_running_loop()
        for fd in fds:
            loop.remove_reader(fd)


async def journald_get_first_match(*identifiers, seek=False):
    def cb(_event):
        nonlocal event
        event = _event
        found.set()

    event = None
    found = asyncio.Event()
    with journald_subscriptions(((identifiers, cb),), seek=seek):
        await found.wait()
    return event
