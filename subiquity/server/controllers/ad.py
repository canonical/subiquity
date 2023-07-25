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
import os
import re
from typing import List, Optional, Set

from subiquity.common.apidef import API
from subiquity.common.types import (
    AdAdminNameValidation,
    AdConnectionInfo,
    AdDomainNameValidation,
    AdJoinResult,
    AdPasswordValidation,
)
from subiquity.server.ad_joiner import AdJoiner
from subiquity.server.controller import SubiquityController
from subiquitycore.async_helpers import run_bg_task
from subiquitycore.utils import arun_command

log = logging.getLogger("subiquity.server.controllers.ad")

DC_RE = r"^[a-zA-Z0-9.-]+$"
# Validation has changed since Ubiquity. See the following links on why:
# https://bugs.launchpad.net/ubuntu-mate/+bug/1985971
# https://github.com/canonical/subiquity/pull/1553#discussion_r1103063195
# https://learn.microsoft.com/en-us/windows/win32/adschema/a-samaccountname
AD_ACCOUNT_FORBIDDEN_CHARS = r'@"/\[]:;|=,+*?<>'
FIELD = "Domain Controller name"


class DcPingStrategy:
    # Consider staging in the snap for future proof.
    cmd = "/usr/sbin/realm"
    arg = "discover"

    def has_support(self) -> bool:
        return os.access(self.cmd, os.X_OK)

    async def ping(self, address: str) -> AdDomainNameValidation:
        cp = await arun_command([self.cmd, self.arg, address], env={})
        if cp.returncode:
            return AdDomainNameValidation.REALM_NOT_FOUND

        return AdDomainNameValidation.OK

    async def discover(self) -> str:
        """Attempts to discover a domain through the network.
        Returns the domain or an empty string on error."""
        cp = await arun_command([self.cmd, self.arg], env={})
        discovered = ""
        if cp.returncode == 0:
            # A typical output looks like:
            # 'creative.com\n  type: kerberos\n  realm-name: CREATIVE.COM\n...'
            discovered = cp.stdout.split("\n")[0].strip()

        return discovered


class StubDcPingStrategy(DcPingStrategy):
    """For testing purpose. This class doesn't talk to the network.
    Instead its response follows the following rule:

    - addresses starting with "r" return REALM_NOT_FOUND;
    - addresses starting with any other letter return OK."""

    async def ping(self, address: str) -> AdDomainNameValidation:
        if address[0] == "r":
            return AdDomainNameValidation.REALM_NOT_FOUND

        return AdDomainNameValidation.OK

    async def discover(self) -> str:
        return "ubuntu.com"

    def has_support(self) -> bool:
        return True


class AdController(SubiquityController):
    """Implements the server part of the Active Directory feature."""

    endpoint = API.active_directory
    # No auto install key and schema for now due password handling uncertainty.
    autoinstall_key = "active-directory"
    model_name = "active_directory"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "admin-name": {
                "type": "string",
            },
            "domain-name": {
                "type": "string",
            },
        },
        "additionalProperties": False,
    }
    autoinstall_default = {"admin-name": "", "domain-name": ""}

    def make_autoinstall(self):
        info = self.model.conn_info
        if info is None:
            return None

        return {"admin-name": info.admin_name, "domain-name": info.domain_name}

    def load_autoinstall_data(self, data):
        if data is None:
            return
        if "admin-name" in data and "domain-name" in data:
            info = AdConnectionInfo(
                admin_name=data["admin-name"], domain_name=data["domain-name"]
            )
            self.model.set(info)
            self.model.do_join = False

    def interactive(self):
        # Since we don't accept the domain admin password in the autoinstall
        # file, this cannot be non-interactive.

        # HACK: the interactive behavior is causing some autoinstalls with
        # desktop to block.
        # return True
        return False

    def __init__(self, app):
        super().__init__(app)
        self.ad_joiner = AdJoiner(self.app)
        self.join_result = AdJoinResult.UNKNOWN
        if self.app.opts.dry_run:
            self.ping_strgy = StubDcPingStrategy()
        else:
            self.ping_strgy = DcPingStrategy()

    def start(self):
        if self.ping_strgy.has_support():
            run_bg_task(self._try_discover_domain())

    async def _try_discover_domain(self):
        discovered_domain = await self.ping_strgy.discover()
        if discovered_domain:
            self.model.set_domain(discovered_domain)

    async def GET(self) -> Optional[AdConnectionInfo]:
        """Returns the currently configured AD settings"""
        return self.model.conn_info

    async def POST(self, data: AdConnectionInfo) -> None:
        """Configures this controller with the supplied info.
        Clients are required to validate the info before POST'ing"""
        self.model.set(data)
        await self.configured()

    async def check_admin_name_POST(self, admin_name: str) -> AdAdminNameValidation:
        return AdValidators.admin_user_name(admin_name)

    async def check_domain_name_POST(
        self, domain_name: str
    ) -> List[AdDomainNameValidation]:
        result = AdValidators.domain_name(domain_name)
        return list(result)

    async def ping_domain_controller_POST(
        self, domain_name: str
    ) -> AdDomainNameValidation:
        return await AdValidators.ping_domain_controller(domain_name, self.ping_strgy)

    async def check_password_POST(self, password: str) -> AdPasswordValidation:
        return AdValidators.password(password)

    async def has_support_GET(self) -> bool:
        """Returns True if the executables required
        to configure AD are present in the live system."""
        return self.ping_strgy.has_support()

    async def join_result_GET(self, wait: bool = True) -> AdJoinResult:
        """If [wait] is True and the model is set for joining, this method
        blocks until an attempt to join a domain completes.
        Otherwise returns the current known state.
        Most likely it will be AdJoinResult.UNKNOWN."""
        if wait and self.model.do_join:
            self.join_result = await self.ad_joiner.join_result()

        return self.join_result

    async def join_domain(self, hostname: str, context) -> None:
        """To be called from the install controller if the user requested
        joining an AD domain"""
        await self.ad_joiner.join_domain(self.model.conn_info, hostname, context)


# Helper out-of-class functions grouped.
class AdValidators:
    """Groups functions that validates the AD info supplied by users."""

    @staticmethod
    def admin_user_name(name) -> AdAdminNameValidation:
        """Validates the supplied admin name against known patterns."""

        if len(name) == 0:
            log.debug("admin name is empty")
            return AdAdminNameValidation.EMPTY

        # Triggers error if any of the forbidden chars is present.
        regex = re.compile(f"[{re.escape(AD_ACCOUNT_FORBIDDEN_CHARS)}]")
        if regex.search(name):
            log.debug("<%s>: domain admin name contains invalid characters", name)
            return AdAdminNameValidation.INVALID_CHARS

        return AdAdminNameValidation.OK

    @staticmethod
    def password(value: str) -> AdPasswordValidation:
        """Validates that the password is not empty."""

        if not value:
            return AdPasswordValidation.EMPTY

        return AdPasswordValidation.OK

    @staticmethod
    def domain_name(name: str) -> Set[AdDomainNameValidation]:
        """Check the correctness of a proposed host name.

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

        if name.startswith("-"):
            log.debug("<%s>: %s cannot start with hyphens (-)", name, FIELD)
            result.add(AdDomainNameValidation.START_HYPHEN)

        if name.endswith("-"):
            log.debug("<%s>: %s cannot end with hyphens (-)", name, FIELD)
            result.add(AdDomainNameValidation.END_HYPHEN)

        if ".." in name:
            log.debug("<%s>: %s cannot contain double dots (..)", name, FIELD)
            result.add(AdDomainNameValidation.MULTIPLE_DOTS)

        if name.startswith("."):
            log.debug("<%s>: %s cannot start with dots (.)", name, FIELD)
            result.add(AdDomainNameValidation.START_DOT)

        if name.endswith("."):
            log.debug("<%s>: %s cannot end with dots (.)", name, FIELD)
            result.add(AdDomainNameValidation.END_DOT)

        regex = re.compile(DC_RE)
        if not regex.search(name):
            result.add(AdDomainNameValidation.INVALID_CHARS)
            log.debug("<%s>: %s contains invalid characters", name, FIELD)

        if result:
            return result

        return {AdDomainNameValidation.OK}

    @staticmethod
    async def ping_domain_controller(
        name: str, strategy: DcPingStrategy
    ) -> AdDomainNameValidation:
        """Attempts to find the specified DC in the network.
        Returns either OK, EMPTY or REALM_NOT_FOUND."""

        if not name:
            return AdDomainNameValidation.EMPTY

        return await strategy.ping(name)
