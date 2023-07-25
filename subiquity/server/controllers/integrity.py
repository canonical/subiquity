# Copyright 2022 Canonical, Ltd.
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

from subiquity.common.apidef import API
from subiquity.common.types import CasperMd5Results
from subiquity.journald import journald_get_first_match
from subiquity.server.controller import SubiquityController
from subiquitycore.async_helpers import schedule_task

log = logging.getLogger("subiquity.server.controllers.integrity")

mock_pass = {"checksum_missmatch": [], "result": "pass"}
mock_skip = {"checksum_missmatch": [], "result": "skip"}
mock_fail = {"checksum_missmatch": ["./casper/initrd"], "result": "fail"}


class IntegrityController(SubiquityController):
    endpoint = API.integrity

    model_name = "integrity"
    result_filepath = "/run/casper-md5check.json"

    @property
    def result(self):
        return CasperMd5Results(self.model.md5check_results.get("result", "unknown"))

    async def GET(self) -> CasperMd5Results:
        return self.result

    async def wait_casper_md5check(self):
        if not self.app.opts.dry_run:
            await journald_get_first_match(
                "systemd", "UNIT=casper-md5check.service", "JOB_RESULT=done"
            )

    async def get_md5check_results(self):
        if self.app.opts.dry_run:
            return mock_fail
        with open(self.result_filepath) as fp:
            try:
                ret = json.load(fp)
            except json.JSONDecodeError as jde:
                log.debug(f"error reading casper-md5check results: {jde}")
                return {}
            else:
                log.debug(f"casper-md5check results: {ret}")
                return ret

    async def md5check(self):
        await self.wait_casper_md5check()
        self.model.md5check_results = await self.get_md5check_results()

    def start(self):
        self._md5check_task = schedule_task(self.md5check())
