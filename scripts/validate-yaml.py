#!/usr/bin/python3
import sys

import yaml


class StorageChecker:

    def __init__(self):
        self.actions = {}
        self.unmounted_swap_ids = set()

    def _check_partition(self, action):
        assert 'device' in action
        assert action['device'] in self.actions
        assert 'ptable' in self.actions[action['device']]

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

    def check(self, action):
        assert 'type' in action
        assert 'id' in action
        m = getattr(self, '_check_{type}'.format(**action), None)
        if m:
            m(action)
        self.actions[action['id']] = action

    def final_checks(self):
        if len(self.unmounted_swap_ids) > 0:
            raise Exception(
                "some swap formats had no mounts: {}".format(
                    self.unmounted_swap_ids))


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
