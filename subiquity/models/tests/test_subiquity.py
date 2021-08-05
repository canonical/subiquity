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
import unittest
import yaml

from subiquity.models.subiquity import ModelNames, SubiquityModel
from subiquity.server.server import (
    INSTALL_MODEL_NAMES,
    POSTINSTALL_MODEL_NAMES,
    )


class TestModelNames(unittest.TestCase):

    def test_for_known_variant(self):
        model_names = ModelNames({'a'}, var1={'b'}, var2={'c'})
        self.assertEqual(model_names.for_variant('var1'), {'a', 'b'})

    def test_for_unknown_variant(self):
        model_names = ModelNames({'a'}, var1={'b'}, var2={'c'})
        self.assertEqual(model_names.for_variant('var3'), {'a'})

    def test_all(self):
        model_names = ModelNames({'a'}, var1={'b'}, var2={'c'})
        self.assertEqual(model_names.all(), {'a', 'b', 'c'})


class TestSubiquityModel(unittest.TestCase):

    def writtenFiles(self, config):
        for k, v in config.get('write_files', {}).items():
            yield v

    def assertConfigWritesFile(self, config, path):
        self.assertIn(path, [s['path'] for s in self.writtenFiles(config)])

    def writtenFilesMatching(self, config, pattern):
        files = list(self.writtenFiles(config))
        matching = []
        for spec in files:
            if fnmatch.fnmatch(spec['path'], pattern):
                matching.append(spec)
        return matching

    def writtenFilesMatchingContaining(self, config, pattern, content):
        matching = []
        for spec in self.writtenFilesMatching(config, pattern):
            if content in spec['content']:
                matching.append(content)
        return matching

    def configVal(self, config, path):
        cur = config
        for component in path.split('.'):
            if not isinstance(cur, dict):
                self.fail(
                    "extracting {} reached non-dict {} too early".format(
                        path, cur))
            if component not in cur:
                self.fail("no value found for {}".format(path))
            cur = cur[component]
        return cur

    def assertConfigHasVal(self, config, path, val):
        self.assertEqual(self.configVal(config, path), val)

    def assertConfigDoesNotHaveVal(self, config, path):
        cur = config
        for component in path.split('.'):
            if not isinstance(cur, dict):
                self.fail(
                    "extracting {} reached non-dict {} too early".format(
                        path, cur))
            if component not in cur:
                return
            cur = cur[component]
        self.fail("config has value {} for {}".format(cur, path))

    def test_configure(self):
        model = SubiquityModel(
            'test', ModelNames({'a', 'b'}), ModelNames(set()))
        model.set_source_variant('var')
        model.configured('a')
        self.assertFalse(model._install_event.is_set())
        model.configured('b')
        self.assertTrue(model._install_event.is_set())

    def make_model(self):
        return SubiquityModel(
            'test', INSTALL_MODEL_NAMES, POSTINSTALL_MODEL_NAMES)

    def test_proxy_set(self):
        model = self.make_model()
        proxy_val = 'http://my-proxy'
        model.proxy.proxy = proxy_val
        config = model.render('ident')
        self.assertConfigHasVal(config, 'proxy.http_proxy', proxy_val)
        self.assertConfigHasVal(config, 'proxy.https_proxy', proxy_val)
        self.assertConfigHasVal(config, 'apt.http_proxy', proxy_val)
        self.assertConfigHasVal(config, 'apt.https_proxy', proxy_val)
        confs = self.writtenFilesMatchingContaining(
            config,
            'etc/systemd/system/snapd.service.d/*.conf',
            'HTTP_PROXY=' + proxy_val)
        self.assertTrue(len(confs) > 0)

    def test_proxy_notset(self):
        model = self.make_model()
        config = model.render('ident')
        self.assertConfigDoesNotHaveVal(config, 'proxy.http_proxy')
        self.assertConfigDoesNotHaveVal(config, 'proxy.https_proxy')
        self.assertConfigDoesNotHaveVal(config, 'apt.http_proxy')
        self.assertConfigDoesNotHaveVal(config, 'apt.https_proxy')
        confs = self.writtenFilesMatchingContaining(
            config,
            'etc/systemd/system/snapd.service.d/*.conf',
            'HTTP_PROXY=')
        self.assertTrue(len(confs) == 0)

    def test_keyboard(self):
        model = self.make_model()
        config = model.render('ident')
        self.assertConfigWritesFile(config, 'etc/default/keyboard')

    def test_writes_machine_id_media_info(self):
        model_no_proxy = self.make_model()
        model_proxy = self.make_model()
        model_proxy.proxy.proxy = 'http://something'
        for model in model_no_proxy, model_proxy:
            config = model.render('ident')
            self.assertConfigWritesFile(config, 'etc/machine-id')
            self.assertConfigWritesFile(config, 'var/log/installer/media-info')

    def test_storage_version(self):
        model = self.make_model()
        config = model.render('ident')
        self.assertConfigHasVal(config, 'storage.version', 1)

    def test_write_netplan(self):
        model = self.make_model()
        config = model.render('ident')
        netplan_content = None
        for fspec in config['write_files'].values():
            if fspec['path'].startswith('etc/netplan'):
                if netplan_content is not None:
                    self.fail("writing two files to netplan?")
                netplan_content = fspec['content']
        self.assertIsNot(netplan_content, None)
        netplan = yaml.safe_load(netplan_content)
        self.assertConfigHasVal(netplan, 'network.version', 2)

    def test_has_sources(self):
        model = self.make_model()
        config = model.render('ident')
        self.assertIn('sources', config)

    def test_mirror(self):
        model = self.make_model()
        mirror_val = 'http://my-mirror'
        model.mirror.set_mirror(mirror_val)
        config = model.render('ident')
        from curtin.commands.apt_config import get_mirror
        try:
            from curtin.distro import get_architecture
        except ImportError:
            from curtin.util import get_architecture
        self.assertEqual(
            get_mirror(config["apt"], "primary", get_architecture()),
            mirror_val)
