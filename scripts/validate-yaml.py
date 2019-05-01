#!/usr/bin/python3
import sys

import yaml


class StorageChecker:

    def __init__(self):
        self.actions = {}
        self.unmounted_swap_ids = set()
        self.path_to_mount = {}

    def _check_partition(self, action):
        assert 'device' in action
        assert 'size' in action
        assert action['device'] in self.actions
        assert 'ptable' in self.actions[action['device']]
        if action['flag'] in ('boot', 'bios_grub', 'prep'):
            assert self.actions[action['device']]['type'] == 'disk'

    def _check_format(self, action):
        assert 'volume' in action
        assert action['volume'] in self.actions
        if action['fstype'] == 'swap':
            self.unmounted_swap_ids.add(action['id'])

    def _check_mount(self, action):
        assert 'device' in action
        assert action['device'] in self.actions
        if not action.get('path'):
            assert self.actions[action['device']]['fstype'] == "swap"
            self.unmounted_swap_ids.remove(action['device'])
        else:
            self.path_to_mount[action['path']] = action

    def _check_raid(self, action):
        assert 'raidlevel' in action
        for d in action['devices']:
            assert d in self.actions

    def _check_lvm_volgroup(self, action):
        assert 'name' in action
        for d in action['devices']:
            assert d in self.actions

    def _check_lvm_partition(self, action):
        assert 'name' in action
        assert 'size' in action
        assert isinstance(action['size'], str)
        assert action['volgroup'] in self.actions

    def check(self, action):
        assert 'type' in action
        assert 'id' in action
        m = getattr(self, '_check_{type}'.format(**action), None)
        if m:
            m(action)
        self.actions[action['id']] = action

    def final_checks(self):
        # Check we mounted all the swap devices
        if len(self.unmounted_swap_ids) > 0:
            raise Exception(
                "some swap formats had no mounts: {}".format(
                    self.unmounted_swap_ids))

        # Check we mounted /
        assert '/' in self.path_to_mount

        # Check /boot is on a physical disk
        if '/boot' in self.path_to_mount:
            boot_mount = self.path_to_mount['/boot']
        else:
            boot_mount = self.path_to_mount['/']
        boot_fs = self.actions[boot_mount['device']]
        boot_part = self.actions[boot_fs['volume']]
        assert boot_part['type'] == 'partition', boot_part['type']
        boot_device = self.actions[boot_part['device']]
        assert boot_device['type'] == 'disk'


config = yaml.safe_load(open(sys.argv[1]))


def main():
    storage_checker = StorageChecker()

    for action in config['storage']['config']:
        try:
            storage_checker.check(action)
        except Exception:
            print('checking {} failed'.format(action))
            raise

    storage_checker.final_checks()


main()
