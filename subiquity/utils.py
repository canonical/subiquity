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

import os
from subprocess import Popen, PIPE
from subiquity.async import Async
import errno
import logging

log = logging.getLogger("subiquity.utils")
SYS_CLASS_NET = "/sys/class/net/"


def run_command_async(cmd, timeout=None):
    return Async.pool.submit(run_command, cmd, timeout)


def run_command(command, timeout=None):
    """ Execute command through system shell
    :param command: command to run
    :param timeout: (optional) use 'timeout' to limit time. default 300
    :type command: str
    :returns: {status: returncode, output: stdout, err: stderr}
    :rtype: dict
    .. code::
        # Get output of juju status
        cmd_dict = utils.get_command_output('juju status')
    """
    cmd_env = os.environ.copy()
    # set consistent locale
    cmd_env['LC_ALL'] = 'C'
    if timeout:
        command = "timeout %ds %s" % (timeout, command)

    try:
        p = Popen(command, shell=True,
                  stdout=PIPE, stderr=PIPE,
                  bufsize=-1, env=cmd_env, close_fds=True)
    except OSError as e:
        if e.errno == errno.ENOENT:
            return dict(ret=127, output="", err="")
        else:
            raise e
    stdout, stderr = p.communicate()
    if p.returncode == 126 or p.returncode == 127:
        stdout = bytes()
    if not stderr:
        stderr = bytes()
    return dict(status=p.returncode,
                output=stdout.decode('utf-8'),
                err=stderr.decode('utf-8'))


def sys_dev_path(devname, path=""):
    return SYS_CLASS_NET + devname + "/" + path


def read_sys_net(devname, path, translate=None, enoent=None, keyerror=None):
    try:
        contents = ""
        with open(sys_dev_path(devname, path), "r") as fp:
            contents = fp.read().strip()
        if translate is None:
            return contents

        try:
            return translate.get(contents)
        except KeyError:
            log.debug("found unexpected value '%s' in '%s/%s'", contents,
                      devname, path)
            if keyerror is not None:
                return keyerror
            raise
    except OSError as e:
        if e.errno == errno.ENOENT and enoent is not None:
            return enoent
        raise
