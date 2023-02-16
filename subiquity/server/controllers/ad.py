# Copyright 2023 Canonical, Ltd.
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
import re
from typing import List, Optional, Set

from subiquity.common.apidef import API
from subiquity.common.types import (
    ADConnectionInfo,
    AdAdminNameValidation,
    AdDomainNameValidation,
    AdPasswordValidation
)
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.ad')

DC_RE = r'^[a-zA-Z0-9.-]+$'
# Validation has changed since Ubiquity. See the following links on why:
# https://bugs.launchpad.net/ubuntu-mate/+bug/1985971
# https://github.com/canonical/subiquity/pull/1553#discussion_r1103063195
# https://learn.microsoft.com/en-us/windows/win32/adschema/a-samaccountname
AD_ACCOUNT_FORBIDDEN_CHARS = r'@"/\[]:;|=,+*?<>'
FIELD = "Domain Controller name"


class ADController(SubiquityController):
    """ Implements the server part of the Active Directory feature. """
    model_name = "ad"
    endpoint = API.active_directory
    # No auto install key and schema for now due password handling uncertainty.

    async def GET(self) -> Optional[ADConnectionInfo]:
        """Returns the currently configured AD settings"""
        return self.model.conn_info

    async def POST(self, data: ADConnectionInfo) -> None:
        """ Configures this controller with the supplied info.
            Clients are required to validate the info before POST'ing """
        self.model.conn_info = data
        await self.configured()

    async def check_admin_name_GET(self, admin_name: str) \
            -> AdAdminNameValidation:
        return AdValidators.admin_user_name(admin_name)

    async def check_domain_name_GET(self, domain_name: str) \
            -> List[AdDomainNameValidation]:
        result = AdValidators.domain_name(domain_name)
        return list(result)

    async def check_password_GET(self, password: str) -> AdPasswordValidation:
        return AdValidators.password(password)


# Helper out-of-class functions grouped.
class AdValidators:
    """ Groups functions that validates the AD info supplied by users. """
    @staticmethod
    def admin_user_name(name) -> AdAdminNameValidation:
        """ Validates the supplied admin name against known patterns. """

        if len(name) == 0:
            log.debug("admin name is empty")
            return AdAdminNameValidation.EMPTY

        # Triggers error if any of the forbidden chars is present.
        regex = re.compile(f"[{re.escape(AD_ACCOUNT_FORBIDDEN_CHARS)}]")
        if regex.search(name):
            log.debug('<%s>: domain admin name contains invalid characters',
                      name)
            return AdAdminNameValidation.INVALID_CHARS

        return AdAdminNameValidation.OK

    @staticmethod
    def password(value: str) -> AdPasswordValidation:
        """ Validates that the password is not empty. """

        if not value:
            return AdPasswordValidation.EMPTY

        return AdPasswordValidation.OK

    @staticmethod
    def domain_name(name: str) -> Set[AdDomainNameValidation]:
        """ Check the correctness of a proposed host name.

        Returns a set of the possible errors:
            - OK = self explanatory. Should be the only result then.
            - EMPTY = Self explanatory. Should be the only result then.
            - TOO_LONG = Self explanatory.
            - INVALID_CHARS = Found characters not matching the expected regex.
            - START_DOT = Starts with a dot (.)
            - END_DOT = Ends with a dot (.)
            - START_HYPHEN = Starts with an hyphen (-).
            - END_HYPHEN = Ends with a hyphen (-).
            - MULTIPLE_DOTS = Contains multiple sequenced dots (..)
        """
        result = set()

        if len(name) < 1:
            log.debug("%s is empty", FIELD)
            result.add(AdDomainNameValidation.EMPTY)
            return result

        if len(name) > 63:
            log.debug("<%s>: %s too long", name, FIELD)
            result.add(AdDomainNameValidation.TOO_LONG)

        if name.startswith('-'):
            log.debug("<%s>: %s cannot start with hyphens (-)",
                      name, FIELD)
            result.add(AdDomainNameValidation.START_HYPHEN)

        if name.endswith('-'):
            log.debug("<%s>: %s cannot end with hyphens (-)",
                      name, FIELD)
            result.add(AdDomainNameValidation.END_HYPHEN)

        if '..' in name:
            log.debug('<%s>: %s cannot contain double dots (..)', name, FIELD)
            result.add(AdDomainNameValidation.MULTIPLE_DOTS)

        if name.startswith('.'):
            log.debug('<%s>: %s cannot start with dots (.)',
                      name, FIELD)
            result.add(AdDomainNameValidation.START_DOT)

        if name.endswith('.'):
            log.debug('<%s>: %s cannot end with dots (.)',
                      name, FIELD)
            result.add(AdDomainNameValidation.END_DOT)

        regex = re.compile(DC_RE)
        if not regex.search(name):
            result.add(AdDomainNameValidation.INVALID_CHARS)
            log.debug('<%s>: %s contains invalid characters', name, FIELD)

        if result:
            return result

        return {AdDomainNameValidation.OK}
