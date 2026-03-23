# Copyright 2026 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import tempfile
import unittest
from unittest import mock

import apport

from subiquity.common.errorreport import ErrorReport


class TestErrorReport(unittest.TestCase):
    def test_collect_filtered_journal(self):
        # This is more an integration test than a unit-test.
        unfiltered = """
Mar 23 14:21:16 ubuntu-server subiquity_event.1591[1591]: final system configuration
Mar 23 14:21:16 ubuntu-server systemd[1]: Started run-u50.service - /snap/subiquity/x1/usr/bin/python3.12 -m curtin --showtrace -vvv --set "json:reporting={\"subiquity\": {\"type\": \"journald\", \"identifier\": \"curtin_event.1591.9\"}}" in-target -t /target -- useradd johndoe --comment "john doe" --shell /bin/bash --groups adm,cdrom,dip,plugdev,sudo,users --create-home.
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: start: cmd-in-target: curtin command in-target
Mar 23 14:21:16 ubuntu-server curtin_event.1591.9[10757]: start: cmd-in-target: curtin command in-target
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/dev', '/target/dev'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/proc', '/target/proc'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/run', '/target/run'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/sys', '/target/sys'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/sys/firmware/efi/efivars', '/target/sys/firmware/efi/efivars'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/target/usr/bin/true', '/target/usr/bin/ischroot'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['unshare', '--help'] with allowed return codes [0] (capture=True)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Checking if target_proc (/target/proc) is a mount
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: It is, so unshare will use --mount-proc=/target/proc
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['unshare', '--fork', '--pid', '--mount-proc=/target/proc', '--', 'chroot', '/target', 'useradd', 'johndoe', '--comment', 'john doe', '--shell', '/bin/bash', '--groups', 'adm,cdrom,dip,plugdev,sudo,users', '--create-home'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server useradd[10781]: new group: name=johndoe, GID=1000
Mar 23 14:21:16 ubuntu-server useradd[10781]: new user: name=johndoe, UID=1000, GID=1000, home=/home/johndoe, shell=/bin/bash, from=none
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to group 'adm'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to group 'cdrom'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to group 'sudo'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to group 'dip'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to group 'plugdev'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to group 'users'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to shadow group 'adm'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to shadow group 'cdrom'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to shadow group 'sudo'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to shadow group 'dip'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to shadow group 'plugdev'
Mar 23 14:21:16 ubuntu-server useradd[10781]: add 'johndoe' to shadow group 'users'
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['udevadm', 'settle'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_event.1591[1591]:  curtin command in-target
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: TIMED subp(['udevadm', 'settle']): 0.004
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--make-private', '/target/usr/bin/ischroot'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['umount', '/target/usr/bin/ischroot'] with allowed return codes [0] (capture=False)
"""  # noqa
        expected_filtered = """
Mar 23 14:21:16 ubuntu-server subiquity_event.1591[1591]: final system configuration
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: start: cmd-in-target: curtin command in-target
Mar 23 14:21:16 ubuntu-server curtin_event.1591.9[10757]: start: cmd-in-target: curtin command in-target
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/dev', '/target/dev'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/proc', '/target/proc'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/run', '/target/run'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/sys', '/target/sys'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/sys/firmware/efi/efivars', '/target/sys/firmware/efi/efivars'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--bind', '/target/usr/bin/true', '/target/usr/bin/ischroot'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['unshare', '--help'] with allowed return codes [0] (capture=True)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Checking if target_proc (/target/proc) is a mount
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: It is, so unshare will use --mount-proc=/target/proc
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['udevadm', 'settle'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_event.1591[1591]:  curtin command in-target
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: TIMED subp(['udevadm', 'settle']): 0.004
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['mount', '--make-private', '/target/usr/bin/ischroot'] with allowed return codes [0] (capture=False)
Mar 23 14:21:16 ubuntu-server subiquity_log.1591[10757]: Running command ['umount', '/target/usr/bin/ischroot'] with allowed return codes [0] (capture=False)
"""  # noqa
        orig_recent_syslog = apport.hookutils.recent_syslog

        def fake_recent_syslog(*args, **kwargs) -> str:
            if "path" in kwargs:
                kwargs.pop("path")
            with tempfile.NamedTemporaryFile(
                mode="w", delete=True, delete_on_close=False, encoding="utf-8"
            ) as journal_file:
                journal_file.write(unfiltered)
                journal_file.close()
                # Instead of reading from the journal, read from the specified file.
                return orig_recent_syslog(*args, path=journal_file.name, **kwargs)

        with mock.patch(
            "subiquity.common.errorreport.apport.hookutils.recent_syslog",
            autospec=True,
            wraps=fake_recent_syslog,
        ):
            collected = ErrorReport.collect_filtered_journal()
            self.assertEqual(expected_filtered, collected)
