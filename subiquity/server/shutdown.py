# Copyright 2025 Canonical, Ltd.
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

import logging

from subiquitycore.utils import arun_command

log = logging.getLogger("subiquity.server.shutdown")


# On desktop, a systemd inhibitor is in place to block shutdown.  Starting with
# systemd 257, the inhibitor also prevents the root user from shutting down
# unless the --check-inhibitors=no, --ignore-inhibitors, or the --force option
# is used.  See LP: #2092438


async def initiate_reboot() -> None:
    await arun_command(["systemctl", "reboot", "--ignore-inhibitors"])


async def initiate_poweroff() -> None:
    await arun_command(["systemctl", "poweroff", "--ignore-inhibitors"])
