# Copyright 2015 Canonical, Ltd.
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

import subprocess
from subiquity.async import Async
import shlex
import logging

log = logging.getLogger("subiquity.utils")


def run_command_async(cmd, streaming_callback=None):
    return Async.pool.submit(run_command, cmd, streaming_callback)


def run_command(cmd, streaming_callback=None):
    """ Executes `cmd` sending its output to `streaming_callback`
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    log.debug("Running command: {}".format(cmd))
    proc = subprocess.Popen(cmd, close_fds=True,
                            stdout=streaming_callback)
    proc.kill()
    # streaming_callback.close()
