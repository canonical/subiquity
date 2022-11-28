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

import yaml

import attr


class DryRunController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("DryRun")

    async def crash_GET(self) -> None:
        1/0


@attr.s(auto_attribs=True)
class DRConfig:
    """ Configuration for dry-run-only executions.
    All variables here should have default values ; to indicate the behavior we
    want by default in dry-run mode. """

    # Tells whether we should run /usr/bin/ubuntu-advantage instead of using
    # Mock objects.
    pro_magic_attach_run_locally: bool = False
    # When running /usr/bin/ubuntu-advantage locally, do not use the production
    # ua-contrats.
    pro_ua_contracts_url: str = "https://contracts.staging.canonical.com"

    @classmethod
    def load(cls, stream):
        data = yaml.safe_load(stream)
        return cls(**data)
