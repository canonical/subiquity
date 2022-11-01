# Copyright 2021 Canonical, Ltd.
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

import aiohttp
from aiohttp.client_exceptions import ClientResponseError
import async_timeout
import asyncio
import contextlib
from functools import wraps
import json
import os
import tempfile
from unittest.mock import patch
from urllib.parse import unquote

from subiquitycore.tests import SubiTestCase
from subiquitycore.utils import astart_command

default_timeout = 10


def find(items, key, value):
    for item in items:
        if key in item and item[key] == value:
            yield item


def first(items, key, value):
    return next(find(items, key, value))


def match(items, **kw):
    typename = kw.pop('_type', None)
    if typename is not None:
        kw['$type'] = typename
    return [item for item in items
            if all(item.get(k) == v for k, v in kw.items())]


def timeout(multiplier=1):
    def wrapper(coro):
        @wraps(coro)
        async def run(*args, **kwargs):
            async with async_timeout.timeout(default_timeout * multiplier):
                return await coro(*args, **kwargs)
        return run
    return wrapper


def json_print(json_data):
    print(json.dumps(json_data, indent=4))


class Client:
    def __init__(self, session):
        self.session = session

    def loads(self, data):
        if data == '' or data is None:  # json.loads likes neither of these
            return None
        return json.loads(data)

    def dumps(self, data):
        # if the data we're dumping is literally False,
        # we want that to be 'false'
        if data or isinstance(data, bool):
            return json.dumps(data, separators=(',', ':'))
        elif data is not None:
            return '""'
        else:
            return data

    async def get(self, query, **kwargs):
        return await self.request('GET', query, **kwargs)

    async def post(self, query, data=None, **kwargs):
        return await self.request('POST', query, data, **kwargs)

    async def request(self, method, query, data=None, **kwargs):
        params = {k: self.dumps(v) for k, v in kwargs.items()}
        data = self.dumps(data)
        async with self.session.request(method, f'http://a{query}',
                                        data=data, params=params) as resp:
            print(unquote(str(resp.url)))
            content = await resp.content.read()
            content = content.decode()
            if 400 <= resp.status:
                print(content)
                resp.raise_for_status()
            return self.loads(content)

    async def poll_startup(self):
        for _ in range(default_timeout * 10):
            try:
                resp = await self.get('/meta/status')
                if resp["state"] in ('STARTING_UP', 'CLOUD_INIT_WAIT',
                                     'EARLY_COMMANDS'):
                    await asyncio.sleep(.5)
                    continue
                if resp["state"] == 'ERROR':
                    raise Exception('server in error state')
                return
            except aiohttp.client_exceptions.ClientConnectorError:
                await asyncio.sleep(.5)
        raise Exception('timeout on server startup')


class Server(Client):
    async def server_shutdown(self, immediate=True):
        try:
            await self.post('/shutdown', mode='POWEROFF', immediate=immediate)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            return

    async def spawn(self, output_base, socket, machine_config,
                    bootloader='uefi', extra_args=None):
        env = os.environ.copy()
        env['SUBIQUITY_REPLAY_TIMESCALE'] = '100'
        cmd = ['python3', '-m', 'subiquity.cmd.server',
               '--dry-run',
               '--bootloader', bootloader,
               '--socket', socket,
               '--output-base', output_base,
               '--machine-config', machine_config]
        if extra_args is not None:
            cmd.extend(extra_args)
        self.proc = await astart_command(cmd, env=env)

    async def close(self):
        try:
            await asyncio.wait_for(self.server_shutdown(), timeout=5.0)
            await asyncio.wait_for(self.proc.communicate(), timeout=5.0)
        except asyncio.exceptions.TimeoutError:
            pass
        finally:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass


class SystemSetupServer(Server):
    async def spawn(self, output_base, socket, machine_config,
                    bootloader='uefi', extra_args=None):
        env = os.environ.copy()
        env['SUBIQUITY_REPLAY_TIMESCALE'] = '100'
        cmd = ['python3', '-m', 'system_setup.cmd.server',
               '--dry-run', '--socket', socket, '--output-base', output_base]
        root = os.path.abspath(output_base)
        conffile = os.path.join(root, "etc/wsl.conf")
        os.makedirs(os.path.dirname(conffile), exist_ok=True)
        # The server should crash in the presence of a non-empty conf file.
        with open(conffile, "w+") as f:
            f.write("[automount]\noptions=metadata")

        if extra_args is not None:
            cmd.extend(extra_args)
        self.proc = await astart_command(cmd, env=env)


class TestAPI(SubiTestCase):
    class _MachineConfig(os.PathLike):
        def __init__(self, outer, path):
            self.outer = outer
            self.orig_path = path
            self.path = None

        def __fspath__(self):
            return self.path or self.orig_path

        @contextlib.contextmanager
        def edit(self):
            with open(self.orig_path, 'r') as fp:
                data = json.load(fp)
            yield data
            self.path = self.outer.tmp_path('machine-config.json')
            with open(self.path, 'w') as fp:
                json.dump(data, fp)

    def machineConfig(self, path):
        return self._MachineConfig(self, path)

    def assertDictSubset(self, expected, actual):
        """All keys in dictionary expected, and matching values, must match
        keys and values in actual.  Actual may contain additional keys and
        values that don't appear in expected, and this is not a failure."""

        for k, v in expected.items():
            self.assertEqual(v, actual[k], k)


async def poll_for_socket_exist(socket_path):
    for _ in range(default_timeout * 5):
        # test level timeout will trigger first, this loop is just a fallback
        if os.path.exists(socket_path):
            return
        await asyncio.sleep(.1)
    raise Exception('timeout looking for socket to exist')


@contextlib.contextmanager
def tempdirs(*args, **kwargs):
    # This does the following:
    # * drop in replacement for TemporaryDirectory that doesn't cleanup, so
    #   that the log files can be examined later
    # * make it an otherwise-unnecessary contextmanager so that the indentation
    #   of the caller can be preserved
    prefix = '/tmp/testapi/'
    os.makedirs(prefix, exist_ok=True)
    tempdir = tempfile.mkdtemp(prefix=prefix)
    print(tempdir)
    yield tempdir


@contextlib.asynccontextmanager
async def start_server_factory(factory, *args, **kwargs):
    with tempfile.TemporaryDirectory() as tempdir:
        socket_path = f'{tempdir}/socket'
        conn = aiohttp.UnixConnector(path=socket_path)
        async with aiohttp.ClientSession(connector=conn) as session:
            server = factory(session)
            try:
                await server.spawn(tempdir, socket_path, *args, **kwargs)
                await poll_for_socket_exist(socket_path)
                await server.poll_startup()
                yield server
            finally:
                await server.close()


@contextlib.asynccontextmanager
async def start_server(*args, **kwargs):
    async with start_server_factory(Server, *args, **kwargs) as instance:
        sources = await instance.get('/source')
        await instance.post(
            '/source', source_id=sources['sources'][0]['id'])
        while True:
            resp = await instance.get('/storage/v2')
            print(resp)
            if resp['status'] != 'PROBING':
                break
            await asyncio.sleep(0.5)
        yield instance


@contextlib.asynccontextmanager
async def start_system_setup_server(*args, **kwargs):
    async with start_server_factory(SystemSetupServer, *args, **kwargs) as srv:
        yield srv


@contextlib.asynccontextmanager
async def connect_server(*args, **kwargs):
    # This is not used by the tests directly, but can be convenient when
    # wanting to debug the server process.  Change a test's start_server
    # to connect_server, disable the test timeout, and run just that test.
    socket_path = '.subiquity/socket'
    conn = aiohttp.UnixConnector(path=socket_path)
    async with aiohttp.ClientSession(connector=conn) as session:
        yield Client(session)


class TestBitlocker(TestAPI):
    @timeout()
    async def test_has_bitlocker(self):
        async with start_server('examples/win10.json') as inst:
            resp = await inst.get('/storage/has_bitlocker')
            self.assertEqual(1, len(resp))

    @timeout()
    async def test_not_bitlocker(self):
        async with start_server('examples/simple.json') as inst:
            resp = await inst.get('/storage/has_bitlocker')
            self.assertEqual(0, len(resp))


class TestFlow(TestAPI):
    @timeout(2)
    async def test_serverish_flow(self):
        async with start_server('examples/simple.json') as inst:
            await inst.post('/locale', 'en_US.UTF-8')
            keyboard = {
                'layout': 'us',
                'variant': '',
                'toggle': None
            }
            await inst.post('/keyboard', keyboard)
            await inst.post('/source',
                            source_id='ubuntu-server', search_drivers=True)
            await inst.post('/network')
            await inst.post('/proxy', '')
            await inst.post('/mirror', 'http://us.archive.ubuntu.com/ubuntu')

            resp = await inst.get('/storage/v2/guided')
            [reformat] = resp['possible']
            await inst.post('/storage/v2/guided', {'target': reformat})
            await inst.post('/storage/v2')
            await inst.get('/meta/status', cur='WAITING')
            await inst.post('/meta/confirm', tty='/dev/tty1')
            await inst.get('/meta/status', cur='NEEDS_CONFIRMATION')
            identity = {
                'realname': 'ubuntu',
                'username': 'ubuntu',
                'hostname': 'ubuntu-server',
                'crypted_password': '$6$exDY1mhS4KUYCE/2$zmn9ToZwTKLhCw.b4/'
                                    + 'b.ZRTIZM30JZ4QrOQ2aOXJ8yk96xpcCof0kx'
                                    + 'KwuX1kqLG/ygbJ1f8wxED22bTL4F46P0'
            }
            await inst.post('/identity', identity)
            ssh = {
                'install_server': False,
                'allow_pw': False,
                'authorized_keys': []
            }
            await inst.post('/ssh', ssh)
            await inst.post('/snaplist', [])
            ua_params = {
                "token": "a1b2c3d4e6f7g8h9I0K1",
            }
            await inst.post('/ubuntu_pro', ua_params)
            for state in 'RUNNING', 'WAITING', 'RUNNING', 'UU_RUNNING':
                await inst.get('/meta/status', cur=state)

    @timeout()
    async def test_v2_flow(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            orig_resp = await inst.get('/storage/v2')
            sda = first(orig_resp['disks'], 'id', disk_id)
            self.assertTrue(len(sda['partitions']) > 0)

            data = {'disk_id': disk_id}
            resp = await inst.post('/storage/v2/reformat_disk', data)
            sda = first(resp['disks'], 'id', disk_id)
            [gap] = sda['partitions']
            self.assertEqual('Gap', gap['$type'])

            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'format': 'ext3',
                    'mount': '/',
                }
            }
            add_resp = await inst.post('/storage/v2/add_partition', data)
            [sda] = add_resp['disks']
            [root] = match(sda['partitions'], mount='/')
            self.assertEqual('ext3', root['format'])

            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': root['number'],
                    'format': 'ext4',
                    'wipe': 'superblock',
                }
            }
            edit_resp = await inst.post('/storage/v2/edit_partition', data)

            [add_sda] = add_resp['disks']
            [add_root] = match(add_sda['partitions'], mount='/')

            [edit_sda] = edit_resp['disks']
            [edit_root] = match(edit_sda['partitions'], mount='/')

            for key in 'size', 'number', 'mount', 'boot':
                self.assertEqual(add_root[key], edit_root[key], key)
            self.assertEqual('ext4', edit_root['format'])

            del_resp = await inst.post('/storage/v2/delete_partition', data)
            [sda] = del_resp['disks']
            [p, g] = sda['partitions']
            self.assertEqual('Partition', p['$type'])
            self.assertEqual('Gap', g['$type'])

            reset_resp = await inst.post('/storage/v2/reset')
            self.assertEqual(orig_resp, reset_resp)

            resp = await inst.get('/storage/v2/guided')
            [reformat] = match(resp['possible'],
                               _type='GuidedStorageTargetReformat')
            await inst.post('/storage/v2/guided', {'target': reformat})
            after_guided_resp = await inst.get('/storage/v2')
            post_resp = await inst.post('/storage/v2')
            # posting to the endpoint shouldn't change the answer
            self.assertEqual(after_guided_resp, post_resp)


class TestGuided(TestAPI):
    @timeout()
    async def test_guided_v2_reformat(self):
        cfg = 'examples/win10-along-ubuntu.json'
        async with start_server(cfg) as inst:
            resp = await inst.get('/storage/v2/guided')
            [reformat] = match(resp['possible'],
                               _type='GuidedStorageTargetReformat')
            resp = await inst.post('/storage/v2/guided', {'target': reformat})
            self.assertEqual(reformat, resp['configured']['target'])
            resp = await inst.get('/storage/v2')
            [p1, p2] = resp['disks'][0]['partitions']
            expected_p1 = {
                '$type': 'Partition',
                'boot': True,
                'format': 'fat32',
                'grub_device': True,
                'mount': '/boot/efi',
                'number': 1,
                'preserve': False,
                'wipe': 'superblock',
            }
            self.assertDictSubset(expected_p1, p1)
            expected_p2 = {
                'number': 2,
                'mount': '/',
                'format': 'ext4',
                'preserve': False,
                'wipe': 'superblock',
            }
            self.assertDictSubset(expected_p2, p2)

            v1resp = await inst.get('/storage')
            parts = match(v1resp['config'], type='partition')
            for p in parts:
                self.assertFalse(p['preserve'], p)
                self.assertEqual('superblock', p.get('wipe'), p)

    @timeout()
    async def test_guided_v2_resize(self):
        cfg = 'examples/win10-along-ubuntu.json'
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            orig_resp = await inst.get('/storage/v2')
            [orig_p1, orig_p2, orig_p3, orig_p4, orig_p5] = \
                orig_resp['disks'][0]['partitions']
            resp = await inst.get('/storage/v2/guided')
            [resize_ntfs, resize_ext4] = match(
                    resp['possible'], _type='GuidedStorageTargetResize')
            resize_ntfs['new_size'] = 30 << 30
            data = {'target': resize_ntfs}
            resp = await inst.post('/storage/v2/guided', data)
            self.assertEqual(resize_ntfs, resp['configured']['target'])
            resp = await inst.get('/storage/v2')
            [p1, p2, p3, p6, p4, p5] = resp['disks'][0]['partitions']
            expected_p1 = {
                '$type': 'Partition',
                'boot': True,
                'format': 'vfat',
                'grub_device': True,
                'mount': '/boot/efi',
                'number': 1,
                'size': orig_p1['size'],
                'resize': None,
                'wipe': None,
            }
            self.assertDictSubset(expected_p1, p1)
            self.assertEqual(orig_p2, p2)
            self.assertEqual(orig_p4, p4)
            self.assertEqual(orig_p5, p5)
            expected_p6 = {
                'number': 6,
                'mount': '/',
                'format': 'ext4',
            }
            self.assertDictSubset(expected_p6, p6)

    @timeout()
    async def test_guided_v2_use_gap(self):
        cfg = self.machineConfig('examples/win10-along-ubuntu.json')
        with cfg.edit() as data:
            pt = data['storage']['blockdev']['/dev/sda']['partitiontable']
            [node] = match(pt['partitions'], node='/dev/sda5')
            pt['partitions'].remove(node)
            del data['storage']['blockdev']['/dev/sda5']
            del data['storage']['filesystem']['/dev/sda5']
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            orig_resp = await inst.get('/storage/v2')
            [orig_p1, orig_p2, orig_p3, orig_p4, gap] = \
                orig_resp['disks'][0]['partitions']
            resp = await inst.get('/storage/v2/guided')
            [use_gap] = match(resp['possible'],
                              _type='GuidedStorageTargetUseGap')
            data = {'target': use_gap}
            resp = await inst.post('/storage/v2/guided', data)
            self.assertEqual(use_gap, resp['configured']['target'])
            resp = await inst.get('/storage/v2')
            [p1, p2, p3, p4, p5] = resp['disks'][0]['partitions']
            expected_p1 = {
                '$type': 'Partition',
                'boot': True,
                'format': 'vfat',
                'grub_device': True,
                'mount': '/boot/efi',
                'number': 1,
                'size': orig_p1['size'],
                'resize': None,
                'wipe': None,
            }
            self.assertDictSubset(expected_p1, p1)
            self.assertEqual(orig_p2, p2)
            self.assertEqual(orig_p3, p3)
            self.assertEqual(orig_p4, p4)
            expected_p5 = {
                'number': 5,
                'mount': '/',
                'format': 'ext4',
            }
            self.assertDictSubset(expected_p5, p5)

    @timeout()
    async def test_guided_v2_resize_logical(self):
        cfg = 'examples/threebuntu-on-msdos.json'
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get('/storage/v2/guided')
            [resize] = match(
                    resp['possible'], _type='GuidedStorageTargetResize',
                    partition_number=6)
            data = {'target': resize}
            resp = await inst.post('/storage/v2/guided', data)
            self.assertEqual(resize, resp['configured']['target'])
            # should not throw a Gap Not Found exception


class TestAdd(TestAPI):
    @timeout()
    async def test_v2_add_boot_partition(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'

            resp = await inst.post('/storage/v2')
            sda = first(resp['disks'], 'id', disk_id)
            gap = first(sda['partitions'], '$type', 'Gap')

            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            single_add = await inst.post('/storage/v2/add_partition', data)
            self.assertEqual(2, len(single_add['disks'][0]['partitions']))
            self.assertTrue(single_add['disks'][0]['boot_device'])

            await inst.post('/storage/v2/reset')

            # these manual steps are expected to be mostly equivalent to just
            # adding the single partition and getting the automatic boot
            # partition
            resp = await inst.post(
                '/storage/v2/add_boot_partition', disk_id=disk_id)
            sda = first(resp['disks'], 'id', disk_id)
            gap = first(sda['partitions'], '$type', 'Gap')
            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            manual_add = await inst.post('/storage/v2/add_partition', data)

            # the only difference is the partition number assigned - when we
            # explicitly add_boot_partition, that is the first partition
            # created, versus when we add_partition and get a boot partition
            # implicitly
            for resp in single_add, manual_add:
                for part in resp['disks'][0]['partitions']:
                    part.pop('number')
                    part.pop('path')

            self.assertEqual(single_add, manual_add)

    @timeout()
    async def test_v2_deny_multiple_add_boot_partition(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            await inst.post('/storage/v2/add_boot_partition', disk_id=disk_id)
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/add_boot_partition',
                                disk_id=disk_id)

    @timeout()
    async def test_v2_deny_multiple_add_boot_partition_BIOS(self):
        async with start_server('examples/simple.json', 'bios') as inst:
            disk_id = 'disk-sda'
            await inst.post('/storage/v2/add_boot_partition', disk_id=disk_id)
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/add_boot_partition',
                                disk_id=disk_id)

    @timeout()
    async def test_add_format_required(self):
        disk_id = 'disk-sda'
        async with start_server('examples/simple.json') as inst:
            bad_partitions = [
                {},
                {'mount': '/'},
            ]
            for partition in bad_partitions:
                data = {'disk_id': disk_id, 'partition': partition}
                with self.assertRaises(ClientResponseError,
                                       msg=f'data {data}'):
                    await inst.post('/storage/v2/add_partition', data)

    @timeout()
    async def test_add_default_size_handling(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', disk_id)
            [gap] = sda['partitions']

            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            sda = first(resp['disks'], 'id', disk_id)
            sda1 = first(sda['partitions'], 'number', 1)
            sda2 = first(sda['partitions'], 'number', 2)
            self.assertEqual(gap['size'], sda1['size'] + sda2['size'])

    @timeout()
    async def test_v2_add_boot_BIOS(self):
        async with start_server('examples/simple.json', 'bios') as inst:
            disk_id = 'disk-sda'
            resp = await inst.post('/storage/v2/add_boot_partition',
                                   disk_id=disk_id)
            sda = first(resp['disks'], 'id', disk_id)
            sda1 = first(sda['partitions'], 'number', 1)
            self.assertTrue(sda['boot_device'])
            self.assertTrue(sda1['boot'])

    @timeout()
    async def test_v2_blank_is_not_boot(self):
        async with start_server('examples/simple.json', 'bios') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', disk_id)
            self.assertFalse(sda['boot_device'])

    @timeout()
    async def test_v2_multi_disk_multi_boot(self):
        async with start_server('examples/many-nics-and-disks.json') as inst:
            resp = await inst.get('/storage/v2')
            vda = first(resp['disks'], 'id', 'disk-vda')
            vdb = first(resp['disks'], 'id', 'disk-vdb')
            await inst.post('/storage/v2/reformat_disk',
                            {'disk_id': vda['id']})
            await inst.post('/storage/v2/reformat_disk',
                            {'disk_id': vdb['id']})
            await inst.post('/storage/v2/add_boot_partition',
                            disk_id=vda['id'])
            await inst.post('/storage/v2/add_boot_partition',
                            disk_id=vdb['id'])
            # should allow both disks to get a boot partition with no Exception


class TestDelete(TestAPI):
    @timeout()
    async def test_v2_delete_without_reformat(self):
        cfg = 'examples/win10.json'
        extra = ['--storage-version', '1']
        async with start_server(cfg, extra_args=extra) as inst:
            data = {
                'disk_id': 'disk-sda',
                'partition': {'number': 1}
            }
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/delete_partition', data)

    @timeout()
    async def test_v2_delete_without_reformat_is_ok_with_sv2(self):
        cfg = 'examples/win10.json'
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            data = {
                'disk_id': 'disk-sda',
                'partition': {'number': 1}
            }
            await inst.post('/storage/v2/delete_partition', data)

    @timeout()
    async def test_v2_delete_with_reformat(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.post('/storage/v2/reformat_disk',
                                   {'disk_id': disk_id})
            [sda] = resp['disks']
            [gap] = sda['partitions']
            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'mount': '/',
                    'format': 'ext4',
                }
            }
            await inst.post('/storage/v2/add_partition', data)
            data = {
                'disk_id': disk_id,
                'partition': {'number': 1}
            }
            await inst.post('/storage/v2/delete_partition', data)

    @timeout()
    async def test_delete_nonexistant(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            await inst.post('/storage/v2/reformat_disk', {'disk_id': disk_id})
            data = {
                'disk_id': disk_id,
                'partition': {'number': 1}
            }
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/delete_partition', data)


class TestEdit(TestAPI):
    @timeout()
    async def test_edit_no_change_size(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')

            sda = first(resp['disks'], 'id', disk_id)
            sda3 = first(sda['partitions'], 'number', 3)
            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': 3,
                    'size': sda3['size'] - (1 << 30)
                }
            }
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/edit_partition', data)

    @timeout()
    async def test_edit_no_change_grub(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': 3,
                    'boot': True,
                }
            }
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/edit_partition', data)

    @timeout()
    async def test_edit_format(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': 3,
                    'format': 'btrfs',
                    'wipe': 'superblock',
                }
            }
            resp = await inst.post('/storage/v2/edit_partition', data)

            sda = first(resp['disks'], 'id', disk_id)
            sda3 = first(sda['partitions'], 'number', 3)
            self.assertEqual('btrfs', sda3['format'])

    @timeout()
    async def test_edit_mount(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': 3,
                    'mount': '/',
                }
            }
            resp = await inst.post('/storage/v2/edit_partition', data)

            sda = first(resp['disks'], 'id', disk_id)
            sda3 = first(sda['partitions'], 'number', 3)
            self.assertEqual('/', sda3['mount'])

    @timeout()
    async def test_edit_format_and_mount(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': 3,
                    'format': 'btrfs',
                    'mount': '/',
                    'wipe': 'superblock',
                }
            }
            resp = await inst.post('/storage/v2/edit_partition', data)

            sda = first(resp['disks'], 'id', disk_id)
            sda3 = first(sda['partitions'], 'number', 3)
            self.assertEqual('btrfs', sda3['format'])
            self.assertEqual('/', sda3['mount'])

    @timeout()
    async def test_v2_reuse(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')
            orig_sda = first(resp['disks'], 'id', disk_id)

            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': 3,
                    'format': 'ext4',
                    'mount': '/',
                    'wipe': 'superblock',
                }
            }
            resp = await inst.post('/storage/v2/edit_partition', data)
            sda = first(resp['disks'], 'id', disk_id)
            sda1 = first(sda['partitions'], 'number', 1)
            self.assertIsNone(sda1['wipe'])
            self.assertEqual('/boot/efi', sda1['mount'])
            self.assertEqual('vfat', sda1['format'])
            self.assertTrue(sda1['boot'])

            sda2 = first(sda['partitions'], 'number', 2)
            orig_sda2 = first(orig_sda['partitions'], 'number', 2)
            self.assertEqual(orig_sda2, sda2)

            sda3 = first(sda['partitions'], 'number', 3)
            self.assertIsNotNone(sda3['wipe'])
            self.assertEqual('/', sda3['mount'])
            self.assertEqual('ext4', sda3['format'])
            self.assertFalse(sda3['boot'])

            sda4 = first(sda['partitions'], 'number', 4)
            orig_sda4 = first(orig_sda['partitions'], 'number', 4)
            self.assertEqual(orig_sda4, sda4)


class TestReformat(TestAPI):
    @timeout()
    async def test_reformat_msdos(self):
        cfg = 'examples/simple.json'
        async with start_server(cfg) as inst:
            data = {
                'disk_id': 'disk-sda',
                'ptable': 'msdos',
            }
            resp = await inst.post('/storage/v2/reformat_disk', data)
            [sda] = resp['disks']
            self.assertEqual('msdos', sda['ptable'])


class TestPartitionTableTypes(TestAPI):
    @timeout()
    async def test_ptable_gpt(self):
        async with start_server('examples/win10.json') as inst:
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', 'disk-sda')
            self.assertEqual('gpt', sda['ptable'])

    @timeout()
    async def test_ptable_msdos(self):
        async with start_server('examples/many-nics-and-disks.json') as inst:
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', 'disk-sda')
            self.assertEqual('msdos', sda['ptable'])

    @timeout()
    async def test_ptable_none(self):
        async with start_server('examples/simple.json') as inst:
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', 'disk-sda')
            self.assertEqual(None, sda['ptable'])


class TestTodos(TestAPI):  # server indicators of required client actions
    @timeout()
    async def test_todos_simple(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.post('/storage/v2/reformat_disk',
                                   {'disk_id': disk_id})
            self.assertTrue(resp['need_root'])
            self.assertTrue(resp['need_boot'])

            [sda] = resp['disks']
            [gap] = sda['partitions']
            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            self.assertFalse(resp['need_root'])
            self.assertFalse(resp['need_boot'])

    @timeout()
    async def test_todos_manual(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.post('/storage/v2/reformat_disk',
                                   {'disk_id': disk_id})
            self.assertTrue(resp['need_root'])
            self.assertTrue(resp['need_boot'])

            resp = await inst.post('/storage/v2/add_boot_partition',
                                   disk_id=disk_id)
            self.assertTrue(resp['need_root'])
            self.assertFalse(resp['need_boot'])

            [sda] = resp['disks']
            gap = first(sda['partitions'], '$type', 'Gap')
            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            self.assertFalse(resp['need_root'])
            self.assertFalse(resp['need_boot'])

    @timeout()
    async def test_todos_guided(self):
        async with start_server('examples/simple.json') as inst:
            resp = await inst.post('/storage/v2/reformat_disk',
                                   {'disk_id': 'disk-sda'})
            self.assertTrue(resp['need_root'])
            self.assertTrue(resp['need_boot'])

            resp = await inst.get('/storage/v2/guided')
            [reformat] = resp['possible']
            await inst.post('/storage/v2/guided', {'target': reformat})
            resp = await inst.get('/storage/v2')
            self.assertFalse(resp['need_root'])
            self.assertFalse(resp['need_boot'])


class TestInfo(TestAPI):
    @timeout()
    async def test_path(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', disk_id)
            self.assertEqual('/dev/sda', sda['path'])

    async def test_model_and_vendor(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', disk_id)
            self.assertEqual('QEMU HARDDISK', sda['model'])
            self.assertEqual('ATA', sda['vendor'])

    async def test_no_vendor(self):
        async with start_server('examples/many-nics-and-disks.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', disk_id)
            self.assertEqual('QEMU HARDDISK', sda['model'])
            self.assertEqual(None, sda['vendor'])


class TestFree(TestAPI):
    @timeout()
    async def test_free_only(self):
        async with start_server('examples/simple.json') as inst:
            await inst.post('/meta/free_only', enable=True)
            components = await inst.get('/mirror/disable_components')
            components.sort()
            self.assertEqual(['multiverse', 'restricted'], components)

    @timeout()
    async def test_not_free_only(self):
        async with start_server('examples/simple.json') as inst:
            comps = ['universe', 'multiverse']
            await inst.post('/mirror/disable_components', comps)
            await inst.post('/meta/free_only', enable=False)
            components = await inst.get('/mirror/disable_components')
            self.assertEqual(['universe'], components)


class TestOSProbe(TestAPI):
    @timeout()
    async def test_win10(self):
        async with start_server('examples/win10.json') as inst:
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', 'disk-sda')
            sda1 = first(sda['partitions'], 'number', 1)
            expected = {
                'label': 'Windows',
                'long': 'Windows Boot Manager',
                'subpath': '/efi/Microsoft/Boot/bootmgfw.efi',
                'type': 'efi',
                'version': None
            }

            self.assertEqual(expected, sda1['os'])


class TestPartitionTableEditing(TestAPI):
    @timeout()
    async def test_use_free_space_after_existing(self):
        cfg = 'examples/ubuntu-and-free-space.json'
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            # Disk has 3 existing partitions and free space.  Add one to end.
            # sda1 is an ESP, so that should get implicitly picked up.
            resp = await inst.get('/storage/v2')
            [sda] = resp['disks']
            [e1, e2, e3, gap] = sda['partitions']
            self.assertEqual('Gap', gap['$type'])

            data = {
                'disk_id': 'disk-sda',
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            [sda] = resp['disks']
            [p1, p2, p3, p4] = sda['partitions']
            e1.pop('annotations')
            e1.update({'mount': '/boot/efi', 'grub_device': True})
            self.assertDictSubset(e1, p1)
            self.assertEqual(e2, p2)
            self.assertEqual(e3, p3)
            e4 = {
                '$type': 'Partition',
                'number': 4,
                'size': gap['size'],
                'offset': gap['offset'],
                'format': 'ext4',
                'mount': '/',
            }
            self.assertDictSubset(e4, p4)

    @timeout()
    async def test_resize(self):
        cfg = self.machineConfig('examples/ubuntu-and-free-space.json')
        with cfg.edit() as data:
            blockdev = data['storage']['blockdev']
            sizes = {k: int(v['attrs']['size']) for k, v in blockdev.items()}
            # expand sda3 to use the rest of the disk
            sda3_size = (sizes['/dev/sda'] - sizes['/dev/sda1']
                         - sizes['/dev/sda2'] - (2 << 20))
            blockdev['/dev/sda3']['attrs']['size'] = str(sda3_size)

        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            # Disk has 3 existing partitions and no free space.
            resp = await inst.get('/storage/v2')
            [sda] = resp['disks']
            [orig_p1, orig_p2, orig_p3] = sda['partitions']

            p3 = orig_p3.copy()
            p3['size'] = 10 << 30
            data = {
                'disk_id': 'disk-sda',
                'partition': p3,
            }
            resp = await inst.post('/storage/v2/edit_partition', data)
            [sda] = resp['disks']
            [_, _, actual_p3, g1] = sda['partitions']
            self.assertEqual(10 << 30, actual_p3['size'])
            self.assertEqual(True, actual_p3['resize'])
            self.assertIsNone(actual_p3['wipe'])
            end_size = orig_p3['size'] - (10 << 30)
            self.assertEqual(end_size, g1['size'])

            expected_p1 = orig_p1.copy()
            expected_p1.pop('annotations')
            expected_p1.update({'mount': '/boot/efi', 'grub_device': True})
            expected_p3 = actual_p3
            data = {
                'disk_id': 'disk-sda',
                'gap': g1,
                'partition': {
                    'format': 'ext4',
                    'mount': '/srv',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            [sda] = resp['disks']
            [actual_p1, actual_p2, actual_p3, actual_p4] = sda['partitions']
            self.assertDictSubset(expected_p1, actual_p1)
            self.assertEqual(orig_p2, actual_p2)
            self.assertEqual(expected_p3, actual_p3)
            self.assertEqual(end_size, actual_p4['size'])
            self.assertEqual('Partition', actual_p4['$type'])

            v1resp = await inst.get('/storage')
            config = v1resp['config']
            [sda3] = match(config, type='partition', number=3)
            [sda3_format] = match(config, type='format', volume=sda3['id'])
            self.assertTrue(sda3['preserve'])
            self.assertTrue(sda3['resize'])
            self.assertTrue(sda3_format['preserve'])

    @timeout()
    async def test_est_min_size(self):
        cfg = self.machineConfig('examples/win10-along-ubuntu.json')
        with cfg.edit() as data:
            fs = data['storage']['filesystem']
            fs['/dev/sda1']['ESTIMATED_MIN_SIZE'] = 0
            # data file has no sda2 in filesystem
            fs['/dev/sda3']['ESTIMATED_MIN_SIZE'] = -1
            fs['/dev/sda4']['ESTIMATED_MIN_SIZE'] = (1 << 20) + 1

        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get('/storage/v2')
            [sda] = resp['disks']
            [p1, _, p3, p4, _] = sda['partitions']
            self.assertEqual(1 << 20, p1['estimated_min_size'])
            self.assertEqual(-1, p3['estimated_min_size'])
            self.assertEqual(2 << 20, p4['estimated_min_size'])

    @timeout()
    async def test_v2_orig_config(self):
        cfg = 'examples/win10-along-ubuntu.json'
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            start_resp = await inst.get('/storage/v2')
            resp = await inst.get('/storage/v2/guided')
            resize = match(resp['possible'],
                           _type='GuidedStorageTargetResize')[0]
            resize['new_size'] = 30 << 30
            await inst.post('/storage/v2/guided', {'target': resize})
            orig_config = await inst.get('/storage/v2/orig_config')
            end_resp = await inst.get('/storage/v2')
            self.assertEqual(start_resp, orig_config)
            self.assertNotEqual(start_resp, end_resp)


class TestGap(TestAPI):
    async def test_blank_disk_is_one_big_gap(self):
        async with start_server('examples/simple.json') as inst:
            resp = await inst.get('/storage/v2')
            sda = first(resp['disks'], 'id', 'disk-sda')
            gap = sda['partitions'][0]
            expected = (100 << 30) - (2 << 20)
            self.assertEqual(expected, gap['size'])
            self.assertEqual('YES', gap['usable'])

    async def test_gap_at_end(self):
        async with start_server('examples/simple.json') as inst:
            resp = await inst.get('/storage/v2')
            [sda] = resp['disks']
            gap = first(sda['partitions'], '$type', 'Gap')
            data = {
                'disk_id': 'disk-sda',
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                    'size': 4 << 30,
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            [sda] = resp['disks']
            [boot] = match(sda['partitions'], mount='/boot/efi')
            [p1, p2, gap] = sda['partitions']
            self.assertEqual('Gap', gap['$type'])
            expected = (100 << 30) - p1['size'] - p2['size'] - (2 << 20)
            self.assertEqual(expected, gap['size'])

    async def SKIP_test_two_gaps(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.post('/storage/v2/add_boot_partition',
                                   disk_id=disk_id)
            json_print(resp)
            boot_size = resp['disks'][0]['partitions'][0]['size']
            root_size = 4 << 30
            data = {
                'disk_id': disk_id,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                    'size': root_size,
                }
            }
            await inst.post('/storage/v2/add_partition', data)
            data = {
                'disk_id': disk_id,
                'partition': {'number': 1}
            }
            resp = await inst.post('/storage/v2/delete_partition', data)
            sda = first(resp['disks'], 'id', disk_id)
            self.assertEqual(3, len(sda['partitions']))

            boot_gap = sda['partitions'][0]
            self.assertEqual(boot_size, boot_gap['size'])
            self.assertEqual('Gap', boot_gap['$type'])

            root = sda['partitions'][1]
            self.assertEqual(root_size, root['size'])
            self.assertEqual('Partition', root['$type'])

            end_gap = sda['partitions'][2]
            end_size = (10 << 30) - boot_size - root_size - (2 << 20)
            self.assertEqual(end_size, end_gap['size'])
            self.assertEqual('Gap', end_gap['$type'])


class TestRegression(TestAPI):
    @timeout()
    async def test_edit_not_trigger_boot_device(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.get('/storage/v2')
            [sda] = resp['disks']
            [gap] = sda['partitions']
            data = {
                'disk_id': disk_id,
                'gap': gap,
                'partition': {
                    'format': 'ext4',
                    'mount': '/foo',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            [sda] = resp['disks']
            [part] = match(sda['partitions'], mount='/foo')
            part.update({
                'format': 'ext3',
                'mount': '/bar',
                'wipe': 'superblock',
            })
            data['partition'] = part
            data.pop('gap')
            await inst.post('/storage/v2/edit_partition', data)
            # should not throw an exception complaining about boot

    @timeout()
    async def test_osprober_knames(self):
        cfg = 'examples/lp-1986676-missing-osprober.json'
        async with start_server(cfg) as inst:
            resp = await inst.get('/storage/v2')
            [nvme] = match(resp['disks'], id='disk-nvme0n1')
            [nvme_p2] = match(nvme['partitions'], path='/dev/nvme0n1p2')
            expected = {
                'long': 'Ubuntu 22.04.1 LTS',
                'label': 'Ubuntu',
                'type': 'linux',
                'subpath': None,
                'version': '22.04.1'
            }
            self.assertEqual(expected, nvme_p2['os'])

    @timeout()
    async def test_edit_should_trigger_wipe_when_requested(self):
        # LP: #1983036 - a partition wipe was requested but didn't happen
        # The old way this worked was to use changes to the 'format' value to
        # decide if a wipe was happening or not, and now the client chooses so
        # explicitly.
        async with start_server('examples/win10-along-ubuntu.json') as inst:
            resp = await inst.get('/storage/v2')
            [d1] = resp['disks']
            [p5] = match(d1['partitions'], number=5)
            p5.update(dict(mount='/home', wipe='superblock'))
            data = dict(disk_id=d1['id'], partition=p5)
            resp = await inst.post('/storage/v2/edit_partition', data)

            v1resp = await inst.get('/storage')
            [c_p5] = match(v1resp['config'], number=5)
            [c_p5fmt] = match(v1resp['config'], volume=c_p5['id'])
            self.assertEqual('superblock', c_p5['wipe'])
            self.assertFalse(c_p5fmt['preserve'])
            self.assertTrue(c_p5['preserve'])

            # then let's change our minds and not wipe it
            [d1] = resp['disks']
            [p5] = match(d1['partitions'], number=5)
            p5['wipe'] = None
            data = dict(disk_id=d1['id'], partition=p5)
            resp = await inst.post('/storage/v2/edit_partition', data)

            v1resp = await inst.get('/storage')
            [c_p5] = match(v1resp['config'], number=5)
            [c_p5fmt] = match(v1resp['config'], volume=c_p5['id'])
            self.assertNotIn('wipe', c_p5)
            self.assertTrue(c_p5fmt['preserve'])
            self.assertTrue(c_p5['preserve'])

    @timeout()
    async def test_edit_should_leave_other_values_alone(self):
        async with start_server('examples/win10-along-ubuntu.json') as inst:
            async def check_preserve():
                v1resp = await inst.get('/storage')
                [c_p5] = match(v1resp['config'], number=5)
                [c_p5fmt] = match(v1resp['config'], volume=c_p5['id'])
                self.assertNotIn('wipe', c_p5)
                self.assertTrue(c_p5fmt['preserve'])
                self.assertTrue(c_p5['preserve'])

            resp = await inst.get('/storage/v2')
            d1 = resp['disks'][0]
            [p5] = match(resp['disks'][0]['partitions'], number=5)
            orig_p5 = p5.copy()
            self.assertEqual('ext4', p5['format'])
            self.assertIsNone(p5['mount'])

            data = {'disk_id': d1['id'], 'partition': p5}
            resp = await inst.post('/storage/v2/edit_partition', data)
            [p5] = match(resp['disks'][0]['partitions'], number=5)
            self.assertEqual(orig_p5, p5)
            await check_preserve()

            p5.update({'mount': '/'})
            data = {'disk_id': d1['id'], 'partition': p5}
            resp = await inst.post('/storage/v2/edit_partition', data)
            [p5] = match(resp['disks'][0]['partitions'], number=5)
            expected = orig_p5.copy()
            expected['mount'] = '/'
            expected['annotations'] = [
                'existing', 'already formatted as ext4', 'mounted at /'
            ]
            self.assertEqual(expected, p5)
            await check_preserve()

            data = {'disk_id': d1['id'], 'partition': p5}
            resp = await inst.post('/storage/v2/edit_partition', data)
            [p5] = match(resp['disks'][0]['partitions'], number=5)
            self.assertEqual(expected, p5)
            await check_preserve()

    @timeout()
    async def test_no_change_edit(self):
        cfg = 'examples/simple.json'
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get('/storage/v2')
            [d] = resp['disks']
            [g] = d['partitions']
            data = {
                "disk_id": 'disk-sda',
                "gap": g,
                "partition": {
                    "size": 107372085248,
                    "format": "ext4",
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            [p] = resp['disks'][0]['partitions']
            self.assertEqual('ext4', p['format'])

            orig_p = p.copy()

            data = {"disk_id": 'disk-sda', "partition": p}
            resp = await inst.post('/storage/v2/edit_partition', data)
            [p] = resp['disks'][0]['partitions']
            self.assertEqual(orig_p, p)


class TestCancel(TestAPI):
    @timeout()
    async def test_cancel_drivers(self):
        with patch.dict(os.environ, {'SUBIQUITY_DEBUG': 'has-drivers'}):
            async with start_server('examples/simple.json') as inst:
                await inst.post('/source', source_id="placeholder",
                                search_drivers=True)
                # /drivers?wait=true is expected to block until APT is
                # configured.
                # Let's make sure we cancel it.
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(inst.get('/drivers', wait=True),
                                           0.1)
                names = ['locale', 'keyboard', 'source', 'network', 'proxy',
                         'mirror', 'storage']
                await inst.post('/meta/mark_configured', endpoint_names=names)
                await inst.get('/meta/status', cur='WAITING')
                await inst.post('/meta/confirm', tty='/dev/tty1')
                await inst.get('/meta/status', cur='NEEDS_CONFIRMATION')

                # should not raise ServerDisconnectedError
                resp = await inst.get('/drivers', wait=True)
                self.assertEqual(['nvidia-driver-470-server'], resp['drivers'])


class TestSource(TestAPI):
    async def test_optional_search_drivers(self):
        async with start_server('examples/simple.json') as inst:
            await inst.post('/source', source_id='ubuntu-server')
            resp = await inst.get('/source')
            self.assertFalse(resp['search_drivers'])

            await inst.post('/source', source_id='ubuntu-server',
                            search_drivers=True)
            resp = await inst.get('/source')
            self.assertTrue(resp['search_drivers'])

            await inst.post('/source', source_id='ubuntu-server',
                            search_drivers=False)
            resp = await inst.get('/source')
            self.assertFalse(resp['search_drivers'])


class TestIdentityValidation(TestAPI):
    async def test_username_validation(self):
        async with start_server('examples/simple.json') as inst:
            resp = await inst.get('/identity/validate_username',
                                  username='plugdev')
            self.assertEqual(resp, 'SYSTEM_RESERVED')

            resp = await inst.get('/identity/validate_username',
                                  username='root')
            self.assertEqual(resp, 'ALREADY_IN_USE')

            resp = await inst.get('/identity/validate_username',
                                  username='r'*33)
            self.assertEqual(resp, 'TOO_LONG')

            resp = await inst.get('/identity/validate_username',
                                  username='01root')
            self.assertEqual(resp, 'INVALID_CHARS')

            resp = await inst.get('/identity/validate_username',
                                  username='o#$%^&')
            self.assertEqual(resp, 'INVALID_CHARS')


class TestManyPrimaries(TestAPI):
    @timeout()
    async def test_create_primaries(self):
        cfg = 'examples/simple.json'
        extra = ['--storage-version', '2']
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get('/storage/v2')
            d1 = resp['disks'][0]

            data = {'disk_id': d1['id'], 'ptable': 'msdos'}
            resp = await inst.post('/storage/v2/reformat_disk', data)
            [gap] = match(resp['disks'][0]['partitions'], _type='Gap')

            for _ in range(4):
                self.assertEqual('YES', gap['usable'])
                data = {
                    'disk_id': d1['id'],
                    'gap': gap,
                    'partition': {
                        'size': 1 << 30,
                        'format': 'ext4',
                    }
                }
                resp = await inst.post('/storage/v2/add_partition', data)
                [gap] = match(resp['disks'][0]['partitions'], _type='Gap')

            self.assertEqual('TOO_MANY_PRIMARY_PARTS', gap['usable'])

            data = {
                'disk_id': d1['id'],
                'gap': gap,
                'partition': {
                    'size': 1 << 30,
                    'format': 'ext4',
                }
            }
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/add_partition', data)


class TestKeyboard(TestAPI):
    @timeout()
    async def test_input_source(self):
        async with start_server('examples/simple.json') as inst:
            data = {'layout': 'fr', 'variant': 'latin9'}
            await inst.post('/keyboard/input_source', data, user='foo')


class TestUbuntuProContractSelection(TestAPI):
    @timeout()
    async def test_upcs_flow(self):
        async with start_server('examples/simple.json') as inst:
            # Wait should fail if no initiate first.
            with self.assertRaises(Exception):
                await inst.get('/ubuntu_pro/contract_selection/wait')

            # Cancel should fail if no initiate first.
            with self.assertRaises(Exception):
                await inst.post('/ubuntu_pro/contract_selection/cancel')

            await inst.post('/ubuntu_pro/contract_selection/initiate')
            # Double initiate should fail
            with self.assertRaises(Exception):
                await inst.post('/ubuntu_pro/contract_selection/initiate')

            # This call should block for long enough.
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(
                        inst.get('/ubuntu_pro/contract_selection/wait'),
                        timeout=0.5)

            await inst.post('/ubuntu_pro/contract_selection/cancel')
            with self.assertRaises(Exception):
                await inst.get('/ubuntu_pro/contract_selection/wait')


class TestWSLSetupOptions(TestAPI):
    async def test_wslsetupoptions(self):
        async with start_system_setup_server('examples/simple.json') as inst:
            await inst.post('/meta/client_variant', variant='wsl_setup')

            payload = {'install_language_support_packages': False}
            endpoint = '/wslsetupoptions'
            resp = await inst.get(endpoint)
            self.assertTrue(resp['install_language_support_packages'])
            await inst.post(endpoint, payload)

            resp = await inst.get(endpoint)
            self.assertFalse(resp['install_language_support_packages'])
