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
