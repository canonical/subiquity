# Copyright 2021 Canonical, Ltd.
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
import tempfile

from curtin.util import write_file

from subiquitycore.lsb_release import lsb_release

from subiquity.server.curtin import run_curtin_command


async def mount(runner, device, mountpoint, options=None, type=None):
    opts = []
    if options is not None:
        opts.extend(['-o', options])
    if type is not None:
        opts.extend(['-t', type])
    await runner.run(['mount'] + opts + [device, mountpoint])


async def unmount(runner, mountpoint):
    await runner.run(['umount', mountpoint])


async def setup_overlay(runner, dir):
    tdir = tempfile.mkdtemp()
    w = f'{tdir}/work'
    u = f'{tdir}/upper'
    for d in w, u:
        os.mkdir(d)
    await mount(
        runner, 'overlay', dir, type='overlay',
        options=f'lowerdir={dir},upperdir={u},workdir={w}')


async def configure_apt(app, context, config_location):
    # Configure apt so that installs from the pool on the cdrom are
    # preferred during installation but not in the installed system.
    #
    # This has a few steps.
    #
    # 1. As the remaining steps mean that any changes to apt configuration
    #    are do not persist into the installed system, we get curtin to
    #    configure apt a bit earlier than it would by default.
    #
    # 2. Bind-mount the cdrom into the installed system as /cdrom.
    #
    # 3. Set up an overlay over /target/etc/apt. This means that any
    #    changes we make will not persist into the installed system and we
    #    do not have to worry about cleaning up after ourselves.
    #
    # 4. Configure apt in /target to look at the pool on the cdrom.  This
    #    has two subcases:
    #
    #     a. if we expect the network to be working, this basically means
    #        prepending
    #        "deb file:///run/cdrom $(lsb_release -sc) main restricted"
    #        to the sources.list file.
    #
    #     b. if the network is not expected to be working, we replace the
    #        sources.list with a file just referencing the cdrom.
    #
    # 5. If the network is not expected to be working, we also set up an
    #    overlay over /target/var/lib/apt/lists (if the network is working,
    #    we'll run "apt update" after the /target/etc/apt overlay has been
    #    cleared).

    def tpath(*args):
        return os.path.join(app.base_model.target, *args)

    await run_curtin_command(
        app, context, 'apt-config', '-t', tpath(), config=config_location)

    await setup_overlay(app.command_runner, tpath('etc/apt'))

    os.mkdir(tpath('cdrom'))
    await mount(app.command_runner, '/cdrom', tpath('cdrom'), options='bind')

    if app.base_model.network.has_network:
        os.rename(
            tpath('etc/apt/sources.list'),
            tpath('etc/apt/sources.list.d/original.list'))
    else:
        os.unlink(tpath('etc/apt/apt.conf.d/90curtin-aptproxy'))
        await setup_overlay(app.command_runner, tpath('var/lib/apt/lists'))

    codename = lsb_release()['codename']

    write_file(
        tpath('etc/apt/sources.list'),
        f'deb [check-date=no] file:///cdrom {codename} main restricted\n',
        )

    await run_curtin_command(
        app, context, "in-target", "-t", tpath(), "--", "apt-get", "update")
