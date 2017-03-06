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
        1/0

    def get_parent(self):
        return self.parent

    def clear_ptable(self):
        self._ptable = None

    @property
    def action_id(self):
        return str(self._action_id)

    @property
    def id(self):
        return self.action_id

    @property
    def type(self):
        return self._type

    def get(self):
        action = {
            'id': self.action_id,
            'model': self._model,
            'serial': self._serial,
            'type': self._type,
        }
        if self._ptable:
            action['ptable'] = self._ptable
        if self._wipe:
            action['wipe'] = self._wipe
        # if we don't have a valid serial, then we must use
        # device path, which is stored in action_id
        if self._serial in ['Unknown Serial']:
            del action['serial']
            action['path'] = '/dev/{}'.format(self.action_id)

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
        1/0

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


class LVMVolGroupAction(DiskAction):
    def __init__(self, action_id, volgroup, dev_ids):
        self._action_id = action_id
        self.parent = None
        self._volgroup = volgroup
        self._devices = dev_ids
        self._type = 'lvm_volgroup'

    __hash__ = None

    def __eq__(self, other):
        1/0

    def get(self):
        action = {
            'devices': self._devices,
            'id': self.action_id,
            'name': self._volgroup,
            'type': self._type,
        }
        return action

    @property
    def volgroup(self):
        return self._volgroup

    @property
    def devices(self):
        return self._devices


class LVMPartitionAction(DiskAction):
    def __init__(self, parent, lvpartition, size):
        self.parent = parent,
        self._lvpartition = lvpartition
        self._size = size
        self._type = 'lvm_partition'
        self._action_id = "{}_{}_part".format(self.parent.action_id,
                                              self._lvpartition)

    __hash__ = None

    def __eq__(self, other):
        1/0

    def get(self):
        action = {
            'id': self.action_id,
            'name': self._lvpartition,
            'type': self._type,
            'volgroup': self.parent.action_id,
        }
        return action

    @property
    def lvpartition(self):
        return self._lvpartition

    @property
    def size(self):
        return self._size


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
        1/0

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
        self._backing_device = backing_id
        self._cache_device = cache_id
        self._action_id = action_id
        self._type = 'bcache'

    __hash__ = None

    @property
    def backing_device(self):
        return self._backing_device

    @property
    def cache_device(self):
        return self._cache_device

    def __eq__(self, other):
        1/0

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
        1/0

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
        1/0

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
    a['preserve'] = True
    return a


def release_action(action):
    a = copy.deepcopy(action)
    if 'preserve' in action:
        del a['preserve']
    return a
