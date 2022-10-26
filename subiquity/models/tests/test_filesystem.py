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

import unittest
from unittest import mock

import attr
from parameterized import parameterized

from subiquity.models.filesystem import (
    Bootloader,
    dehumanize_size,
    Disk,
    Filesystem,
    FilesystemModel,
    get_raid_size,
    humanize_size,
    NotFinalPartitionError,
    Partition,
    align_down,
    LVM_CHUNK_SIZE,
    )
from subiquity.common.filesystem import gaps


class TestHumanizeSize(unittest.TestCase):

    basics = [
        ('1.000M', 2**20),
        ('1.500M', 2**20+2**19),
        ('1.500M', 2**20+2**19),
        ('1023.000M', 1023*2**20),
        ('1.000G', 1024*2**20),
        ]

    def test_basics(self):
        for string, integer in self.basics:
            with self.subTest(input=string):
                self.assertEqual(string, humanize_size(integer))


class TestDehumanizeSize(unittest.TestCase):

    basics = [
        ('1', 1),
        ('134', 134),

        ('0.5B', 0),  # Does it make sense to allow this?
        ('1B', 1),

        ('1K', 2**10),
        ('1k', 2**10),
        ('0.5K', 2**9),
        ('2.125K', 2**11 + 2**7),

        ('1M', 2**20),
        ('1m', 2**20),
        ('0.5M', 2**19),
        ('2.125M', 2**21 + 2**17),

        ('1G', 2**30),
        ('1g', 2**30),
        ('0.25G', 2**28),
        ('2.5G', 2**31 + 2**29),

        ('1T', 2**40),
        ('1t', 2**40),
        ('4T', 2**42),
        ('4.125T', 2**42 + 2**37),

        ('1P', 2**50),
        ('1P', 2**50),
        ('0.5P', 2**49),
        ('1.5P', 2**50 + 2**49),
        ]

    def test_basics(self):
        for input, expected_output in self.basics:
            with self.subTest(input=input):
                self.assertEqual(expected_output, dehumanize_size(input))

    errors = [
        ('', "input cannot be empty"),
        ('1u', "unrecognized suffix 'u' in '1u'"),
        ('-1', "'-1': cannot be negative"),
        ('1.1.1', "'1.1.1' is not valid input"),
        ('1rm', "'1rm' is not valid input"),
        ('1e6M', "'1e6M' is not valid input"),
        ]

    def test_errors(self):
        for input, expected_error in self.errors:
            with self.subTest(input=input):
                try:
                    dehumanize_size(input)
                except ValueError as e:
                    actual_error = str(e)
                else:
                    self.fail(
                        "dehumanize_size({!r}) did not error".format(input))
                self.assertEqual(expected_error, actual_error)


@attr.s
class FakeDev:

    size = attr.ib()
    id = attr.ib(default="id")


class TestRoundRaidSize(unittest.TestCase):

    def test_lp1816777(self):

        self.assertLessEqual(
            get_raid_size("raid1", [FakeDev(500107862016)]*2),
            499972571136)


@attr.s
class FakeStorageInfo:
    name = attr.ib(default=None)
    size = attr.ib(default=None)
    free = attr.ib(default=None)
    serial = attr.ib(default=None)
    model = attr.ib(default=None)
    raw = attr.ib(default=attr.Factory(dict))


def make_model(bootloader=None, storage_version=None):
    model = FilesystemModel()
    if bootloader is not None:
        model.bootloader = bootloader
    if storage_version is not None:
        model.storage_version = storage_version
    model._probe_data = {}
    return model


def make_disk(fs_model=None, **kw):
    if fs_model is None:
        fs_model = make_model()
    if 'serial' not in kw:
        kw['serial'] = 'serial%s' % len(fs_model._actions)
    if 'path' not in kw:
        kw['path'] = '/dev/thing%s' % len(fs_model._actions)
    if 'ptable' not in kw:
        kw['ptable'] = 'gpt'
    size = kw.pop('size', 100*(2**30))
    fs_model._actions.append(Disk(
        m=fs_model, info=FakeStorageInfo(size=size), **kw))
    disk = fs_model._actions[-1]
    return disk


def make_model_and_disk(bootloader=None, **kw):
    model = make_model(bootloader)
    return model, make_disk(model, **kw)


def make_partition(model, device=None, *, preserve=False, size=None,
                   offset=None, **kw):
    flag = kw.pop('flag', None)
    if device is None:
        device = make_disk(model)
    if size is None or offset is None:
        gap = gaps.largest_gap(device)
        if size is None:
            size = gap.size//2
        if offset is None:
            offset = gap.offset
    partition = Partition(m=model, device=device, size=size, offset=offset,
                          preserve=preserve, flag=flag, **kw)
    model._actions.append(partition)
    return partition


def make_filesystem(model, *, partition, **kw):
    return Filesystem(m=model, volume=partition, **kw)


def make_model_and_partition(bootloader=None):
    model, disk = make_model_and_disk(bootloader)
    return model, make_partition(model, disk)


def make_raid(model):
    name = 'md%s' % len(model._actions)
    return model.add_raid(
        name, 'raid1', {make_disk(model), make_disk(model)}, set())


def make_model_and_raid(bootloader=None):
    model = make_model(bootloader)
    return model, make_raid(model)


def make_vg(model, pvs=None):
    name = 'vg%s' % len(model._actions)

    if pvs is None:
        pvs = {make_disk(model)}

    return model.add_volgroup(name, pvs)


def make_model_and_vg(bootloader=None):
    model = make_model(bootloader)
    return model, make_vg(model)


def make_lv(model, vg=None, size=None):
    if vg is None:
        vg = make_vg(model)
    name = 'lv%s' % len(model._actions)
    size = gaps.largest_gap_size(vg) if size is None else size
    return model.add_logical_volume(vg, name, size)


def make_model_and_lv(bootloader=None, lv_size=None):
    model = make_model(bootloader)
    return model, make_lv(model, size=lv_size)


class TestFilesystemModel(unittest.TestCase):

    def _test_ok_for_xxx(self, model, make_new_device, attr,
                         test_partitions=True):
        # Newly formatted devs are ok_for_raid
        dev1 = make_new_device()
        self.assertTrue(getattr(dev1, attr))
        # A freshly formatted dev is not ok_for_raid
        dev2 = make_new_device()
        model.add_filesystem(dev2, 'ext4')
        self.assertFalse(getattr(dev2, attr))
        if test_partitions:
            # A device with a partition is not ok_for_raid
            dev3 = make_new_device()
            make_partition(model, dev3)
            self.assertFalse(getattr(dev3, attr))
        # Empty existing devices are ok
        dev4 = make_new_device()
        dev4.preserve = True
        self.assertTrue(getattr(dev4, attr))
        # A dev with an existing filesystem is ok (there is no
        # way to remove the format)
        dev5 = make_new_device()
        dev5.preserve = True
        fs = model.add_filesystem(dev5, 'ext4')
        fs.preserve = True
        self.assertTrue(dev5.ok_for_raid)
        # But a existing, *mounted* filesystem is not.
        model.add_mount(fs, '/')
        self.assertFalse(dev5.ok_for_raid)

    def test_disk_ok_for_xxx(self):
        model = make_model()
        self._test_ok_for_xxx(
            model, lambda: make_disk(model), "ok_for_raid")
        self._test_ok_for_xxx(
            model, lambda: make_disk(model), "ok_for_lvm_vg")

    def test_partition_ok_for_xxx(self):
        model = make_model()

        def make_new_device():
            return make_partition(model)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_raid", False)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_lvm_vg", False)

        part = make_partition(make_model(Bootloader.BIOS), flag='bios_grub')
        self.assertFalse(part.ok_for_raid)
        self.assertFalse(part.ok_for_lvm_vg)
        part = make_partition(make_model(Bootloader.UEFI), flag='boot')
        self.assertFalse(part.ok_for_raid)
        self.assertFalse(part.ok_for_lvm_vg)
        part = make_partition(make_model(Bootloader.PREP), flag='prep')
        self.assertFalse(part.ok_for_raid)
        self.assertFalse(part.ok_for_lvm_vg)

    def test_raid_ok_for_xxx(self):
        model = make_model()

        def make_new_device():
            return make_raid(model)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_raid", False)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_lvm_vg", False)

    def test_vg_ok_for_xxx(self):
        model, vg = make_model_and_vg()
        self.assertFalse(vg.ok_for_raid)
        self.assertFalse(vg.ok_for_lvm_vg)

    def test_lv_ok_for_xxx(self):
        model, lv = make_model_and_lv()
        self.assertFalse(lv.ok_for_raid)
        self.assertFalse(lv.ok_for_lvm_vg)


def fake_up_blockdata_disk(disk, **kw):
    model = disk._m
    if model._probe_data is None:
        model._probe_data = {}
    blockdev = model._probe_data.setdefault('blockdev', {})
    d = blockdev[disk.path] = {
        'DEVTYPE': 'disk',
        'ID_SERIAL': disk.serial,
        'ID_MODEL': disk.model,
        'attrs': {
            'size': disk.size,
            },
        }
    d.update(kw)


def fake_up_blockdata(model):
    for disk in model.all_disks():
        fake_up_blockdata_disk(disk)


class TestAutoInstallConfig(unittest.TestCase):

    def test_basic(self):
        model, disk = make_model_and_disk()
        fake_up_blockdata(model)
        model.apply_autoinstall_config([{'type': 'disk', 'id': 'disk0'}])
        [new_disk] = model.all_disks()
        self.assertIsNot(new_disk, disk)
        self.assertEqual(new_disk.serial, disk.serial)

    def test_largest(self):
        model = make_model()
        make_disk(model, serial='smaller', size=10*(2**30))
        make_disk(model, serial='larger', size=11*(2**30))
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'match': {
                    'size': 'largest',
                    },
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "larger")

    def test_smallest(self):
        model = make_model()
        make_disk(model, serial='smaller', size=10*(2**30))
        make_disk(model, serial='larger', size=11*(2**30))
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'match': {
                    'size': 'smallest',
                    },
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "smaller")

    def test_smallest_skips_zero_size(self):
        model = make_model()
        make_disk(model, serial='smallest', size=0)
        make_disk(model, serial='smaller', size=10*(2**30))
        make_disk(model, serial='larger', size=11*(2**30))
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'match': {
                    'size': 'smallest',
                    },
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "smaller")

    def test_serial_exact(self):
        model = make_model()
        make_disk(model, serial='aaaa', path='/dev/aaa')
        make_disk(model, serial='bbbb', path='/dev/bbb')
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'serial': 'aaaa',
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.path, "/dev/aaa")

    def test_serial_glob(self):
        model = make_model()
        make_disk(model, serial='aaaa', path='/dev/aaa')
        make_disk(model, serial='bbbb', path='/dev/bbb')
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'match': {
                    'serial': 'a*',
                    },
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.path, "/dev/aaa")

    def test_path_exact(self):
        model = make_model()
        make_disk(model, serial='aaaa', path='/dev/aaa')
        make_disk(model, serial='bbbb', path='/dev/bbb')
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'path': '/dev/aaa',
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "aaaa")

    def test_path_glob(self):
        model = make_model()
        d1 = make_disk(model, serial='aaaa', path='/dev/aaa')
        d2 = make_disk(model, serial='bbbb', path='/dev/bbb')
        fake_up_blockdata_disk(d1)
        fake_up_blockdata_disk(d2)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'match': {
                    'path': '/dev/a*',
                    },
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_model_glob(self):
        model = make_model()
        d1 = make_disk(model, serial='aaaa')
        d2 = make_disk(model, serial='bbbb')
        fake_up_blockdata_disk(d1, ID_MODEL='aaa')
        fake_up_blockdata_disk(d2, ID_MODEL='bbb')
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'match': {
                    'model': 'a*',
                    },
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_vendor_glob(self):
        model = make_model()
        d1 = make_disk(model, serial='aaaa')
        d2 = make_disk(model, serial='bbbb')
        fake_up_blockdata_disk(d1, ID_VENDOR='aaa')
        fake_up_blockdata_disk(d2, ID_VENDOR='bbb')
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
                'match': {
                    'vendor': 'a*',
                    },
            },
            ])
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_no_matching_disk(self):
        model = make_model()
        make_disk(model, serial='bbbb')
        fake_up_blockdata(model)
        with self.assertRaises(Exception) as cm:
            model.apply_autoinstall_config([{
                    'type': 'disk',
                    'id': 'disk0',
                    'serial': 'aaaa',
                }])
        self.assertIn("matched no disk", str(cm.exception))

    def test_reuse_disk(self):
        model = make_model()
        make_disk(model, serial='aaaa')
        fake_up_blockdata(model)
        with self.assertRaises(Exception) as cm:
            model.apply_autoinstall_config([{
                    'type': 'disk',
                    'id': 'disk0',
                    'serial': 'aaaa',
                },
                {
                    'type': 'disk',
                    'id': 'disk0',
                    'serial': 'aaaa',
                }])
        self.assertIn("was already used", str(cm.exception))

    def test_partition_percent(self):
        model = make_model()
        make_disk(model, serial='aaaa', size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
            },
            {
                'type': 'partition',
                'id': 'part0',
                'device': 'disk0',
                'size': '50%',
            }])
        disk = model._one(type="disk")
        part = model._one(type="partition")
        self.assertEqual(part.size, disk.available_for_partitions//2)

    def test_partition_remaining(self):
        model = make_model()
        make_disk(model, serial='aaaa', size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
            },
            {
                'type': 'partition',
                'id': 'part0',
                'device': 'disk0',
                'size': dehumanize_size('50M'),
            },
            {
                'type': 'partition',
                'id': 'part1',
                'device': 'disk0',
                'size': -1,
            },
            ])
        disk = model._one(type="disk")
        part1 = model._one(type="partition", id="part1")
        self.assertEqual(
            part1.size, disk.available_for_partitions - dehumanize_size('50M'))

    def test_partition_not_final_remaining_size(self):
        model = make_model()
        make_disk(model, serial='aaaa', size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        with self.assertRaises(NotFinalPartitionError):
            model.apply_autoinstall_config([
                {
                    'type': 'disk',
                    'id': 'disk0',
                },
                {
                    'type': 'partition',
                    'id': 'part0',
                    'device': 'disk0',
                    'size': dehumanize_size('50M'),
                },
                {
                    'type': 'partition',
                    'id': 'part1',
                    'device': 'disk0',
                    'size': -1,
                },
                {
                    'type': 'partition',
                    'id': 'part2',
                    'device': 'disk0',
                    'size': dehumanize_size('10M'),
                },
                ])

    def test_extended_partition_remaining_size(self):
        model = make_model(bootloader=Bootloader.BIOS, storage_version=2)
        disk = make_disk(model, serial='aaaa', size=dehumanize_size("100M"),
                         ptable='msdos')
        ebr_space = disk.alignment_data().ebr_space
        start_offset = disk.alignment_data().min_start_offset

        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
            },
            {
                'type': 'partition',
                'id': 'part0',
                'device': 'disk0',
                'size': dehumanize_size('40M'),
                'offset': start_offset,
            },
            {
                'type': 'partition',
                'id': 'part1',
                'device': 'disk0',
                'size': -1,
                'flag': 'extended',
                # p0 offset + p0 size
                'offset': start_offset + dehumanize_size('40M'),
            },
            {
                'type': 'partition',
                'number': 5,
                'id': 'part5',
                'device': 'disk0',
                'size': dehumanize_size('10M'),
                'flag': 'logical',
                # p1 (extended) offset + ebr_space
                'offset': start_offset + dehumanize_size('40M') + ebr_space,
            },
            ])
        extended = model._one(type="partition", id="part1")
        self.assertEqual(
                extended.size,
                disk.available_for_partitions - dehumanize_size('40M'))

    def test_logical_partition_remaining_size(self):
        model = make_model(bootloader=Bootloader.BIOS, storage_version=2)
        disk = make_disk(model, serial='aaaa', size=dehumanize_size("100M"),
                         ptable='msdos')
        ebr_space = disk.alignment_data().ebr_space
        start_offset = disk.alignment_data().min_start_offset

        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
            },
            {
                'type': 'partition',
                'id': 'part0',
                'device': 'disk0',
                'size': dehumanize_size('40M'),
                'flag': 'extended',
                'offset': start_offset,
            },
            {
                'type': 'partition',
                'number': 5,
                'id': 'part5',
                'device': 'disk0',
                'size': -1,
                'flag': 'logical',
                # p0 (extended) offset + ebr_space
                'offset': start_offset + ebr_space,
            },
            ])
        extended = model._one(type="partition", id="part0")
        logical = model._one(type="partition", id="part5")
        # At this point, there should be one large gap outside the extended
        # partition and one smaller one inside the extended partition.
        # Make sure our logical partition picks up the smaller one.
        self.assertEqual(logical.size, extended.size - ebr_space)

    def test_partition_remaining_size_in_extended_and_logical(self):
        model = make_model(bootloader=Bootloader.BIOS, storage_version=2)
        disk = make_disk(model, serial='aaaa', size=dehumanize_size("100M"),
                         ptable='msdos')
        ebr_space = disk.alignment_data().ebr_space
        start_offset = disk.alignment_data().min_start_offset
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
            },
            {
                'type': 'partition',
                'id': 'part0',
                'device': 'disk0',
                'size': dehumanize_size('40M'),
                'offset': start_offset,
            },
            {
                'type': 'partition',
                'id': 'part1',
                'device': 'disk0',
                'size': -1,
                'flag': 'extended',
                # p0 offset + size of p0
                'offset': start_offset + dehumanize_size('40M'),
            },
            {
                'type': 'partition',
                'number': 5,
                'id': 'part5',
                'device': 'disk0',
                'size': dehumanize_size('10M'),
                'flag': 'logical',
                # p1 offset + ebr_space
                'offset': start_offset + dehumanize_size('40M') + ebr_space,
            },
            {
                'type': 'partition',
                'number': 6,
                'id': 'part6',
                'device': 'disk0',
                'size': -1,
                'flag': 'logical',
                # p5 offset + p5 size + ebr_space
                'offset': start_offset + dehumanize_size('40M') + ebr_space \
                        + dehumanize_size('10M') + ebr_space
            },
            ])
        extended = model._one(type="partition", id="part1")
        p5 = model._one(type="partition", id="part5")
        p6 = model._one(type="partition", id="part6")
        self.assertEqual(
                extended.size,
                disk.available_for_partitions - dehumanize_size('40M'))
        self.assertEqual(
                p6.size,
                extended.size - p5.size - 2 * ebr_space)

    def test_lv_percent(self):
        model = make_model()
        make_disk(model, serial='aaaa', size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
            },
            {
                'type': 'lvm_volgroup',
                'id': 'vg0',
                'name': 'vg0',
                'devices': ['disk0'],
            },
            {
                'type': 'lvm_partition',
                'id': 'lv1',
                'name': 'lv1',
                'volgroup': 'vg0',
                'size': "50%",
            },
            ])
        vg = model._one(type="lvm_volgroup")
        lv1 = model._one(type="lvm_partition")
        self.assertEqual(lv1.size, vg.available_for_partitions//2)

    def test_lv_remaining(self):
        model = make_model()
        make_disk(model, serial='aaaa', size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config([
            {
                'type': 'disk',
                'id': 'disk0',
            },
            {
                'type': 'lvm_volgroup',
                'id': 'vg0',
                'name': 'vg0',
                'devices': ['disk0'],
            },
            {
                'type': 'lvm_partition',
                'id': 'lv1',
                'name': 'lv1',
                'volgroup': 'vg0',
                'size': dehumanize_size("50M"),
            },
            {
                'type': 'lvm_partition',
                'id': 'lv2',
                'name': 'lv2',
                'volgroup': 'vg0',
                'size': -1,
            },
            ])
        vg = model._one(type="lvm_volgroup")
        lv2 = model._one(type="lvm_partition", id='lv2')
        self.assertEqual(
            lv2.size, align_down(
                vg.available_for_partitions - dehumanize_size("50M"),
                LVM_CHUNK_SIZE))

    def test_render_does_not_include_unreferenced(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk2 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True)
        disk2p1 = make_partition(model, disk2, preserve=True)
        fs = model.add_filesystem(disk1p1, 'ext4')
        model.add_mount(fs, '/')
        rendered_ids = {action['id'] for action in model._render_actions()}
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(disk2.id not in rendered_ids)
        self.assertTrue(disk2p1.id not in rendered_ids)

    def test_render_includes_all_partitions(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True,
                                 offset=1 << 20, size=512 << 20)
        disk1p2 = make_partition(model, disk1, preserve=True,
                                 offset=513 << 20, size=8192 << 20)
        fs = model.add_filesystem(disk1p2, 'ext4')
        model.add_mount(fs, '/')
        rendered_ids = {action['id'] for action in model._render_actions()}
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(disk1p2.id in rendered_ids)

    def test_render_numbers_existing_partitions(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True)
        fs = model.add_filesystem(disk1p1, 'ext4')
        model.add_mount(fs, '/')
        actions = model._render_actions()
        for action in actions:
            if action['id'] != disk1p1.id:
                continue
            self.assertEqual(action['number'], 1)

    def test_render_includes_unmounted_new_partition(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk2 = make_disk(model)
        disk1p1 = make_partition(model, disk1, preserve=True)
        disk2p1 = make_partition(model, disk2)
        fs = model.add_filesystem(disk1p1, 'ext4')
        model.add_mount(fs, '/')
        rendered_ids = {action['id'] for action in model._render_actions()}
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(disk2.id in rendered_ids)
        self.assertTrue(disk2p1.id in rendered_ids)


class TestPartitionNumbering(unittest.TestCase):
    def setUp(self):
        self.cur_idx = 1

    def assert_next(self, part):
        self.assertEqual(self.cur_idx, part.number)
        self.cur_idx += 1

    def test_gpt(self):
        m, d1 = make_model_and_disk(ptable='gpt')
        for _ in range(8):
            self.assert_next(make_partition(m, d1))

    @parameterized.expand([
        ['msdos', 4],
        ['vtoc', 3],
    ])
    def test_all_primary(self, ptable, primaries):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        for _ in range(primaries):
            self.assert_next(make_partition(m, d1))

    @parameterized.expand([
        ['msdos', 4],
        ['vtoc', 3],
    ])
    def test_primary_and_extended(self, ptable, primaries):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        for _ in range(primaries - 1):
            self.assert_next(make_partition(m, d1))
        size = gaps.largest_gap_size(d1)
        self.assert_next(make_partition(m, d1, flag='extended', size=size))
        for _ in range(3):
            self.assert_next(make_partition(m, d1, flag='logical'))

    @parameterized.expand(
        [[pt, primaries, i]
         for pt, primaries in (('msdos', 4), ('vtoc', 3))
         for i in range(3)]
    )
    def test_delete_logical(self, ptable, primaries, idx_to_remove):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        self.assert_next(make_partition(m, d1))
        size = gaps.largest_gap_size(d1)
        self.assert_next(make_partition(m, d1, flag='extended', size=size))
        self.cur_idx = primaries + 1
        parts = [make_partition(m, d1, flag='logical') for _ in range(3)]
        for p in parts:
            self.assert_next(p)
        to_remove = parts.pop(idx_to_remove)
        m.remove_partition(to_remove)
        self.cur_idx = primaries + 1
        for p in parts:
            self.assert_next(p)

    @parameterized.expand(
        [[pt, primaries, i]
         for pt, primaries in (('msdos', 4), ('vtoc', 3))
         for i in range(3)]
    )
    def test_out_of_offset_order(self, ptable, primaries, idx_to_remove):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable, size=100 << 20)
        self.assert_next(make_partition(m, d1, size=10 << 20))
        size = gaps.largest_gap_size(d1)
        self.assert_next(make_partition(m, d1, flag='extended', size=size))
        self.cur_idx = primaries + 1
        parts = []
        parts.append(make_partition(
                m, d1, flag='logical', size=9 << 20, offset=30 << 20))
        parts.append(make_partition(
                m, d1, flag='logical', size=9 << 20, offset=20 << 20))
        parts.append(make_partition(
                m, d1, flag='logical', size=9 << 20, offset=40 << 20))
        for p in parts:
            self.assert_next(p)
        to_remove = parts.pop(idx_to_remove)
        m.remove_partition(to_remove)
        self.cur_idx = primaries + 1
        for p in parts:
            self.assert_next(p)

    @parameterized.expand([
        [1, 'msdos', 4],
        [1, 'vtoc', 3],
        [2, 'msdos', 4],
        [2, 'vtoc', 3],
    ])
    def test_no_extra_primary(self, sv, ptable, primaries):
        m = make_model(storage_version=sv)
        d1 = make_disk(m, ptable=ptable, size=100 << 30)
        for _ in range(primaries):
            self.assert_next(make_partition(m, d1, size=1 << 30))
        with self.assertRaises(Exception):
            make_partition(m, d1)

    @parameterized.expand([['gpt'], ['msdos'], ['vtoc']])
    def test_p1_preserved(self, ptable):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        p1 = make_partition(m, d1, preserve=True, number=1)
        p2 = make_partition(m, d1)
        p3 = make_partition(m, d1)
        self.assertEqual(1, p1.number)
        self.assertEqual(True, p1.preserve)
        self.assertEqual(2, p2.number)
        self.assertEqual(False, p2.preserve)
        self.assertEqual(3, p3.number)
        self.assertEqual(False, p3.preserve)

    @parameterized.expand([['gpt'], ['msdos'], ['vtoc']])
    def test_p2_preserved(self, ptable):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        p2 = make_partition(m, d1, preserve=True, number=2)
        p1 = make_partition(m, d1)
        p3 = make_partition(m, d1)
        self.assertEqual(1, p1.number)
        self.assertEqual(False, p1.preserve)
        self.assertEqual(2, p2.number)
        self.assertEqual(True, p2.preserve)
        self.assertEqual(3, p3.number)
        self.assertEqual(False, p3.preserve)


class TestAlignmentData(unittest.TestCase):
    @parameterized.expand([['gpt'], ['msdos'], ['vtoc']])
    def test_alignment_gaps_coherence(self, ptable):
        d1 = make_disk(ptable=ptable)
        ad = d1.alignment_data()
        align_max = d1.size - ad.min_start_offset - ad.min_end_offset
        self.assertEqual(gaps.largest_gap_size(d1), align_max)


class TestSwap(unittest.TestCase):
    def test_basic(self):
        m = make_model()
        with mock.patch.object(m, '_should_add_swapfile', return_value=False):
            cfg = m.render()
            self.assertEqual({'size': 0}, cfg['swap'])
