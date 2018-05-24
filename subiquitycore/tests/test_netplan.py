import os

from subiquitycore.tests import SubiTestCase, populate_dir
from subiquitycore.netplan import configs_in_root


class TestConfigsInRoot(SubiTestCase):
    def test_masked_true(self):
        """configs_in_root masked=False should not return masked files."""
        my_dir = self.tmp_dir()
        unmasked = ['run/netplan/00base.yaml',
                    'lib/netplan/01system.yaml', 'etc/netplan/99end.yaml']
        masked = ["etc/netplan/00base.yaml"]
        populate_dir(my_dir, {f: "key: here\n" for f in unmasked + masked})
        self.assertEqual(
            [os.path.join(my_dir, p) for p in unmasked],
            configs_in_root(my_dir))

    def test_masked_false(self):
        """configs_in_root mask=True should return all configs."""
        my_dir = self.tmp_dir()
        yamls = [
            'etc/netplan/00base.yaml',
            'run/netplan/00base.yaml',
            'lib/netplan/01system.yaml',
            'etc/netplan/99end.yaml']
        populate_dir(my_dir, {f: "someyaml: here\n" for f in yamls})
        self.assertEqual(
            [os.path.join(my_dir, p) for p in yamls],
            configs_in_root(my_dir, masked=True))

    def test_only_includes_yaml(self):
        """configs_in_root should only return *.yaml files."""
        my_dir = self.tmp_dir()
        yamls = ['etc/netplan/00base.yaml', 'etc/netplan/99end.yaml']
        nonyamls = ['etc/netplan/ignored.yaml.dist', 'run/netplan/my.cfg']
        populate_dir(my_dir, {f: "someyaml: here\n" for f in yamls + nonyamls})
        self.assertEqual(
            [os.path.join(my_dir, p) for p in yamls],
            configs_in_root(my_dir))
