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
import pwd
import sys

from subiquitycore.controller import BaseController
from subiquitycore.models import IdentityModel
from subiquitycore.snapd import SnapdConnection
from subiquitycore.utils import disable_console_conf, run_command

from console_conf.ui.views import IdentityView, LoginView

log = logging.getLogger('console_conf.controllers.identity')


def get_managed():
    """ Check if device is managed """
    con = SnapdConnection('', '/run/snapd.socket')
    return con.get('v2/system-info').json()['result']['managed']


def get_realname(username):
    try:
        info = pwd.getpwnam(username)
    except KeyError:
        return ''
    return info.pw_gecos.split(',', 1)[0]


def get_device_owner():
    """ Get device owner, if any """
    con = SnapdConnection('', '/run/snapd.socket')
    for user in con.get('v2/users').json()['result']:
        if 'username' not in user:
            continue
        username = user['username']
        homedir = '/home/' + username
        if os.path.isdir(homedir):
            return {
                'username': username,
                'realname': get_realname(username),
                'homedir': homedir,
                }
    return None

def host_key_fingerprints():
    """Query sshd to find the host keys and then fingerprint them.

    Returns a sequence of (key-type, fingerprint) pairs.
    """
    config = run_command(['sshd', '-T'])
    if config['status'] != 0:
        log.debug("sshd -T failed %r", config['err'])
        return []
    keyfiles = []
    for line in config['output'].splitlines():
        if line.startswith('hostkey '):
            keyfiles.append(line.split(None, 1)[1])
    info = []
    for keyfile in keyfiles:
        result = run_command(['ssh-keygen', '-lf', keyfile])
        if result['status'] != 0:
            log.debug("ssh-keygen -lf %s failed %r", keyfile, result['err'])
            continue
        parts = result['output'].strip().split()
        length, fingerprint, host, keytype = parts
        keytype = keytype.strip('()')
        info.append((keytype, fingerprint))
    return info


host_keys_intro = """
The host key fingerprints are:

"""

host_key_tmpl = """\
    {keytype:{width}} {fingerprint}
"""

single_host_key_tmpl = """\
The {keytype} host key fingerprints is:
    {fingerprint}
"""


def host_key_info():
    fingerprints = host_key_fingerprints()
    if len(fingerprints) == 1:
        [(keytype, fingerprint)] = fingerprints
        return single_host_key_tmpl.format(keytype=keytype, fingerprint=fingerprint)
    lines = [host_keys_intro]
    longest_type = max([len(keytype) for keytype, _ in fingerprints])
    for keytype, fingerprint in fingerprints:
        lines.append(host_key_tmpl.format(keytype=keytype, fingerprint=fingerprint, width=longest_type))
    return "".join(lines)

login_details_tmpl = """\
Ubuntu Core 16 on {first_ip} ({tty_name})
{host_key_info}
To login:
{sshcommands}
Personalize your account at https://login.ubuntu.com.
"""

login_details_tmpl_no_ip = """\
Ubuntu Core 16 on <no ip address> ({tty_name})

You cannot log in until the system has an IP address. (Is there
supposed to be a DHCP server running on your network?)

Personalize your account at https://login.ubuntu.com.
"""

def write_login_details(fp, username, ips):
    sshcommands = "\n"
    for ip in ips:
        sshcommands += "    ssh %s@%s\n"%(username, ip)
    tty_name = os.ttyname(0)[5:] # strip off the /dev/
    if len(ips) == 0:
        fp.write(login_details_tmpl_no_ip.format(
            sshcommands=sshcommands, tty_name=tty_name))
    else:
        first_ip = ips[0]
        fp.write(login_details_tmpl.format(
            sshcommands=sshcommands, host_key_info=host_key_info(), tty_name=tty_name, first_ip=first_ip))

def write_login_details_standalone():
    owner = get_device_owner()
    from probert import network
    from subiquitycore.models.network import NETDEV_IGNORED_IFACE_NAMES, NETDEV_IGNORED_IFACE_TYPES
    import operator
    observer = network.UdevObserver()
    observer.start()
    ips = []
    for l in sorted(observer.links.values(), key=operator.attrgetter('name')):
        if l.type in NETDEV_IGNORED_IFACE_TYPES:
            continue
        if l.name in NETDEV_IGNORED_IFACE_NAMES:
            continue
        for _, addr in sorted(l.addresses.items()):
            if addr.scope == "global":
                ips.append(addr.ip)
    if len(ips) == 0:
        if owner is None:
            print("device managed without user")
            return 2
        else:
            tty_name = os.ttyname(0)[5:]
            print("Ubuntu Core 16 on <no ip address> ({})".format(tty_name))
            print()
            print("You cannot log in until the system has an IP address.")
            print("(Is there supposed to be a DHCP server running on your network?)")
            return 2
    if owner is None:
        print("device managed without user @ {}".format(', '.join(ips)))
    else:
        write_login_details(sys.stdout, owner['username'], ips)
    return 0


class IdentityController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = IdentityModel(self.opts)

    def default(self):
        title = "Profile setup"
        excerpt = "Enter an email address from your account in the store."
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 40)
        self.ui.set_body(IdentityView(self.model, self, self.opts, self.loop))
        device_owner = get_device_owner()
        if get_managed():
            device_owner = get_device_owner()
            if device_owner:
                self.model.add_user(device_owner)
                key_file = os.path.join(device_owner['homedir'],
                                        ".ssh/authorized_keys")
                cp = run_command(['ssh-keygen', '-lf', key_file])
                self.model.user.fingerprints = (
                    cp.stdout.replace('\r', '').splitlines())
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
            self.ui.frame.body.progress.set_text("Contacting store...")
            self.loop.draw_screen()
            result = run_command(["snap", "create-user", "--sudoer", "--json", email])
            self.ui.frame.body.progress.set_text("")
            if result['status'] != 0:
                self.ui.frame.body.error.set_text("Creating user failed:\n" + result['err'])
                return
            else:
                data = json.loads(result['output'])
                result = {
                    'realname': email,
                    'username': data['username'],
                    }
                os.makedirs('/run/console-conf', exist_ok=True)
                login_details_path = '/run/console-conf/login-details.txt'
                self.model.add_user(result)
        ips = []
        net_model = self.controllers['Network'].model
        for dev in net_model.get_all_netdevs():
            ips.extend(dev.actual_global_ip_addresses)
        with open(login_details_path, 'w') as fp:
            write_login_details(fp, result['username'], ips)
        self.login()

    def cancel(self):
        # You can only go back if we haven't created a user yet.
        if self.model.user is None:
            self.signal.emit_signal('prev-screen')

    def login(self):
        title = "Configuration Complete"
        footer = "View configured user and device access methods"
        self.ui.set_header(title)
        self.ui.set_footer(footer)

        net_model = self.controllers['Network'].model
        ifaces = net_model.get_all_netdevs()
        login_view = LoginView(self.opts, self.model, self, ifaces)

        self.ui.set_body(login_view)

    def login_done(self):
        if not self.opts.dry_run:
            # stop the console-conf services (this will kill the current process).
            disable_console_conf()

        self.signal.emit_signal('quit')
