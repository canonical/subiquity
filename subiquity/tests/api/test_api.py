#!/usr/bin/env python3

import aiohttp
from aiohttp.client_exceptions import ClientResponseError
import async_timeout
import asyncio
from functools import wraps
import json
import logging
import os
import sys
import unittest
from urllib.parse import unquote

from subiquitycore.utils import astart_command


logging.basicConfig(level=logging.DEBUG)
socket_path = '.subiquity/socket'


ver = sys.version_info
if ver.major < 3 or ver.minor < 8:
    raise Exception('skip asyncio testing')


def find(items, key, value):
    for item in items:
        if item[key] == value:
            yield item


def first(items, key, value):
    return next(find(items, key, value))


def timeout(_timeout):
    def wrapper(coro):
        @wraps(coro)
        async def run(*args, **kwargs):
            with async_timeout.timeout(_timeout):
                return await coro(*args, **kwargs)
        return run
    return wrapper


def json_print(json_data):
    print(json.dumps(json_data, indent=4))


def loads(data):
    if data == '' or data is None:  # json.loads likes neither of these
        return None
    return json.loads(data)


def dumps(data):
    # if the data we're dumping is literally False, we want that to be 'false'
    if data or type(data) is bool:
        return json.dumps(data, separators=(',', ':'))
    elif data is not None:
        return '""'
    else:
        return data


class ClientException(Exception):
    pass


class TestAPI(unittest.IsolatedAsyncioTestCase):
    machine_config = 'examples/simple.json'
    need_spawn_server = True

    async def get(self, query, **kwargs):
        return await self.request('GET', query, **kwargs)

    async def post(self, query, data=None, **kwargs):
        return await self.request('POST', query, data, **kwargs)

    async def request(self, method, query, data=None, **kwargs):
        params = {}
        for key in kwargs:
            params[key] = dumps(kwargs[key])
        data = dumps(data)
        async with self.session.request(method, f'http://a{query}',
                                        data=data, params=params) as resp:
            print(unquote(str(resp.url)))
            resp.raise_for_status()
            content = await resp.content.read()
            return loads(content.decode())

    async def server_startup(self):
        for _ in range(20):
            try:
                await self.get('/meta/status')
                return
            except aiohttp.client_exceptions.ClientConnectorError:
                await asyncio.sleep(.5)
        raise Exception('timeout on server startup')

    async def server_shutdown(self, immediate=True):
        try:
            await self.post('/shutdown', mode='POWEROFF', immediate=immediate)
            raise Exception('expected ServerDisconnectedError')
        except aiohttp.client_exceptions.ServerDisconnectedError:
            return

    async def spawn_server(self):
        env = os.environ.copy()
        env['SUBIQUITY_REPLAY_TIMESCALE'] = '100'
        cmd = 'python3 -m subiquity.cmd.server --dry-run --bootloader uefi' \
              + ' --machine-config ' + self.machine_config
        cmd = cmd.split(' ')
        self.proc = await astart_command(cmd, env=env)
        self.server = asyncio.create_task(self.proc.communicate())

    async def asyncSetUp(self):
        if self.need_spawn_server:
            await self.spawn_server()

        # setup client
        conn = aiohttp.UnixConnector(path=socket_path)
        self.session = aiohttp.ClientSession(connector=conn)
        await self.server_startup()

    async def asyncTearDown(self):
        if self.need_spawn_server:
            await self.server_shutdown()
            await self.session.close()
            await self.server
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass


# class TestDebug(TestAPI):
#     need_spawn_server = False

#     @unittest.skip("useful for interactive debug only")
#     async def test_v2_delete_debug(self):
#         await self.get('/storage/v2')


class TestSimple(TestAPI):
    @timeout(5)
    async def test_not_bitlocker(self):
        resp = await self.get('/storage/has_bitlocker')
        self.assertEqual(0, len(resp))

    @timeout(10)
    async def test_server_flow(self):
        await self.post('/locale', 'en_US.UTF-8')
        keyboard = {
            'layout': 'us',
            'variant': '',
            'toggle': None
        }
        await self.post('/keyboard', keyboard)
        await self.post('/source', source_id='ubuntu-server')
        await self.post('/network')
        await self.post('/proxy', '')
        await self.post('/mirror', 'http://us.archive.ubuntu.com/ubuntu')
        resp = await self.get('/storage/guided')
        disk_id = resp['disks'][0]['id']
        choice = {"disk_id": disk_id}
        await self.post('/storage/v2/guided', choice=choice)
        await self.post('/storage/v2')
        await self.get('/meta/status', cur='WAITING')
        await self.post('/meta/confirm', tty='/dev/tty1')
        await self.get('/meta/status', cur='NEEDS_CONFIRMATION')
        identity = {
            'realname': 'ubuntu',
            'username': 'ubuntu',
            'hostname': 'ubuntu-server',
            'crypted_password': '$6$exDY1mhS4KUYCE/2$zmn9ToZwTKLhCw.b4/'
                                + 'b.ZRTIZM30JZ4QrOQ2aOXJ8yk96xpcCof0kx'
                                + 'KwuX1kqLG/ygbJ1f8wxED22bTL4F46P0'
        }
        await self.post('/identity', identity)
        ssh = {
            'install_server': False,
            'allow_pw': False,
            'authorized_keys': []
        }
        await self.post('/ssh', ssh)
        await self.post('/snaplist', [])
        for state in 'RUNNING', 'POST_WAIT', 'POST_RUNNING', 'UU_RUNNING':
            await self.get('/meta/status', cur=state)

    @timeout(5)
    async def test_default(self):
        choice = {'disk_id': 'disk-sda'}
        resp = await self.post('/storage/guided', choice=choice)
        self.assertEqual(7, len(resp['config']))
        self.assertEqual('/dev/sda', resp['config'][0]['path'])

    @timeout(5)
    async def test_guided_v2(self):
        choice = {'disk_id': 'disk-sda'}
        resp = await self.post('/storage/v2/guided', choice=choice)
        self.assertEqual(1, len(resp['disks']))
        self.assertEqual('disk-sda', resp['disks'][0]['id'])

    @timeout(5)
    async def test_v2_add_boot_partition(self):
        self.maxDiff = None
        disk_id = 'disk-sda'

        data = {
            'disk_id': disk_id,
            'partition': {
                'format': 'ext4',
                'mount': '/',
            }
        }
        simple_add = await self.post('/storage/v2/add_partition', data)
        self.assertEqual(2, len(simple_add['disks'][0]['partitions']))

        await self.post('/storage/v2/reset')

        await self.post('/storage/v2/add_boot_partition', disk_id=disk_id)
        manual_add = await self.post('/storage/v2/add_partition', data)
        self.assertEqual(simple_add, manual_add)


class TestWin10(TestAPI):
    machine_config = 'examples/win10.json'

    @timeout(5)
    async def test_bitlocker(self):
        resp = await self.get('/storage/has_bitlocker')
        self.assertEqual('BitLocker', resp[0]['partitions'][2]['format'])

    @timeout(5)
    async def test_delete_bad(self):
        data = {
            'disk_id': 'disk-sda',
            'partition': {
                'size': -1,
                'number': 5,
            }
        }
        with self.assertRaises(ClientResponseError):
            await self.post('/storage/v2/delete_partition', data)

    @timeout(5)
    async def test_v2_flow(self):
        disk_id = 'disk-sda'
        orig_resp = await self.get('/storage/v2')
        self.assertEqual(1, len(orig_resp['disks']))
        self.assertEqual('disk-sda', orig_resp['disks'][0]['id'])
        self.assertEqual(4, len(orig_resp['disks'][0]['partitions']))

        resp = await self.post('/storage/v2/reformat_disk', disk_id=disk_id)
        self.assertEqual(0, len(resp['disks'][0]['partitions']))

        data = {
            'disk_id': disk_id,
            'partition': {
                'number': 1,
                'format': 'ext3',
                'mount': '/',
            }
        }
        add_resp = await self.post('/storage/v2/add_partition', data)
        self.assertEqual(2, len(add_resp['disks'][0]['partitions']))
        self.assertEqual('ext3',
                         add_resp['disks'][0]['partitions'][1]['format'])

        data['partition']['number'] = 2
        data['partition']['format'] = 'ext4'
        resp = await self.post('/storage/v2/edit_partition', data)
        expected = add_resp['disks'][0]['partitions'][1]
        actual = resp['disks'][0]['partitions'][1]
        for key in 'size', 'number', 'mount', 'grub_device':
            self.assertEqual(expected[key], actual[key])
        self.assertEqual('ext4', resp['disks'][0]['partitions'][1]['format'])

        resp = await self.post('/storage/v2/delete_partition', data)
        self.assertEqual(1, len(resp['disks'][0]['partitions']))

        resp = await self.post('/storage/v2/reset')
        self.assertEqual(orig_resp, resp)

        choice = {'disk_id': disk_id}
        orig_resp = await self.post('/storage/v2/guided', choice=choice)
        await self.post('/storage/v2')
        resp = await self.get('/storage/v2')
        # posting to the endpoint shouldn't change the answer
        self.assertEqual(orig_resp, resp)

    @timeout(5)
    async def test_v2_free_for_partitions(self):
        disk_id = 'disk-sda'
        resp = await self.post('/storage/v2/reformat_disk', disk_id=disk_id)

        data = {
            'disk_id': disk_id,
            'partition': {
                'size': resp['disks'][0]['size'] // 2,
                'number': 1,
                'format': 'ext4',
                'mount': '/',
            }
        }
        resp = await self.post('/storage/v2/add_partition', data)
        self.assertEqual(2, len(resp['disks'][0]['partitions']))
        self.assertEqual('ext4', resp['disks'][0]['partitions'][1]['format'])
        self.assertEqual(42410704896, resp['disks'][0]['free_for_partitions'])

    @timeout(5)
    async def test_v2_delete_requires_reformat(self):
        disk_id = 'disk-sda'
        data = {
            'disk_id': disk_id,
            'partition': {
                'number': 4,
                'mount': '/',
                'format': 'ext4',
            }
        }
        await self.post('/storage/v2/edit_partition', data)
        with self.assertRaises(ClientResponseError):
            await self.post('/storage/v2/delete_partition', data)

    @timeout(5)
    async def test_v2_reuse(self):
        orig_resp = await self.get('/storage/v2')

        disk_id = 'disk-sda'
        data = {
            'disk_id': disk_id,
            'partition': {
                'number': 3,
                'format': 'ext4',
                'mount': '/',
            }
        }
        resp = await self.post('/storage/v2/edit_partition', data)
        orig_disk = orig_resp['disks'][0]
        disk = resp['disks'][0]
        self.assertEqual('/dev/sda', disk['path'])

        esp = disk['partitions'][0]
        self.assertIsNone(esp['wipe'])
        self.assertEqual('/boot/efi', esp['mount'])
        self.assertEqual('vfat', esp['format'])
        self.assertTrue(esp['grub_device'])

        part = disk['partitions'][1]
        expected = orig_disk['partitions'][1]
        self.assertEqual(expected, part)

        root = disk['partitions'][2]
        self.assertEqual('superblock', root['wipe'])
        self.assertEqual('/', root['mount'])
        self.assertEqual('ext4', root['format'])
        self.assertFalse(root['grub_device'])

        part = disk['partitions'][3]
        expected = orig_disk['partitions'][3]
        self.assertEqual(expected, part)

    @timeout(5)
    async def test_v2_gpt(self):
        resp = await self.get('/storage/v2')
        sda = first(resp['disks'], 'id', 'disk-sda')
        self.assertEqual('gpt', sda['ptable'])

    @timeout(5)
    async def test_add_rules(self):
        disk_id = 'disk-sda'
        await self.post('/storage/v2/reformat_disk', disk_id=disk_id)

        bad_partitions = [
            {'partition': {}},
            {'partition': {'format': 'ext4'}},
            {'partition': {'mount': '/'}},
        ]
        for partition in bad_partitions:
            with self.assertRaises(ClientResponseError):
                data = {'disk_id': disk_id, 'partition': partition}
                await self.post('/storage/v2/add_partition', data)

        for size, expected in ((None, 85360377856), (20 << 30, 20 << 30)):
            partition = {'format': 'ext4', 'mount': '/', 'size': size}
            data = {'disk_id': disk_id, 'partition': partition}
            resp = await self.post('/storage/v2/add_partition', data)
            sda = first(resp['disks'], 'id', disk_id)
            sda2 = first(sda['partitions'], 'number', 2)
            self.assertEqual(expected, sda2['size'])
            await self.post('/storage/v2/reformat_disk', disk_id=disk_id)

    @timeout(5)
    async def test_edit_rules(self):
        disk_id = 'disk-sda'
        data = {
            'disk_id': disk_id,
            'partition': {
                'number': 3,
                'format': 'ext4',
                'mount': '/',
                'wipe': None,
            }
        }
        await self.post('/storage/v2/edit_partition', data)

        data['partition']['size'] = 85240896512 // 2
        with self.assertRaises(ClientResponseError):
            await self.post('/storage/v2/edit_partition', data)

        data['partition']['size'] = None
        data['partition']['grub_device'] = True
        with self.assertRaises(ClientResponseError):
            await self.post('/storage/v2/edit_partition', data)

        data['partition']['grub_device'] = None
        data['partition']['format'] = 'btrfs'
        await self.post('/storage/v2/edit_partition', data)

    @timeout(5)
    async def test_todos_simple(self):
        disk_id = 'disk-sda'
        resp = await self.post('/storage/v2/reformat_disk', disk_id=disk_id)
        self.assertTrue(resp['todos_needs_root_mounted'])
        self.assertTrue(resp['todos_needs_bootloader_partition'])

        data = {
            'disk_id': disk_id,
            'partition': {
                'format': 'ext4',
                'mount': '/',
            }
        }
        resp = await self.post('/storage/v2/add_partition', data)
        self.assertFalse(resp['todos_needs_root_mounted'])
        self.assertFalse(resp['todos_needs_bootloader_partition'])

    @timeout(5)
    async def test_todos_manual(self):
        disk_id = 'disk-sda'
        resp = await self.post('/storage/v2/reformat_disk', disk_id=disk_id)
        self.assertTrue(resp['todos_needs_root_mounted'])
        self.assertTrue(resp['todos_needs_bootloader_partition'])

        resp = await self.post('/storage/v2/add_boot_partition',
                               disk_id=disk_id)
        self.assertTrue(resp['todos_needs_root_mounted'])
        self.assertFalse(resp['todos_needs_bootloader_partition'])

        data = {
            'disk_id': disk_id,
            'partition': {
                'format': 'ext4',
                'mount': '/',
            }
        }
        resp = await self.post('/storage/v2/add_partition', data)
        self.assertFalse(resp['todos_needs_root_mounted'])
        self.assertFalse(resp['todos_needs_bootloader_partition'])

    @timeout(5)
    async def test_todos_guided(self):
        disk_id = 'disk-sda'
        resp = await self.post('/storage/v2/reformat_disk', disk_id=disk_id)
        self.assertTrue(resp['todos_needs_root_mounted'])
        self.assertTrue(resp['todos_needs_bootloader_partition'])

        choice = {'disk_id': disk_id}
        resp = await self.post('/storage/v2/guided', choice=choice)
        self.assertFalse(resp['todos_needs_root_mounted'])
        self.assertFalse(resp['todos_needs_bootloader_partition'])

    @timeout(5)
    async def test_edit_partial(self):
        disk_id = 'disk-sda'
        await self.post('/storage/v2/reformat_disk', disk_id=disk_id)

        data = {
            'disk_id': disk_id,
            'partition': {
                'format': 'ext4',
                'mount': '/',
            }
        }
        await self.post('/storage/v2/add_partition', data)

        data['partition'].update({
            'number': 2,
            'format': None,
            'mount': '/home'
        })
        resp = await self.post('/storage/v2/edit_partition', data)

        sda = first(resp['disks'], 'id', disk_id)
        sda2 = first(sda['partitions'], 'number', 2)
        self.assertEqual('ext4', sda2['format'])
        self.assertEqual('/home', sda2['mount'])


class TestManyDisks(TestAPI):
    machine_config = 'examples/many-nics-and-disks.json'

    @timeout(5)
    async def test_v2_msdos(self):
        disk_id = 'disk-sda'
        resp = await self.get('/storage/v2')
        sda = first(resp['disks'], 'id', disk_id)
        self.assertEqual('msdos', sda['ptable'])

        sda5 = first(sda['partitions'], 'number', 5)
        sda5.update({'format': 'ext4', 'mount': '/'})
        data = {
            'disk_id': disk_id,
            'partition': sda5
        }
        await self.post('/storage/v2/edit_partition', data)
