# Copyright 2019 Canonical, Ltd.
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

import fnmatch
import json
import re
import unittest
from unittest import mock

import yaml
from cloudinit.config.schema import SchemaValidationError

from subiquitycore.tests.parameterized import parameterized

try:
    from cloudinit.config.schema import SchemaProblem
except ImportError:

    def SchemaProblem(x, y):
        return (x, y)  # TODO(drop on cloud-init 22.3 SRU)


from subiquity.common.types import IdentityData
from subiquity.models.subiquity import (
    CLOUDINIT_CLEAN_FILE_TMPL,
    HOSTS_CONTENT,
    ModelNames,
    SubiquityModel,
)
from subiquity.server.server import INSTALL_MODEL_NAMES, POSTINSTALL_MODEL_NAMES
from subiquity.server.types import InstallerChannels
from subiquitycore.pubsub import MessageHub


class TestModelNames(unittest.TestCase):
    def test_for_known_variant(self):
        model_names = ModelNames({"a"}, var1={"b"}, var2={"c"})
        self.assertEqual(model_names.for_variant("var1"), {"a", "b"})

    def test_for_unknown_variant(self):
        model_names = ModelNames({"a"}, var1={"b"}, var2={"c"})
        self.assertEqual(model_names.for_variant("var3"), {"a"})

    def test_all(self):
        model_names = ModelNames({"a"}, var1={"b"}, var2={"c"})
        self.assertEqual(model_names.all(), {"a", "b", "c"})


class TestSubiquityModel(unittest.IsolatedAsyncioTestCase):
    maxDiff = None

    def writtenFiles(self, config):
        for k, v in config.get("write_files", {}).items():
            yield v

    def assertConfigWritesFile(self, config, path):
        self.assertIn(path, [s["path"] for s in self.writtenFiles(config)])

    def writtenFilesMatching(self, config, pattern):
        files = list(self.writtenFiles(config))
        matching = []
        for spec in files:
            if fnmatch.fnmatch(spec["path"], pattern):
                matching.append(spec)
        return matching

    def writtenFilesMatchingContaining(self, config, pattern, content):
        matching = []
        for spec in self.writtenFilesMatching(config, pattern):
            if content in spec["content"]:
                matching.append(content)
        return matching

    def configVal(self, config, path):
        cur = config
        for component in path.split("."):
            if not isinstance(cur, dict):
                self.fail(
                    "extracting {} reached non-dict {} too early".format(path, cur)
                )
            if component not in cur:
                self.fail("no value found for {}".format(path))
            cur = cur[component]
        return cur

    def assertConfigHasVal(self, config, path, val):
        self.assertEqual(self.configVal(config, path), val)

    def assertConfigDoesNotHaveVal(self, config, path):
        cur = config
        for component in path.split("."):
            if not isinstance(cur, dict):
                self.fail(
                    "extracting {} reached non-dict {} too early".format(path, cur)
                )
            if component not in cur:
                return
            cur = cur[component]
        self.fail("config has value {} for {}".format(cur, path))

    async def test_configure(self):
        hub = MessageHub()
        model = SubiquityModel("test", hub, ModelNames({"a", "b"}), ModelNames(set()))
        model.set_source_variant("var")
        await hub.abroadcast((InstallerChannels.CONFIGURED, "a"))
        self.assertFalse(model._install_event.is_set())
        await hub.abroadcast((InstallerChannels.CONFIGURED, "b"))
        self.assertTrue(model._install_event.is_set())

    def make_model(self):
        return SubiquityModel(
            "test", MessageHub(), INSTALL_MODEL_NAMES, POSTINSTALL_MODEL_NAMES
        )

    def test_proxy_set(self):
        model = self.make_model()
        proxy_val = "http://my-proxy"
        model.proxy.proxy = proxy_val
        config = model.render()
        self.assertConfigHasVal(config, "proxy.http_proxy", proxy_val)
        self.assertConfigHasVal(config, "proxy.https_proxy", proxy_val)
        confs = self.writtenFilesMatchingContaining(
            config,
            "etc/systemd/system/snapd.service.d/*.conf",
            "HTTP_PROXY=" + proxy_val,
        )
        self.assertTrue(len(confs) > 0)

    def test_proxy_notset(self):
        model = self.make_model()
        config = model.render()
        self.assertConfigDoesNotHaveVal(config, "proxy.http_proxy")
        self.assertConfigDoesNotHaveVal(config, "proxy.https_proxy")
        self.assertConfigDoesNotHaveVal(config, "apt.http_proxy")
        self.assertConfigDoesNotHaveVal(config, "apt.https_proxy")
        confs = self.writtenFilesMatchingContaining(
            config, "etc/systemd/system/snapd.service.d/*.conf", "HTTP_PROXY="
        )
        self.assertTrue(len(confs) == 0)

    def test_keyboard(self):
        model = self.make_model()
        config = model.render()
        self.assertConfigWritesFile(config, "etc/default/keyboard")

    def test_writes_machine_id_media_info(self):
        model_no_proxy = self.make_model()
        model_proxy = self.make_model()
        model_proxy.proxy.proxy = "http://something"
        for model in model_no_proxy, model_proxy:
            config = model.render()
            self.assertConfigWritesFile(config, "etc/machine-id")

    def test_storage_version(self):
        model = self.make_model()
        config = model.render()
        self.assertConfigHasVal(config, "storage.version", 1)

    @parameterized.expand(
        [
            [{}, True],
            [{"NETPLAN_CONFIG_ROOT_READ_ONLY": False}, True],
            [{"NETPLAN_CONFIG_ROOT_READ_ONLY": True}, False],
        ]
    )
    def test_write_netplan(self, features, np_content_expected):
        with mock.patch(
            "subiquity.cloudinit.open",
            mock.mock_open(read_data=json.dumps({"features": features})),
        ):
            model = self.make_model()
            config = model.render()
            netplan_content = None

            for fspec in config["write_files"].values():
                if fspec["path"].startswith("etc/netplan"):
                    if netplan_content is not None:
                        self.fail("writing two files to netplan?")
                    netplan_content = fspec["content"]
            if np_content_expected:
                self.assertIsNotNone(netplan_content)
                netplan = yaml.safe_load(netplan_content)
                self.assertConfigHasVal(netplan, "network.version", 2)
            else:
                self.assertIsNone(netplan_content)

    def test_sources(self):
        model = self.make_model()
        config = model.render()
        self.assertNotIn("sources", config)

    def test_mirror(self):
        model = self.make_model()
        mirror_val = "http://my-mirror"
        model.mirror.create_primary_candidate(mirror_val).elect()
        config = model.render()
        self.assertNotIn("apt", config)

    def test_cloud_init_user_list_merge(self):
        main_user = IdentityData(
            username="mainuser", crypted_password="sample_value", hostname="somehost"
        )
        secondary_user = {"name": "user2"}

        with self.subTest("Main user + secondary user"):
            model = self.make_model()
            model.identity.add_user(main_user)
            model.userdata = {"users": [secondary_user]}

            cloud_init_config = model._cloud_init_config()
            self.assertEqual(len(cloud_init_config["users"]), 2)
            self.assertEqual(
                cloud_init_config["users"][0],
                {"name": "mainuser", "lock_passwd": False},
            )
            self.assertEqual(cloud_init_config["users"][1]["name"], "user2")

        with self.subTest("Secondary user only"):
            model = self.make_model()
            model.userdata = {"users": [secondary_user]}
            cloud_init_config = model._cloud_init_config()
            self.assertEqual(len(cloud_init_config["users"]), 1)
            self.assertEqual(cloud_init_config["users"][0]["name"], "user2")

        with self.subTest("Invalid user-data raises error"):
            model = self.make_model()
            model.userdata = {"bootcmd": "nope"}
            with self.assertRaises(SchemaValidationError) as ctx:
                model._cloud_init_config()
            expected_error = (
                "Cloud config schema errors: bootcmd: 'nope' is not of type 'array'"
            )
            self.assertEqual(expected_error, str(ctx.exception))

    @mock.patch("subiquity.models.subiquity.lsb_release")
    @mock.patch("subiquitycore.file_util.datetime.datetime")
    def test_cloud_init_files_emits_datasource_config_and_clean_script(
        self, datetime, lsb_release
    ):
        datetime.utcnow.return_value = "2004-03-05 ..."
        main_user = IdentityData(
            username="mainuser", crypted_password="sample_pass", hostname="somehost"
        )

        model = self.make_model()
        model.identity.add_user(main_user)
        model.userdata = {}
        expected_files = {
            "etc/cloud/cloud.cfg.d/20-disable-cc-dpkg-grub.cfg": """\
grub_dpkg:
  enabled: false
""",
            "etc/cloud/cloud.cfg.d/99-installer.cfg": re.compile(
                "datasource:\n  None:\n    metadata:\n      instance-id: .*\n    userdata_raw: \"#cloud-config\\\\ngrowpart:\\\\n  mode: \\'off\\'\\\\npreserve_hostname: true\\\\n\\\\\n"  # noqa
            ),
            "etc/hostname": "somehost\n",
            "etc/cloud/ds-identify.cfg": "policy: enabled\n",
            "etc/hosts": HOSTS_CONTENT.format(hostname="somehost"),
        }

        # Avoid removing /etc/hosts and /etc/hostname in cloud-init clean
        cfg_files = ["/" + key for key in expected_files.keys() if "host" not in key]
        cfg_files.append(
            # Obtained from NetworkModel.render when cloud-init features
            # NETPLAN_CONFIG_ROOT_READ_ONLY is True
            "/etc/cloud/cloud.cfg.d/90-installer-network.cfg"
        )
        header = "# Autogenerated by Subiquity: 2004-03-05 ... UTC\n"
        with self.subTest(
            "Stable releases Jammy do not disable cloud-init."
            " NETPLAN_ROOT_READ_ONLY=True uses cloud-init networking"
        ):
            lsb_release.return_value = {"release": "22.04"}
            expected_files[
                "etc/cloud/clean.d/99-installer"
            ] = CLOUDINIT_CLEAN_FILE_TMPL.format(
                header=header, cfg_files=json.dumps(sorted(cfg_files))
            )
            with unittest.mock.patch(
                "subiquity.cloudinit.open",
                mock.mock_open(
                    read_data=json.dumps(
                        {"features": {"NETPLAN_CONFIG_ROOT_READ_ONLY": True}}
                    )
                ),
            ):
                for cpath, content, perms in model._cloud_init_files():
                    if isinstance(expected_files[cpath], re.Pattern):
                        self.assertIsNotNone(expected_files[cpath].match(content))
                    else:
                        self.assertEqual(expected_files[cpath], content)

        with self.subTest(
            "Kinetic++ disables cloud-init post install."
            " NETPLAN_ROOT_READ_ONLY=False avoids cloud-init networking"
        ):
            lsb_release.return_value = {"release": "22.10"}
            cfg_files.append(
                # Added by _cloud_init_files for 22.10 and later releases
                "/etc/cloud/cloud-init.disabled",
            )
            # Obtained from NetworkModel.render
            cfg_files.remove("/etc/cloud/cloud.cfg.d/90-installer-network.cfg")
            cfg_files.append("/etc/netplan/00-installer-config.yaml")
            cfg_files.append(
                "/etc/cloud/cloud.cfg.d/subiquity-disable-cloudinit-networking.cfg"
            )
            expected_files[
                "etc/cloud/clean.d/99-installer"
            ] = CLOUDINIT_CLEAN_FILE_TMPL.format(
                header=header, cfg_files=json.dumps(sorted(cfg_files))
            )
            with unittest.mock.patch(
                "subiquity.cloudinit.open",
                mock.mock_open(
                    read_data=json.dumps(
                        {"features": {"NETPLAN_CONFIG_ROOT_READ_ONLY": False}}
                    )
                ),
            ):
                for cpath, content, perms in model._cloud_init_files():
                    if isinstance(expected_files[cpath], re.Pattern):
                        self.assertIsNotNone(expected_files[cpath].match(content))
                    else:
                        self.assertEqual(expected_files[cpath], content)

    def test_validatecloudconfig_schema(self):
        model = self.make_model()
        with self.subTest("Valid cloud-config does not error"):
            model.validate_cloudconfig_schema(
                data={"ssh_import_id": ["chad.smith"]},
                data_source="autoinstall.user-data",
            )

        # Create our own subclass for focal as schema_deprecations
        # was not yet defined.
        class SchemaDeprecation(SchemaValidationError):
            schema_deprecations = ()

            def __init__(self, schema_errors=(), schema_deprecations=()):
                super().__init__(schema_errors)
                self.schema_deprecations = schema_deprecations

        problem = SchemaProblem(
            "bogus", "'bogus' is deprecated, use 'notbogus' instead"
        )
        with self.subTest("Deprecated cloud-config warns"):
            with unittest.mock.patch(
                "subiquity.models.subiquity.validate_cloudconfig_schema"
            ) as validate:
                validate.side_effect = SchemaDeprecation(schema_deprecations=(problem,))
                with self.assertLogs(
                    "subiquity.models.subiquity", level="INFO"
                ) as logs:
                    model.validate_cloudconfig_schema(
                        data={"bogus": True}, data_source="autoinstall.user-data"
                    )
            expected = (
                "WARNING:subiquity.models.subiquity:The cloud-init"
                " configuration for autoinstall.user-data contains deprecated"
                " values:\n'bogus' is deprecated, use 'notbogus' instead"
            )
            self.assertEqual(logs.output, [expected])

        with self.subTest("Invalid cloud-config schema errors"):
            with self.assertRaises(SchemaValidationError) as ctx:
                model.validate_cloudconfig_schema(
                    data={"bootcmd": "nope"}, data_source="system info"
                )
            expected_error = (
                "Cloud config schema errors: bootcmd: 'nope' is not of type 'array'"
            )
            self.assertEqual(expected_error, str(ctx.exception))

        with self.subTest("Prefix autoinstall.user-data cloud-config errors"):
            with self.assertRaises(SchemaValidationError) as ctx:
                model.validate_cloudconfig_schema(
                    data={"bootcmd": "nope"}, data_source="autoinstall.user-data"
                )
            expected_error = (
                "Cloud config schema errors:"
                " autoinstall.user-data.bootcmd: 'nope' is not of"
                " type 'array'"
            )
            self.assertEqual(expected_error, str(ctx.exception))


class TestUserCreationFlows(unittest.IsolatedAsyncioTestCase):
    """live-server and desktop have a key behavior difference: desktop will
    permit user creation on first boot, while server will do no such thing.
    When combined with documented autoinstall behaviors for the `identity`
    section and allowing `user-data` to mean that the `identity` section may be
    skipped, the following use cases need to be supported:

    1. PASS - interactive, UI triggers user creation (`identity_POST` called)
    2. PASS - interactive, if `identity` `mark_configured`, create nothing
    3. in autoinstall, supply an `identity` section
      a. PASS - and omit `user-data`
      b. PASS - and supply `user-data` but no `user-data.users`
      c. PASS - and supply `user-data` including `user-data.users`
    4. in autoinstall, omit an `identity` section
      a. and omit `user-data`
        1. FAIL - live-server - failure mode is autoinstall schema validation
        2. PASS - desktop
      b. PASS - and supply `user-data` but no `user-data.users`
        - cloud-init defaults
      c. PASS - and supply `user-data` including `user-data.users`

    The distinction of a user being created by autoinstall or not is not
    visible here, so some interactive and autoinstall test cases are equivalent
    at this abstraction layer (and are merged in the actual tests)."""

    def setUp(self):
        install = ModelNames(set())
        postinstall = ModelNames({"userdata"})
        self.model = SubiquityModel("test", MessageHub(), install, postinstall)
        self.user = dict(name="user", passwd="passw0rd")
        # Expected cloud-config user object if supplied in the identity model.
        self.user_id_userdata = {"name": "user", "lock_passwd": False}
        self.user_identity = IdentityData(
            username=self.user["name"], crypted_password=self.user["passwd"]
        )
        self.foobar = dict(name="foobar", passwd="foobarpassw0rd")

    def assertDictSubset(self, expected, actual):
        for key in expected.keys():
            msg = f"expected[{key}] != actual[{key}]"
            self.assertEqual(expected[key], actual[key], msg)

    def test_create_user_cases_1_3a(self):
        self.assertIsNone(self.model.userdata)
        self.model.identity.add_user(self.user_identity)
        cloud_cfg = self.model._cloud_init_config()
        [actual] = cloud_cfg["users"]
        self.assertEqual(self.user_id_userdata, actual)

    def test_assert_no_default_user_cases_2_4a2(self):
        self.assertIsNone(self.model.userdata)
        cloud_cfg = self.model._cloud_init_config()
        self.assertEqual([], cloud_cfg["users"])

    def test_create_user_but_no_merge_case_3b(self):
        # near identical to cases 1 / 3a but user-data is present in
        # autoinstall, however this doesn't change the outcome.
        self.model.userdata = {}
        self.model.identity.add_user(self.user_identity)
        cloud_cfg = self.model._cloud_init_config()
        [actual] = cloud_cfg["users"]
        self.assertEqual(self.user_id_userdata, actual)

    def test_create_user_and_merge_case_3c(self):
        # now we have more user info to merge in
        self.model.userdata = {"users": ["default", self.foobar]}
        self.model.identity.add_user(self.user_identity)
        cloud_cfg = self.model._cloud_init_config()
        for actual in cloud_cfg["users"]:
            if isinstance(actual, str):
                self.assertEqual("default", actual)
            else:
                if actual["name"] == self.user["name"]:
                    self.assertEqual(self.user_id_userdata, actual)
                else:
                    self.assertDictSubset(self.foobar, actual)

    def test_create_user_and_merge_case_3c_empty(self):
        # another merge case, but a merge of an empty list, so we
        # have just supplied the `identity` user with extra steps
        self.model.userdata = {"users": []}
        self.model.identity.add_user(self.user_identity)
        cloud_cfg = self.model._cloud_init_config()
        [actual] = cloud_cfg["users"]
        self.assertEqual(self.user_id_userdata, actual)

    # 4a1 fails before we get here, see TestControllerUserCreationFlows in
    # subiquity/server/controllers/tests/test_identity.py for details.

    def test_create_nothing_case_4b(self):
        self.model.userdata = {}
        cloud_cfg = self.model._cloud_init_config()
        self.assertNotIn("users", cloud_cfg)

    def test_create_only_merge_4c(self):
        self.model.userdata = {"users": ["default", self.foobar]}
        cloud_cfg = self.model._cloud_init_config()
        for actual in cloud_cfg["users"]:
            if isinstance(actual, str):
                self.assertEqual("default", actual)
            else:
                self.assertDictSubset(self.foobar, actual)

    def test_create_only_merge_4c_empty(self):
        # explicitly saying no (additional) users, thank you very much
        self.model.userdata = {"users": []}
        cloud_cfg = self.model._cloud_init_config()
        self.assertEqual([], cloud_cfg["users"])
