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
import random
from tornado.gen import coroutine
import subiquity.utils as utils
from subiquity.models import InstallProgressModel
from subiquity.ui.views import ProgressView
from subiquity.controller import ControllerPolicy
from subiquity.curtin import (CURTIN_CONFIGS,
                              curtin_install_cmd,
                              curtin_write_postinst_config)

log = logging.getLogger("subiquity.controller.installprogress")


class InstallProgressController(ControllerPolicy):
    KIRBY = ["(>'-')>",
             "<('-'<)",
             "<('-')>",
             "(>'-')>",
             "<('-'<)",
             "<('-')>",
             "(>'-')>",
             "<('-'<)",
             "<('-')>",
             "(>'-')>",
             "<('-'<)"]

    def __init__(self, common):
        super().__init__(common)
        self.model = InstallProgressModel()
        self.progress_view = None
        self.is_complete = False
        self.alarm = None

    @coroutine
    def curtin_install(self, postconfig):
        self.signal.emit_signal('installprogress:show')

        log.debug('Curtin Install: calling curtin with '
                  'storage/net/postinstall config')

        curtin_write_postinst_config(postconfig)

        configs = [CURTIN_CONFIGS['network'],
                   CURTIN_CONFIGS['storage'],
                   CURTIN_CONFIGS['postinstall']]
        curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        if self.opts.dry_run:
            log.debug("Filesystem: this is a dry-run")
            result = yield utils.run_command_async('cat /var/log/syslog')
            self.is_complete = True
        else:
            log.debug("filesystem: this is the *real* thing")
            result = yield utils.run_command_async(" ".join(curtin_cmd))
            if result['status'] > 0:
                log.error("Problem with curtin "
                          "install: {}".format(result))
                raise Exception("Problem with curtin install")
            self.is_complete = True

    def progress_indicator(self, *args, **kwargs):
        if self.is_complete:
            self.progress_view.text.set_text(
                "Finished install, press (Q) to reboot.")
            self.loop.remove_alarm(self.alarm)
        else:
            random.shuffle(self.KIRBY)
            self.progress_view.text.set_text(
                "Still installing, watch kirby dance, {}".format(
                    self.KIRBY[random.randrange(len(self.KIRBY))]))
            self.alarm = self.loop.set_alarm_in(0.3, self.progress_indicator)

    @coroutine
    def show_progress(self):
        log.debug('show_progress called')
        title = ("Installing system")
        excerpt = ("Please wait for the installation "
                   "to finish before rebooting.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 90)
        self.progress_view = ProgressView(self.signal)
        self.ui.set_body(self.progress_view)

        if self.opts.dry_run:
            banner = [
                "**** DRY_RUN ****",
                ""
                "",
                "",
                "",
                "Press (Q) to Quit."
            ]
            self.progress_view.text.set_text("\n".join(banner))
        else:
            self.alarm = self.loop.set_alarm_in(0.3, self.progress_indicator)

        self.ui.set_footer(footer, 100)
