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

from typing import List, Optional, TypedDict

import attr
import yaml


class DryRunController:
    def __init__(self, app):
        self.app = app
        self.context = app.context.child("DryRun")

    async def crash_GET(self) -> None:
        1 / 0


class KnownMirror(TypedDict, total=False):
    """Dictionary type hints for a known mirror. Either url or pattern should
    be specified."""

    url: str
    pattern: str

    strategy: str


class SSHImport(TypedDict, total=True):
    """Dictionary type hints for a SSH key import."""

    strategy: str
    username: str


@attr.s(auto_attribs=True)
class DRConfig:
    """Configuration for dry-run-only executions.
    All variables here should have default values ; to indicate the behavior we
    want by default in dry-run mode."""

    # Tells whether "$source"/var/lib/snapd/seed/systems exists on the source.
    systems_dir_exists: bool = False
    # Tells whether we should run /usr/bin/ubuntu-advantage instead of using
    # Mock objects.
    pro_magic_attach_run_locally: bool = False
    # When running /usr/bin/ubuntu-advantage locally, do not use the production
    # ua-contrats.
    pro_ua_contracts_url: str = "https://contracts.staging.canonical.com"

    apt_mirror_check_default_strategy: str = "run-on-host"
    apt_mirrors_known: List[KnownMirror] = [
        {"pattern": r"https?://archive\.ubuntu\.com/ubuntu/?", "strategy": "success"},
        {
            "pattern": r"https?://[a-z]{2,}\.archive\.ubuntu\.com/ubuntu/?",
            "strategy": "success",
        },
        {"pattern": r"/success/?$", "strategy": "success"},
        {"pattern": r"/rand(om)?/?$", "strategy": "random"},
        {"pattern": r"/host/?$", "strategy": "run-on-host"},
        {"pattern": r"/fail(ed)?/?$", "strategy": "failure"},
    ]

    ssh_import_default_strategy: str = "run-on-host"
    ssh_imports: List[SSHImport] = [
        {"username": "heracles", "strategy": "success"},
        {"username": "sisyphus", "strategy": "failure"},
    ]

    # If running ubuntu-drivers on the host, supply a file to
    # umockdev-wrapper.py
    ubuntu_drivers_run_on_host_umockdev: Optional[
        str
    ] = "examples/umockdev/dell-certified+nvidia.yaml"

    @classmethod
    def load(cls, stream):
        data = yaml.safe_load(stream)
        return cls(**data)
