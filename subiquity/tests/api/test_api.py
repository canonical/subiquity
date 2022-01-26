#!/usr/bin/env python3

import aiohttp
from aiohttp.client_exceptions import ClientResponseError
import async_timeout
import asyncio
import contextlib
from functools import wraps
import json
import os
import tempfile
import unittest
from urllib.parse import unquote

from subiquitycore.utils import astart_command

default_timeout = 10


def find(items, key, value):
    for item in items:
        if item[key] == value:
            yield item


def first(items, key, value):
    return next(find(items, key, value))


def timeout(multiplier=1):
    def wrapper(coro):
        @wraps(coro)
        async def run(*args, **kwargs):
            with async_timeout.timeout(default_timeout * multiplier):
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
        if data or type(data) is bool:
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
                    bootloader='uefi'):
        env = os.environ.copy()
        env['SUBIQUITY_REPLAY_TIMESCALE'] = '100'
        cmd = ['python3', '-m', 'subiquity.cmd.server',
               '--dry-run',
               '--bootloader', bootloader,
               '--socket', socket,
               '--output-base', output_base,
               '--machine-config', machine_config]
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


class TestAPI(unittest.IsolatedAsyncioTestCase):
    pass


async def poll_for_socket_exist(socket_path):
    for _ in range(default_timeout * 5):
        # test level timeout will trigger first, this loop is just a fallback
        if os.path.exists(socket_path):
            return
        await asyncio.sleep(.1)
    raise Exception('timeout looking for socket to exist')


@contextlib.asynccontextmanager
async def start_server(*args, **kwargs):
    with tempfile.TemporaryDirectory() as tempdir:
        socket_path = f'{tempdir}/socket'
        conn = aiohttp.UnixConnector(path=socket_path)
        async with aiohttp.ClientSession(connector=conn) as session:
            server = Server(session)
            try:
                await server.spawn(tempdir, socket_path, *args, **kwargs)
                await poll_for_socket_exist(socket_path)
                await server.poll_startup()
                yield server
            finally:
                await server.close()


@contextlib.asynccontextmanager
async def connect_server(*args, **kwargs):
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
    async def test_server_flow(self):
        async with start_server('examples/simple.json') as inst:
            await inst.post('/locale', 'en_US.UTF-8')
            keyboard = {
                'layout': 'us',
                'variant': '',
                'toggle': None
            }
            await inst.post('/keyboard', keyboard)
            await inst.post('/source', source_id='ubuntu-server')
            await inst.post('/network')
            await inst.post('/proxy', '')
            await inst.post('/mirror', 'http://us.archive.ubuntu.com/ubuntu')
            resp = await inst.get('/storage/guided')
            disk_id = resp['disks'][0]['id']
            choice = {"disk_id": disk_id}
            await inst.post('/storage/v2/guided', choice=choice)
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
            await inst.post('/ubuntu_advantage', ua_params)
            for state in 'RUNNING', 'POST_WAIT', 'POST_RUNNING', 'UU_RUNNING':
                await inst.get('/meta/status', cur=state)

    @timeout()
    async def test_v2_flow(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            orig_resp = await inst.get('/storage/v2')
            sda = first(orig_resp['disks'], 'id', disk_id)
            self.assertTrue(len(sda['partitions']) > 0)

            resp = await inst.post('/storage/v2/reformat_disk',
                                   disk_id=disk_id)
            sda = first(resp['disks'], 'id', disk_id)
            self.assertEqual(0, len(sda['partitions']))

            data = {
                'disk_id': disk_id,
                'partition': {
                    'format': 'ext3',
                    'mount': '/',
                }
            }
            add_resp = await inst.post('/storage/v2/add_partition', data)
            sda = first(add_resp['disks'], 'id', disk_id)
            sda2 = first(sda['partitions'], 'number', 2)
            self.assertEqual('ext3', sda2['format'])

            data = {
                'disk_id': disk_id,
                'partition': {
                    'number': 2,
                    'format': 'ext4',
                }
            }
            resp = await inst.post('/storage/v2/edit_partition', data)
            expected = add_resp['disks'][0]['partitions'][1]
            actual = resp['disks'][0]['partitions'][1]
            for key in 'size', 'number', 'mount', 'boot':
                self.assertEqual(expected[key], actual[key])
            self.assertEqual('ext4',
                             resp['disks'][0]['partitions'][1]['format'])

            resp = await inst.post('/storage/v2/delete_partition', data)
            self.assertEqual(1, len(resp['disks'][0]['partitions']))

            resp = await inst.post('/storage/v2/reset')
            self.assertEqual(orig_resp, resp)

            choice = {'disk_id': disk_id}
            guided_resp = await inst.post('/storage/v2/guided', choice=choice)
            post_resp = await inst.post('/storage/v2')
            # posting to the endpoint shouldn't change the answer
            self.assertEqual(guided_resp, post_resp)


class TestGuided(TestAPI):
    @timeout()
    async def test_guided_v2(self):
        async with start_server('examples/simple.json') as inst:
            choice = {'disk_id': 'disk-sda'}
            resp = await inst.post('/storage/v2/guided', choice=choice)
            self.assertEqual(1, len(resp['disks']))
            self.assertEqual('disk-sda', resp['disks'][0]['id'])


class TestAdd(TestAPI):
    @timeout()
    async def test_v2_add_boot_partition(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'

            data = {
                'disk_id': disk_id,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            single_add = await inst.post('/storage/v2/add_partition', data)
            self.assertEqual(2, len(single_add['disks'][0]['partitions']))
            self.assertTrue(single_add['disks'][0]['boot_device'])

            await inst.post('/storage/v2/reset')

            # these manual steps are expected to be equivalent to just adding
            # the single partition and getting the automatic boot partition
            await inst.post('/storage/v2/add_boot_partition', disk_id=disk_id)
            manual_add = await inst.post('/storage/v2/add_partition', data)
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
    async def test_v2_free_for_partitions(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'
            resp = await inst.post('/storage/v2/add_boot_partition',
                                   disk_id=disk_id)
            sda = first(resp['disks'], 'id', disk_id)
            orig_free = sda['free_for_partitions']

            size_requested = 6 << 30
            expected_free = orig_free - size_requested
            data = {
                'disk_id': disk_id,
                'partition': {
                    'size': size_requested,
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            sda = first(resp['disks'], 'id', disk_id)
            self.assertEqual(expected_free, sda['free_for_partitions'])

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
            expected_total = sda['free_for_partitions']

            data = {
                'disk_id': disk_id,
                'partition': {
                    'format': 'ext4',
                    'mount': '/',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            sda = first(resp['disks'], 'id', disk_id)
            sda1 = first(sda['partitions'], 'number', 1)
            sda2 = first(sda['partitions'], 'number', 2)
            self.assertEqual(expected_total, sda1['size'] + sda2['size'])

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
            await inst.post('/storage/v2/add_boot_partition',
                            disk_id=vda['id'])
            await inst.post('/storage/v2/add_boot_partition',
                            disk_id=vdb['id'])
            # should allow both disks to get a boot partition with no Exception


class TestDelete(TestAPI):
    @timeout()
    async def test_v2_delete_without_reformat(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            data = {
                'disk_id': disk_id,
                'partition': {'number': 1}
            }
            with self.assertRaises(ClientResponseError):
                await inst.post('/storage/v2/delete_partition', data)

    @timeout()
    async def test_v2_delete_with_reformat(self):
        async with start_server('examples/win10.json') as inst:
            disk_id = 'disk-sda'
            await inst.post('/storage/v2/reformat_disk', disk_id=disk_id)
            data = {
                'disk_id': disk_id,
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
            await inst.post('/storage/v2/reformat_disk', disk_id=disk_id)
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
            self.assertEqual('superblock', sda3['wipe'])
            self.assertEqual('/', sda3['mount'])
            self.assertEqual('ext4', sda3['format'])
            self.assertFalse(sda3['boot'])

            sda4 = first(sda['partitions'], 'number', 4)
            orig_sda4 = first(orig_sda['partitions'], 'number', 4)
            self.assertEqual(orig_sda4, sda4)


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
                                   disk_id=disk_id)
            self.assertTrue(resp['need_root'])
            self.assertTrue(resp['need_boot'])

            data = {
                'disk_id': disk_id,
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
                                   disk_id=disk_id)
            self.assertTrue(resp['need_root'])
            self.assertTrue(resp['need_boot'])

            resp = await inst.post('/storage/v2/add_boot_partition',
                                   disk_id=disk_id)
            self.assertTrue(resp['need_root'])
            self.assertFalse(resp['need_boot'])

            data = {
                'disk_id': disk_id,
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
            disk_id = 'disk-sda'
            resp = await inst.post('/storage/v2/reformat_disk',
                                   disk_id=disk_id)
            self.assertTrue(resp['need_root'])
            self.assertTrue(resp['need_boot'])

            choice = {'disk_id': disk_id}
            resp = await inst.post('/storage/v2/guided', choice=choice)
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


class TestRegression(TestAPI):
    @timeout()
    async def test_edit_not_trigger_boot_device(self):
        async with start_server('examples/simple.json') as inst:
            disk_id = 'disk-sda'

            data = {
                'disk_id': disk_id,
                'partition': {
                    'format': 'ext4',
                    'mount': '/foo',
                }
            }
            resp = await inst.post('/storage/v2/add_partition', data)
            sda = first(resp['disks'], 'id', disk_id)
            sda2 = first(sda['partitions'], 'number', 2)
            sda2.update({'format': 'ext3', 'mount': '/bar'})
            data['partition'] = sda2
            await inst.post('/storage/v2/edit_partition', data)
            # should not throw an exception complaining about boot
