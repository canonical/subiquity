# Copyright 2015 Canonical, Ltd.
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


class NetAction():
    def __init__(self, **options):
        self._action_keys = ['type', 'name', 'params', 'subnets']
        self.params = {}
        self.subnets = []
        for k, v in options.items():
            setattr(self, k, v)

    def get(self):
        action = {k: v for k, v in self.__dict__.items()
                  if k in self._action_keys}
        return action


class PhysicalAction(NetAction):
    def __init__(self, **options):
        options['type'] = 'physical'
        if 'name' not in options or len(options['name']) == 0:
            raise Exception('Invalid name for {}'.format(
                self.__class__.__name__))
        if 'mac_address' not in options:
            raise Exception('{} requires a valid mac_address attr'.format(
                self.__class__.__name__))
        super().__init__(**options)
        self._action_keys.extend(['mac_address'])


class BridgeAction(NetAction):
    def __init__(self, **options):
        options['type'] = 'bridge'
        if 'name' not in options or len(options['name']) == 0:
            raise Exception('Invalid name for {}'.format(
                self.__class__.__name__))
        if 'bridge_interfaces' not in options:
            raise Exception('{} requires bridge_interfaces attr'.format(
                self.__class__.__name__))
        super().__init__(**options)
        self._action_keys.extend(['bridge_interfaces'])


class VlanAction(NetAction):
    def __init__(self, **options):
        options['type'] = 'vlan'
        if 'name' not in options or len(options['name']) == 0:
            raise Exception('Invalid name for {}'.format(
                self.__class__.__name__))
        if 'vlan_id' not in options or 'vlan_link' not in options:
            raise Exception('{} requires vlan_id and vlan_link attr'.format(
                self.__class__.__name__))
        super().__init__(**options)
        self._action_keys.extend(['vlan_id', 'vlan_link'])


class BondAction(NetAction):
    def __init__(self, **options):
        options['type'] = 'bond'
        if 'name' not in options or len(options['name']) == 0:
            raise Exception('Invalid name for {}'.format(
                self.__class__.__name__))
        if 'bond_interfaces' not in options:
            raise Exception('{} requires bond_interfaces attr'.format(
                self.__class__.__name__))
        super().__init__(**options)
        self._action_keys.extend(['bond_interfaces'])


class RouteAction(NetAction):
    def __init__(self, **options):
        options['type'] = 'route'
        if 'gateway' not in options:
            raise Exception('{} requires a valid gateway attr'.format(
                self.__class__.__name__))
        super().__init__(**options)
        self._action_keys.extend(['gateway'])
