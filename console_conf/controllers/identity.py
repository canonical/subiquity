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

import logging
import os
import pwd
import shlex
import sys

from console_conf.ui.views import IdentityView, LoginView
from subiquitycore import snap
from subiquitycore.snapd import SnapdConnection
from subiquitycore.ssh import get_ips_standalone, host_key_info
from subiquitycore.tuicontroller import TuiController
from subiquitycore.utils import disable_console_conf

log = logging.getLogger("console_conf.controllers.identity")


def get_core_version():
    """For a ubuntu-core system, return its version or None"""

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


def get_managed(con):
    """Check if device is managed"""
    return con.get("v2/system-info").json()["result"]["managed"]


def get_realname(username):
    try:
        info = pwd.getpwnam(username)
    except KeyError:
        return ""
    return info.pw_gecos.split(",", 1)[0]


def get_device_owner(con):
    """Get device owner, if any"""
    for user in con.get("v2/users").json()["result"]:
        if "username" not in user:
            continue
        username = user["username"]
        homedir = "/home/" + username
        if os.path.isdir(homedir):
            return {
                "username": username,
                "realname": get_realname(username),
                "homedir": homedir,
            }
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


def write_login_details(fp, username, ips, state_dir=None):
    sshcommands = "\n"
    for ip in ips:
        sshcommands += "    ssh %s@%s\n" % (username, ip)
    tty_name = os.ttyname(0)[5:]  # strip off the /dev/
    version = get_core_version() or "16"
    if len(ips) == 0:
        fp.write(
            login_details_tmpl_no_ip.format(
                sshcommands=sshcommands, tty_name=tty_name, version=version
            )
        )
    else:
        first_ip = ips[0]
        key_info = host_key_info(runtime_state_dir=state_dir)
        fp.write(
            login_details_tmpl.format(
                sshcommands=sshcommands,
                host_key_info=key_info,
                tty_name=tty_name,
                first_ip=first_ip,
                version=version,
            )
        )


def write_login_details_standalone():
    # running in standalone mode
    con = SnapdConnection("/", "/run/snapd.socket")
    owner = get_device_owner(con)
    ips = get_ips_standalone()
    if len(ips) == 0:
        if owner is None:
            print("device managed without user")
            return 2
        else:
            tty_name = os.ttyname(0)[5:]
            version = get_core_version() or "16"
            print(login_details_tmpl_no_ip.format(tty_name=tty_name, version=version))
            return 2
    if owner is None:
        print("device managed without user @ {}".format(", ".join(ips)))
    else:
        if snap.is_snap() and snap.is_snap_strictly_confined():
            # normally this is set by the application context, but here we are
            # executing standalone
            runtime_state = os.path.join("/run", snap.snap_name())
        else:
            runtime_state = None
        write_login_details(sys.stdout, owner["username"], ips, state_dir=runtime_state)
    return 0


class IdentityController(TuiController):
    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.identity

    def make_ui(self):
        if get_managed(self.app.snapdcon):
            device_owner = get_device_owner(self.app.snapdcon)
            if device_owner:
                self.model.add_user(device_owner)
            return self.make_login_view()
        else:
            return IdentityView(self.model, self)

    def identity_done(self, email):
        if self.opts.dry_run:
            result = {
                "realname": email,
                "username": email,
            }
            self.model.add_user(result)
            login_details_path = self.opts.output_base + "/login-details.txt"
        else:
            self.app.urwid_loop.draw_screen()
            user_action = {"action": "create", "email": email, "sudoer": True}
            res = self.app.snapdcon.post("v2/users", body=user_action)
            if res.json()["status"] != "OK":
                if isinstance(self.ui.body, IdentityView):
                    self.ui.body.snap_create_user_failed(
                        "Creating user failed:", res.json()["result"]["message"]
                    )
                return
            else:
                username = res.json()["result"][0]["username"]
                result = {
                    "realname": email,
                    "username": username,
                }
                login_details_path = self.app.state_path("login-details.txt")
                self.model.add_user(result)
        ips = []
        net_model = self.app.base_model.network
        for dev in net_model.get_all_netdevs():
            ips.extend(dev.actual_global_ip_addresses)
        with open(login_details_path, "w") as fp:
            write_login_details(
                fp, result["username"], ips, state_dir=self.app.state_dir
            )
        self.login()

    def cancel(self):
        # You can only go back if we haven't created a user yet.
        if self.model.user is None:
            self.app.prev_screen()

    def make_login_view(self):
        title = "Configuration Complete"
        self.ui.set_header(title)

        net_model = self.app.base_model.network
        ifaces = net_model.get_all_netdevs()
        login_view = LoginView(self.opts, self.model, self, ifaces)
        login_view._w.focus_position = 2
        return login_view

    def login(self):
        self.ui.set_body(self.make_login_view())

    def login_done(self):
        if not self.opts.dry_run:
            # stop the console-conf services (this will kill the
            # current process).
            disable_console_conf()

        self.app.exit()
