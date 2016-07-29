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

from subiquitycore.ui.views.identity import BaseIdentityView
from subiquitycore.user import create_user

log = logging.getLogger("console_conf.views.identity")


class IdentityView(BaseIdentityView):
    def create_user(self, result):
        try:
            create_user(
                result, dryrun=self.opts.dry_run, extra_args=['--extrausers'])
        except PermissionError:
            # XXX do something here
            log.exception('Failed to create user.')
            return None
