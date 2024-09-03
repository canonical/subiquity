# Copyright 2024 Canonical, Ltd.
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
import logging
import os
import pathlib
from typing import Optional, Tuple

import requests

from subiquity.server.mounter import Mounter
from subiquity.server.snapd.types import SystemDetails

log = logging.getLogger("subiquity.server.snapd.system_getter")


class NoSnapdSystemsOnSource(Exception):
    pass


class SystemsDirMounter:
    def __init__(self, app, variation_name):
        self.app = app
        self.variation_name = variation_name

    async def mount(self):
        source_handler = self.app.controllers.Source.get_handler(self.variation_name)
        if source_handler is None:
            raise NoSnapdSystemsOnSource
        mounter = Mounter(self.app)
        source_path = source_handler.setup()
        cur_systems_dir = "/var/lib/snapd/seed/systems"
        source_systems_dir = os.path.join(source_path, cur_systems_dir[1:])
        if self.app.opts.dry_run:
            systems_dir_exists = self.app.dr_cfg.systems_dir_exists
        else:
            systems_dir_exists = pathlib.Path(source_systems_dir).is_dir()
        if not systems_dir_exists:
            raise NoSnapdSystemsOnSource
        if not self.app.opts.dry_run:
            await mounter.bind_mount_tree(source_systems_dir, cur_systems_dir)
        return source_handler, mounter

    @contextlib.asynccontextmanager
    async def mounted(self):
        source_handler, mounter = await self.mount()
        try:
            yield
        finally:
            await mounter.cleanup()
            source_handler.cleanup()


class SystemGetter:
    def __init__(self, app):
        self.app = app

    async def _get(self, label: str) -> SystemDetails:
        try:
            return await self.app.snapdapi.v2.systems[label].GET()
        except requests.exceptions.HTTPError as http_err:
            log.warning("v2/systems/%s returned %s", label, http_err.response.text)
            raise

    async def get(
        self, variation_name: str, label: str
    ) -> Tuple[Optional[SystemDetails], bool]:
        """Return system information for a given system label.

        The return value is a SystemDetails object (if any) and True if
        the system was found in the layer that the installer is running
        in or False if the source layer needed to be mounted to find
        it.
        """
        systems = await self.app.snapdapi.v2.systems.GET()
        labels = {system.label for system in systems.systems}
        if label in labels:
            return await self._get(label), True
        else:
            try:
                async with SystemsDirMounter(self.app, variation_name).mounted():
                    return await self._get(label), False
            except NoSnapdSystemsOnSource:
                return None, False
