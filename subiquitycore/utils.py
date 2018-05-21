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
import subprocess

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
                    if 'SNAP' in os.environ:
                        log.warn("Adjusting path for snaps: {}".format(os.environ.get('SNAP')))
                        i = os.environ.get('SNAP') + i
                        if not os.path.exists(i):
                            env_ok = False
                    else:
                        env_ok = False

                    if not env_ok:
                        log.error('FAIL: {} is not found on the'
                                  ' filesystem'.format(i))
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


def _clean_env(env):
    if env is None:
        env = os.environ.copy()
    else:
        env = env.copy()
    # Do we always want to do this?
    env['LC_ALL'] = 'C'
    # Maaaybe want to remove SNAP here too.
    return env


def run_command(cmd, *, input=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace', env=None, **kw):
    """A wrapper around subprocess.run with logging and different defaults.

    We never ever want a subprocess to inherit our file descriptors!
    """
    if input is None:
        kw['stdin'] = subprocess.DEVNULL
    else:
        input = input.encode(encoding)
    log.debug("run_command called: %s", cmd)
    try:
        cp = subprocess.run(cmd, input=input, stdout=stdout, stderr=stderr, env=_clean_env(env), **kw)
        if encoding:
            if isinstance(cp.stdout, bytes):
                cp.stdout = cp.stdout.decode(encoding)
            if isinstance(cp.stderr, bytes):
                cp.stderr = cp.stderr.decode(encoding)
    except subprocess.CalledProcessError as e:
        log.debug("run_command %s", str(e))
        raise
    else:
        log.debug("run_command %s exited with code %s", cp.args, cp.returncode)
        return cp


def start_command(cmd, *, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace', env=None, **kw):
    """A wrapper around subprocess.Popen with logging and different defaults.

    We never ever want a subprocess to inherit our file descriptors!
    """
    log.debug('start_command called: %s', cmd)
    return subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr, env=_clean_env(env), **kw)


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
    run_command(["systemctl", "start", "--no-block", "getty@tty1.service"])
    run_command(["systemctl", "stop", "--no-block", "snap.subiquity.subiquity-service.service", "serial-subiquity@*.service"])
    return
