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

import logging
import os
from subiquity.server.controllers.locale import LocaleController
from subiquitycore.utils import arun_command

log = logging.getLogger('system_setup.server.controllers.locale')


class WSLLocaleController(LocaleController):
    def start(self):
        if self.app.prefillInfo:
            welcome = self.app.prefillInfo.get('Welcome', {'lang': None})
            win_lang = welcome.get('lang')
            if win_lang:
                self.model.selected_language = win_lang
                log.debug('Prefilled Language: {}'
                          .format(self.model.selected_language))

        super().start()

    async def _run_locale_support_cmds(self, lang: str):
        """ Final commands to be ran when a valid language is POST'ed. """

        env = os.environ.copy()
        # Ensure minimal console translation is enabled.
        cmds = (["locale-gen"],
                ["update-locale", "LANG={}".format(lang)],
                ["bash", "-c", "\"apt", "install", "$(check-language-support",
                 "-l", lang[0:2], ")\""])
        if self.app.opts.dry_run:
            for cmd in cmds:
                log.debug('Would run: ' + ' '.join(cmd))
        else:
            for cmd in cmds:
                cp = await arun_command(cmd, env=env)
                if cp.returncode:
                    log.debug('Command \"%s\" failed with return code %d',
                              cp.args, cp.returncode)

    async def POST(self, data: str):
        if data == self.autoinstall_default or data == os.environ.get("LANG"):
            await super().POST(data)
            return

        fileContents: str
        fname = "locale.gen"
        env = os.environ.copy()
        if self.app.opts.dry_run:
            # For debug purposes.
            fname = ".subiquity/" + fname
            await arun_command(['cp', '/etc/locale.gen', '.subiquity/'],
                               env=env)
        else:
            fname = "/etc/" + fname

        pendingWrite = False
        with open(fname, "r") as localeGen:
            # locale.gen is not so big.
            fileContents = localeGen.read()
            lineFound = fileContents.find(data)
            if lineFound == -1:
                # An unsupported locale coming from our UI is a bug.
                raise AssertionError("Selected language {} not supported."
                                     " Rolling back.".format(data))

            commented = "# {}".format(data)
            lineFound = fileContents.find(commented)
            if lineFound != -1:
                fileContents = fileContents.replace(commented, data)
                pendingWrite = True

        if pendingWrite:
            with open(fname, "wt") as f:
                f.write(fileContents)

        # If we arrive here, data is a supported language.
        await self._run_locale_support_cmds(data)
        await super().POST(data)
