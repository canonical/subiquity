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

import contextlib

from systemd import journal


def journald_listen(loop, identifiers, callback, seek=False):
    reader = journal.Reader()
    args = []
    for identifier in identifiers:
        args.append("SYSLOG_IDENTIFIER={}".format(identifier))
    reader.add_match(*args)

    if seek:
        reader.seek_tail()

    def watch():
        if reader.process() != journal.APPEND:
            return
        for event in reader:
            callback(event)
    loop.add_reader(reader.fileno(), watch)
    return reader.fileno()


@contextlib.contextmanager
def journald_subscriptions(loop, ids_callbacks):
    fds = set()
    for id, callback in ids_callbacks:
        fds.add(journald_listen(loop, [id], callback))
    try:
        yield
    finally:
        for fd in fds:
            loop.remove_reader(fd)
