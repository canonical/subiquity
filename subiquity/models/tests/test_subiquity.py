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

from subiquity.models.subiquity import SubiquityModel


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

    def test_proxy_set(self):
        model = SubiquityModel('test')
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
        model = SubiquityModel('test')
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
        model = SubiquityModel('test')
        config = model.render('ident')
        self.assertConfigWritesFile(config, 'etc/default/keyboard')

    def test_writes_machine_id_media_info(self):
        model_no_proxy = SubiquityModel('test')
        model_proxy = SubiquityModel('test')
        model_proxy.proxy.proxy = 'http://something'
        for model in model_no_proxy, model_proxy:
            config = model.render('ident')
            self.assertConfigWritesFile(config, 'etc/machine-id')
            self.assertConfigWritesFile(config, 'var/log/installer/media-info')

    def test_storage_version(self):
        model = SubiquityModel('test')
        config = model.render('ident')
        self.assertConfigHasVal(config, 'storage.version', 1)

    def test_network_version(self):
        model = SubiquityModel('test')
        config = model.render('ident')
        self.assertConfigHasVal(config, 'network.version', 2)

    def test_has_sources(self):
        model = SubiquityModel('test')
        config = model.render('ident')
        self.assertIn('sources', config)

    def test_mirror(self):
        model = SubiquityModel('test')
        mirror_val = 'http://my-mirror'
        model.mirror.set_mirror(mirror_val)
        config = model.render('ident')
        from curtin.commands.apt_config import get_mirror
        from curtin.util import get_architecture
        self.assertEqual(
            get_mirror(config["apt"], "primary", get_architecture()),
            mirror_val)
