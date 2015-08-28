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

import errno
import subprocess
import os
import codecs
import pty
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
    stdoutm, stdouts = pty.openpty()
    proc = subprocess.Popen(cmd,
                            stdout=stdouts,
                            stderr=subprocess.PIPE)
    os.close(stdouts)
    decoder = codecs.getincrementaldecoder('utf-8')()

    def last_ten_lines(s):
            chunk = s[-1500:]
            lines = chunk.splitlines(True)
            return ''.join(lines[-10:]).replace('\r', '')

    decoded_output = ""
    try:
        while proc.poll() is None:
            try:
                b = os.read(stdoutm, 512)
            except OSError as e:
                if e.errno != errno.EIO:
                    raise
                break
            else:
                final = False
                if not b:
                    final = True
                decoded_chars = decoder.decode(b, final)
                if decoded_chars is None:
                    continue

                decoded_output += decoded_chars
                if streaming_callback:
                    ls = last_ten_lines(decoded_output)

                    streaming_callback(ls)
                if final:
                    break
    finally:
        os.close(stdoutm)
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    errors = [l.decode('utf-8') for l in proc.stderr.readlines()]
    if streaming_callback:
        streaming_callback(last_ten_lines(decoded_output))

    errors = ''.join(errors)

    if proc.returncode == 0:
        return decoded_output.strip()
    else:
        log.debug("Error with command: "
                  "[Output] '{}' [Error] '{}'".format(
                      decoded_output.strip(),
                      errors.strip()))
        raise Exception("Problem running command: [Error] '{}'".format(
            errors.strip()))
