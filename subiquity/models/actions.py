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

import copy
import yaml


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


class DiskAction():
    def __init__(self, action_id, model, serial, ptable='gpt',
                 wipe='superblock'):
        self._action_id = action_id
        self.parent = None
        self._ptable = ptable
        self._model = model
        self._serial = serial
        self._wipe = wipe
        self._type = 'disk'

    __hash__ = None

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self._action_id == other._action_id and
                    self.parent == other.parent and
                    self._ptable == other._ptable and
                    self._model == other._model and
                    self._serial == other._serial and
                    self._wipe == other._wipe and
                    self._type == other._type)
        else:
            return False

    def get_parent(self):
        return self.parent

    @property
    def action_id(self):
        return str(self._action_id)

    @property
    def type(self):
        return self._type

    def get(self):
        action = {
            'id': self.action_id,
            'model': self._model,
            'ptable': self._ptable,
            'serial': self._serial,
            'type': self._type,
        }
        if self._wipe:
            action.update({'wipe': self._wipe})
        # if we don't have a valid serial, then we must use
        # device path, which is stored in action_id
        if self._serial in ['Unknown Serial']:
            del action['serial']
            action.update({'path': '/dev/{}'.format(self.action_id)})

        return action

    def __repr__(self):
        return str(self.get())

    def dump(self):
        return yaml.dump(self.get(), default_flow_style=False)


class RaidAction(DiskAction):
    def __init__(self, action_id, raidlevel, dev_ids, spare_ids):
        self._action_id = action_id
        self.parent = None
        self._raidlevel = raidlevel
        self._devices = dev_ids
        self._spares = spare_ids
        self._type = 'raid'

    __hash__ = None

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self._action_id == other._action_id and
                    self.parent == other.parent and
                    self._raidlevel == other._raidlevel and
                    self._devices == other._devices and
                    self._spares == other._spares and
                    self._type == other._type)
        else:
            return False

    def get(self):
        action = {
            'id': self.action_id,
            'name': self.action_id,
            'raidlevel': self._raidlevel,
            'devices': self._devices,
            'spare_devices': self._spares,
            'type': self._type,
        }
        return action


class PartitionAction(DiskAction):
    def __init__(self, parent, partnum, offset, size, flags=None):
        self.parent = parent
        self.partnum = int(partnum)
        self._offset = int(offset)
        self._size = int(size)
        self.flags = flags
        self._type = 'partition'
        self._action_id = "{}{}_part".format(self.parent.action_id,
                                             self.partnum)

        ''' rename action_id for readability '''
        if self.flags in ['bios_grub']:
            self._action_id = 'bios_boot_partition'

    __hash__ = None

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self._action_id == other._action_id and
                    self.parent == other.parent and
                    self.partnum == other.partnum and
                    self._offset == other._offset and
                    self._size == other._size and
                    self.flags == other.flags and
                    self._type == other._type)
        else:
            return False

    @property
    def path(self):
        return "{}{}".format(self.parent.action_id, self.partnum)

    @property
    def devpath(self):
        return "/dev/{}".format(self.path)

    @property
    def size(self):
        return self._size

    @property
    def offset(self):
        return self._offset

    def get(self):
        return {
            'device': self.parent.action_id,
            'flag': self.flags,
            'id': self.action_id,
            'number': self.partnum,
            'size': '{}B'.format(self.size),
            'offset': '{}B'.format(self.offset),
            'type': self._type,
        }


class BcacheAction(DiskAction):
    def __init__(self, action_id, backing_id, cache_id):
        self.parent = None
        self.backing_device = backing_id.parent.action_id
        self.cache_device = cache_id.parent.action_id
        self._action_id = action_id
        self._type = 'bcache'

    __hash__ = None

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self._action_id == other._action_id and
                    self.parent == other.parent and
                    self._backing_device == other._backing_device and
                    self._cache_device == other._cache_device and
                    self._type == other._type)
        else:
            return False

    def get(self):
        return {
            'backing_device': self.backing_device,
            'cache_device': self.cache_device,
            'id': self.action_id,
            'type': self._type,
        }


class FormatAction(DiskAction):
    def __init__(self, parent, fstype):
        self.parent = parent
        self._fstype = fstype
        self._action_id = "{}_fmt".format(self.parent.action_id)
        self._type = 'format'
        # fat filesystem require an id of <= 11 chars
        if fstype.startswith('fat'):
            self._action_id = self._action_id[:11]

    __hash__ = None

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self._action_id == other._action_id and
                    self.parent == other.parent and
                    self._fstype == other._fstype and
                    self._type == other._type)
        else:
            return False

    @property
    def fstype(self):
        return self._fstype

    def get(self):
        return {
            'volume': self.parent.action_id,
            'id': self.action_id,
            'fstype': self.fstype,
            'type': self._type,
        }


class MountAction(DiskAction):
    def __init__(self, parent, path):
        self.parent = parent
        self._path = path
        self._action_id = "{}_mnt".format(self.parent.action_id)
        self._type = 'mount'

    __hash__ = None

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self._action_id == other._action_id and
                    self.parent == other.parent and
                    self._path == other._path and
                    self._type == other._type)
        else:
            return False

    @property
    def path(self):
        return self._path

    def get(self):
        return {
            'device': self.parent.action_id,
            'id': self.action_id,
            'path': self.path,
            'type': self._type,
        }


def preserve_action(action):
    a = copy.deepcopy(action)
    a.update({'preserve': True})
    return a


def release_action(action):
    a = copy.deepcopy(action)
    if 'preserve' in action:
        del a['preserve']
    return a
