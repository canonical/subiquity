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
from subiquity.common.types import ADConnectionInfo, ADValidationResult
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.ad')

DC_RE = r'^[a-zA-Z0-9.-]+$'
ADMIN_RE = r'^[-a-zA-Z0-9_]+$'
FIELD = "Domain Controller name"


class ADController(SubiquityController):
    """ Implements the server part of the Active Directory feature. """
    model_name = "ad"
    endpoint = API.active_directory
    # No auto install key and schema for now due password handling uncertainty.

    async def GET(self) -> Optional[ADConnectionInfo]:
        """Returns the currently configured AD settings"""
        return self.model.conn_info

    async def POST(self, data: ADConnectionInfo) -> List[ADValidationResult]:
        """ Configures this controller with the supplied info.
            Returns a list of errors if the info submitted is invalid or
            [ADValidationResult.OK] on success. """
        result = set()
        result |= check_domain_name(data.domain_name)
        result |= check_admin_user_name(data.admin_name)
        result |= check_password(data.password)

        if len(result) > 0:
            return list(result)

        self.model.conn_info = data
        await self.configured()
        return [ADValidationResult.OK]


# Helper out-of-class functions:

def check_admin_user_name(name) -> Set[ADValidationResult]:
    """ Validates the supplied admin name.
        Returns a set of the possible errors. """
    result = set()

    if len(name) == 0:
        log.debug("admin name is empty")
        return {ADValidationResult.ADMIN_NAME_EMPTY}

# Ubiquity checks the admin name in two steps:
# 1. validate the first char against '[a-zA-Z]'
# 2. check the entire string against r'^[-a-zA-Z0-9_]+$'
    if not re.match('[a-zA-Z]', name[0]):
        result.add(ADValidationResult.ADMIN_NAME_BAD_FIRST_CHAR)

    if len(name) == 1:
        return result

    regex = re.compile(ADMIN_RE)
    if not regex.match(name[1:]):
        log.debug('<%s>: domain admin name contains invalid characters',
                  name)
        result.add(ADValidationResult.ADMIN_NAME_BAD_CHARS)

    return result


def check_password(value: str) -> Set[ADValidationResult]:
    """ Validates that the password is not empty. """
    result = set()

    if len(value) < 1:
        result.add(ADValidationResult.PASSWORD_EMPTY)

    return result


def check_domain_name(name: str) -> Set[ADValidationResult]:
    """ Check the correctness of a proposed host name.

    Returns a set of the possible errors:
        - C{DCNAME_BAD_LENGTH} wrong length.
        - C{DCNAME_BAD_CHARS} contains invalid characters.
        - C{DCNAME_BAD_HYPHEN} starts or ends with a hyphen.
        - C{DCNAME_BAD_DOTS} contains consecutive/initial/final dots."""

    result = set()

    if len(name) < 1 or len(name) > 63:
        log.debug("<%s>: %s too long or too short", name, FIELD)
        result.add(ADValidationResult.DCNAME_BAD_LENGTH)

    if name.startswith('-') or name.endswith('-'):
        log.debug("<%s>: %s cannot start nor end with hyphens (-)",
                  name, FIELD)
        result.add(ADValidationResult.DCNAME_BAD_HYPHEN)

    if '..' in name:
        log.debug('<%s>: %s cannot contain double dots (..)', name, FIELD)
        result.add(ADValidationResult.DCNAME_BAD_DOTS)

    if name.startswith('.') or name.endswith('.'):
        log.debug('<%s>: %s cannot start nor end with dots (.)',
                  name, FIELD)
        result.add(ADValidationResult.DCNAME_BAD_DOTS)

    regex = re.compile(DC_RE)
    if not regex.search(name):
        result.add(ADValidationResult.DCNAME_BAD_CHARS)
        log.debug('<%s>: %s contain invalid characters', name, FIELD)

    return result
