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

import json
import logging
import os
import shlex
import sys

from subiquitycore.controller import BaseController
from subiquitycore.ssh import host_key_info, get_ips_standalone
from subiquitycore.utils import disable_console_conf, run_command

from console_conf.ui.views import IdentityView, LoginView

log = logging.getLogger('console_conf.controllers.identity')


def get_core_version():
    """ For a ubuntu-core system, return its version or None """

    path = "/usr/lib/os-release"
    try:
        with open(path, "r") as fp:
            content = fp.read()
    except FileNotFoundError:
        return None

    version = None
    for line in shlex.split(content):
        key, _, value = line.partition("=")
        if key == "ID" and value != "ubuntu-core":
            return None
        if key == "VERSION_ID":
            version = value
            break

    return version


def get_device_owner():
    """ Check if device is owned """

    # TODO: use proper snap APIs.
    try:
        extrausers_fp = open('/var/lib/extrausers/passwd', 'r')
    except FileNotFoundError:
        return None
    with extrausers_fp:
        passwd_line = extrausers_fp.readline()
        if passwd_line and len(passwd_line) > 0:
            passwd = passwd_line.split(':')
            result = {
                'realname': passwd[4].split(',')[0],
                'username': passwd[0],
                'homedir': passwd[5],
                }
            return result
    return None


login_details_tmpl = """\
Ubuntu Core {version} on {first_ip} ({tty_name})
{host_key_info}

To login:
{sshcommands}
Personalize your account at https://login.ubuntu.com.
"""


login_details_tmpl_no_ip = """\
Ubuntu Core {version} on <no ip address> ({tty_name})

You cannot log in until the system has an IP address. (Is there
supposed to be a DHCP server running on your network?)

Personalize your account at https://login.ubuntu.com.
"""


def write_login_details(fp, username, ips):
    sshcommands = "\n"
    for ip in ips:
        sshcommands += "    ssh %s@%s\n" % (username, ip)
    tty_name = os.ttyname(0)[5:]  # strip off the /dev/
    version = get_core_version() or "16"
    if len(ips) == 0:
        fp.write(login_details_tmpl_no_ip.format(
            sshcommands=sshcommands, tty_name=tty_name, version=version))
    else:
        first_ip = ips[0]
        fp.write(login_details_tmpl.format(sshcommands=sshcommands,
                                           host_key_info=host_key_info(),
                                           tty_name=tty_name,
                                           first_ip=first_ip,
                                           version=version))


def write_login_details_standalone():
    owner = get_device_owner()
    if owner is None:
        print("No device owner details found.")
        return 0
    ips = get_ips_standalone()
    if len(ips) == 0:
        tty_name = os.ttyname(0)[5:]
        version = get_core_version() or "16"
        print(login_details_tmpl_no_ip.format(tty_name=tty_name,
                                              version=version))
        return 2
    write_login_details(sys.stdout, owner['username'], ips)
    return 0


class IdentityController(BaseController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.identity

    def start_ui(self):
        self.ui.set_body(IdentityView(self.model, self))
        device_owner = get_device_owner()
        if device_owner is not None:
            self.model.add_user(device_owner)
            key_file = os.path.join(device_owner['homedir'],
                                    ".ssh/authorized_keys")
            self.model.user.fingerprints = (
                run_command(['ssh-keygen', '-lf',
                             key_file]).stdout.replace('\r', '').splitlines())
            self.login()

    def identity_done(self, email):
        if self.opts.dry_run:
            result = {
                'realname': email,
                'username': email,
                }
            self.model.add_user(result)
            login_details_path = '.subiquity/login-details.txt'
        else:
            self.app.urwid_loop.draw_screen()
            cp = run_command(
                ["snap", "create-user", "--sudoer", "--json", email])
            if cp.returncode != 0:
                if isinstance(self.ui.body, IdentityView):
                    self.ui.body.snap_create_user_failed(
                        "Creating user failed:", cp.stderr)
                return
            else:
                data = json.loads(cp.stdout)
                result = {
                    'realname': email,
                    'username': data['username'],
                    }
                os.makedirs('/run/console-conf', exist_ok=True)
                login_details_path = '/run/console-conf/login-details.txt'
                self.model.add_user(result)
        ips = []
        net_model = self.app.base_model.network
        for dev in net_model.get_all_netdevs():
            ips.extend(dev.actual_global_ip_addresses)
        with open(login_details_path, 'w') as fp:
            write_login_details(fp, result['username'], ips)
        self.login()

    def cancel(self):
        # You can only go back if we haven't created a user yet.
        if self.model.user is None:
            self.app.prev_screen()

    def login(self):
        title = "Configuration Complete"
        self.ui.set_header(title)

        net_model = self.app.base_model.network
        ifaces = net_model.get_all_netdevs()
        login_view = LoginView(self.opts, self.model, self, ifaces)
        login_view._w.focus_position = 2

        self.ui.set_body(login_view)

    def login_done(self):
        if not self.opts.dry_run:
            # stop the console-conf services (this will kill the
            # current process).
            disable_console_conf()

        self.app.exit()
