# Copyright 2016 Canonical, Ltd.
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
import os
import time

from subiquitycore.utils import run_command


log = logging.getLogger("subiquitycore.user")


def create_user(userinfo, dryrun=False, extra_args=[]):
    """Create a user according to the information in userinfo."""
    usercmds = []
    username = userinfo['username']

    useradd = ["useradd", "-m", "-p", userinfo['confirm_password'], username] + extra_args
    usercmds.append(useradd)
    if 'ssh_import_id' in userinfo:
        target = "/home/{}/.ssh/authorized_keys".format(username)
        ssh_id = userinfo['ssh_import_id']
        if ssh_id.startswith('sso'):
            log.info('call out to SSO login')
        else:
            ssh_import_id = ["ssh-import-id", "-o", target, ssh_id]
            usercmds.append(ssh_import_id)

    if not dryrun:
        for cmd in usercmds:
            # TODO(mwhudson): Check return value!
            run_command(cmd, shell=False)

        # always run chown last
        homedir = '/home/' + username
        retries = 10
        while not os.path.exists(homedir) and retries > 0:
            log.debug('waiting on homedir')
            retries -= 1
            time.sleep(0.2)

        if retries <= 0:
            raise ValueError('Failed to create homedir')

        chown = ["chown", "{0}.{0}".format(username), "-R", homedir]
        # TODO(mwhudson): Check return value!
        run_command(chown, shell=False)

        # add sudo rule
        with open('/etc/sudoers.d/installer-user', 'w') as fh:
            fh.write('# installer added user\n\n')
            fh.write('{} ALL=(ALL) NOPASSWD:ALL\n'.format(username))
    else:
        log.info('dry-run, skipping user configuration')
