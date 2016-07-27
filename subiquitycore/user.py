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

from subiquitycore import utils


log = logging.getLogger("subiquitycore.user")


def create_user(userinfo, dryrun=False):
    """Create a user according to the information in userinfo."""
    usercmds = []
    # FIXME: snappy needs --extrausers too; should factor out a way to pass
    #        additional parameters.
    usercmds += ["useradd -m -p {confirm_password} {username}".format(**userinfo)]
    if 'ssh_import_id' in userinfo:
        target = "/home/{username}/.ssh/authorized_keys".format(**userinfo)
        userinfo.update({'target': target})
        ssh_id = userinfo.get('ssh_import_id')
        if ssh_id.startswith('sso'):
            log.info('call out to SSO login')
        else:
            ssh_import_id = "ssh-import-id -o "
            ssh_import_id += "{target} {ssh_import_id}".format(**userinfo)
            usercmds += [ssh_import_id]

    if not dryrun:
        # TODO(mwhudson): cmd.split? really? what if the password contains a space?
        for cmd in usercmds:
            utils.run_command(cmd.split(), shell=False)

        # always run chown last
        homedir = '/home/{username}'.format(**userinfo)
        retries = 10
        while not os.path.exists(homedir) and retries > 0:
            log.debug('waiting on homedir')
            retries -= 1
            time.sleep(0.2)

        if retries <= 0:
            raise ValueError('Failed to create homedir')

        chown = "chown {username}.{username} -R /home/{username}".format(**userinfo)
        utils.run_command(chown.split(), shell=False)

        # add sudo rule
        with open('/etc/sudoers.d/firstboot-user', 'w') as fh:
            fh.write('# firstboot config added user\n\n')
            fh.write('{username} ALL=(ALL) NOPASSWD:ALL\n'.format(**userinfo))
    else:
        log.info('dry-run, skiping user configuration')
