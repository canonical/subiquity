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

from unittest import IsolatedAsyncioTestCase, TestCase

from subiquity.common.types import (
    AdAdminNameValidation,
    AdConnectionInfo,
    AdDomainNameValidation,
    AdJoinResult,
    AdPasswordValidation,
)
from subiquity.models.ad import AdModel
from subiquity.server.controllers.ad import AdController, AdValidators
from subiquitycore.tests.mocks import make_app


class TestADValidation(TestCase):
    def test_password(self):
        # We curently only check for empty passwords.
        passwd = ""
        result = AdValidators.password(passwd)
        self.assertEqual(AdPasswordValidation.EMPTY, result)

        passwd = "u"
        result = AdValidators.password(passwd)
        self.assertEqual(AdPasswordValidation.OK, result)

    def test_domain_name(self):
        domain = ""
        result = AdValidators.domain_name(domain)
        self.assertEqual({AdDomainNameValidation.EMPTY}, result)

        domain = "u" * 64
        result = AdValidators.domain_name(domain)
        self.assertEqual({AdDomainNameValidation.TOO_LONG}, result)

        domain = "..ubuntu.com"
        result = AdValidators.domain_name(domain)
        self.assertEqual(
            {AdDomainNameValidation.MULTIPLE_DOTS, AdDomainNameValidation.START_DOT},
            result,
        )

        domain = ".ubuntu.com."
        result = AdValidators.domain_name(domain)
        self.assertEqual(
            {AdDomainNameValidation.START_DOT, AdDomainNameValidation.END_DOT}, result
        )

        domain = "-ubuntu.com-"
        result = AdValidators.domain_name(domain)
        self.assertEqual(
            {AdDomainNameValidation.START_HYPHEN, AdDomainNameValidation.END_HYPHEN},
            result,
        )

        domain = "ubuntu^pro.com"
        result = AdValidators.domain_name(domain)
        self.assertEqual({AdDomainNameValidation.INVALID_CHARS}, result)

        domain = "ubuntu-p^ro.com."
        result = AdValidators.domain_name(domain)
        self.assertEqual(
            {AdDomainNameValidation.INVALID_CHARS, AdDomainNameValidation.END_DOT},
            result,
        )

        domain = "ubuntupro.com"
        result = AdValidators.domain_name(domain)
        self.assertEqual({AdDomainNameValidation.OK}, result)

    def test_username(self):
        admin = ""
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.EMPTY, result)

        admin = "ubuntu;pro"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "ubuntu:pro"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "=ubuntu"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "ubuntu@pro"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "ubuntu+pro"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "ubuntu\\"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = 'ubuntu"pro'
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "ubuntu[pro"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "ubuntu>"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        admin = "ubuntu*pro"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.INVALID_CHARS, result)

        # Notice that lowercase is not required.
        admin = r"$Ubuntu{}"
        result = AdValidators.admin_user_name(admin)
        self.assertEqual(AdAdminNameValidation.OK, result)


class TestAdJoin(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.controller = AdController(self.app)
        self.controller.model = AdModel()

    async def test_never_join(self):
        # Calling join_result_GET has no effect if the model is not set.
        result = await self.controller.join_result_GET(wait=True)
        self.assertEqual(result, AdJoinResult.UNKNOWN)

    async def test_join_Unknown(self):
        # Result remains UNKNOWN while AdController.join_domain is not called.
        self.controller.model.set(
            AdConnectionInfo(
                domain_name="ubuntu.com", admin_name="Helper", password="1234"
            )
        )

        result = await self.controller.join_result_GET(wait=False)
        self.assertEqual(result, AdJoinResult.UNKNOWN)

    async def test_join_OK(self):
        # The equivalent of a successful POST
        self.controller.model.set(
            AdConnectionInfo(
                domain_name="ubuntu.com", admin_name="Helper", password="1234"
            )
        )
        # Mimics a client requesting the join result. Blocking by default.
        result = self.controller.join_result_GET()
        # Mimics a calling from the install controller.
        await self.controller.join_domain("this", "AD Join")
        self.assertEqual(await result, AdJoinResult.OK)

    async def test_join_Join_Error(self):
        self.controller.model.set(
            AdConnectionInfo(
                domain_name="jubuntu.com", admin_name="Helper", password="1234"
            )
        )
        await self.controller.join_domain("this", "AD Join")
        result = await self.controller.join_result_GET(wait=True)
        self.assertEqual(result, AdJoinResult.JOIN_ERROR)

    async def test_join_Pam_Error(self):
        self.controller.model.set(
            AdConnectionInfo(
                domain_name="pubuntu.com", admin_name="Helper", password="1234"
            )
        )
        await self.controller.join_domain("this", "AD Join")
        result = await self.controller.join_result_GET(wait=True)
        self.assertEqual(result, AdJoinResult.PAM_ERROR)
