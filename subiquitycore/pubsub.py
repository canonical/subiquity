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
import inspect


class CoreChannels:
    NETWORK_UP = 'network-up'


class MessageHub:

    def __init__(self):
        self.subscriptions = {}

    def subscribe(self, channel, method, *args):
        self.subscriptions.setdefault(channel, []).append((method, args))

    async def abroadcast(self, channel):
        for m, args in self.subscriptions.get(channel, []):
            v = m(*args)
            if inspect.iscoroutine(v):
                await v

    def broadcast(self, channel):
        return asyncio.get_event_loop().create_task(self.abroadcast(channel))
