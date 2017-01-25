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

import crypt
import errno
import logging
import os
import random
import yaml
from subprocess import Popen, PIPE

log = logging.getLogger("subiquitycore.utils")
SYS_CLASS_NET = "/sys/class/net/"


def environment_check(check):
    ''' Check the environment to ensure subiquity can run without issues.
    '''
    log.info('Checking environment for installer requirements...')

    def is_file(x):
        return os.path.isfile(x)

    def is_directory(x):
        return os.path.isdir(x)

    def is_mount(x):
        return os.path.ismount(x)

    def is_writable(x):
        return os.access(x, os.W_OK)

    def is_readable(x):
        return os.access(x, os.R_OK)

    def is_executable(x):
        return os.access(x, os.X_OK)

    check_map = {
        'read': is_readable,
        'write': is_writable,
        'exec': is_executable,
        'file': is_file,
        'directory': is_directory,
        'mount': is_mount,
    }

    checks = yaml.safe_load(check).get('checks', None)
    if not checks:
        log.error('Invalid environment check configuration')
        return False

    env_ok = True
    for check_type in [c for c in checks
                       if c in ['read', 'write', 'mount', 'exec']]:
        for ftype, items in checks[check_type].items():
            for i in items:
                if not os.path.exists(i):
                    log.error('FAIL: {} is not found on the'
                              ' filesystem'.format(i))
                    env_ok = False
                    continue
                if check_map[ftype](i) is False:
                    log.error('FAIL: {} is NOT of type: {}'.format(i, ftype))
                    env_ok = False
                    continue
                if check_map[check_type](i) is False:
                    log.error('FAIL: {} does NOT have required attr:'
                              ' {}'.format(i, check_type))
                    env_ok = False

    return env_ok


def run_command_start(command, timeout=None, shell=False):
    log.debug('run_command called: {}'.format(command))
    cmd_env = os.environ.copy()
    # set consistent locale
    cmd_env['LC_ALL'] = 'C'
    if timeout:
        command = "timeout %ds %s" % (timeout, command)

    try:
        log.debug('trying Popen...')
        # dummy stdin fd as per:
        # http://stackoverflow.com/ +
        # questions/27022810/urwid-watch-file-blocks-keypress
        r, w = os.pipe()
        p = Popen(command, shell=shell,
                  stdin=r, stdout=PIPE, stderr=PIPE,
                  bufsize=-1, env=cmd_env, close_fds=True)
        os.close(w)
    except OSError as e:
        if e.errno == errno.ENOENT:
            log.debug('error!')
            return dict(ret=127, output="", err="")
        else:
            log.debug('error raise!')
            raise e
    return p


def run_command_summarize(p, stdout, stderr):
    if p.returncode == 126 or p.returncode == 127:
        stdout = bytes()
    if not stderr:
        stderr = bytes()
    rv = dict(status=p.returncode,
              output=stdout.decode('utf-8'),
              err=stderr.decode('utf-8'))
    log.debug('run_command returning: {}'.format(rv))
    return rv


def run_command(command, timeout=None, shell=False):
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
    p = run_command_start(command, timeout, shell)
    log.debug('calling communicate()')
    if isinstance(p, dict): # only in error cases
        return p
    stdout, stderr = p.communicate()
    return run_command_summarize(p, stdout, stderr)


# FIXME: replace with passlib and update package deps
def crypt_password(passwd, algo='SHA-512'):
    # encryption algo - id pairs for crypt()
    algos = {'SHA-512': '$6$', 'SHA-256': '$5$', 'MD5': '$1$', 'DES': ''}
    if algo not in algos:
        raise Exception('Invalid algo({}), must be one of: {}. '.format(
            algo, ','.join(algos.keys())))

    salt_set = ('abcdefghijklmnopqrstuvwxyz'
                'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                '0123456789./')
    salt = 16 * ' '
    salt = ''.join([random.choice(salt_set) for c in salt])
    return crypt.crypt(passwd, algos[algo] + salt)


def disable_console_conf():
    """ Stop console-conf service; which also restores getty service """
    log.info('disabling console-conf service')
    run_command(["systemctl", "stop", "--no-block", "console-conf@*.service", "serial-console-conf@*.service"])
    return

def disable_subiquity():
    """ Stop subiquity service; which also restores getty service """
    log.info('disabling subiquity service')
    run_command(["mkdir", "-p", "/run/subiquity"])
    run_command(["touch", "/run/subiquity/complete"])
    run_command(["systemctl", "stop", "--no-block", "subiquity*.service"])
    return
