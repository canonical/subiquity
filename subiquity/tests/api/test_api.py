#!/usr/bin/env python3

import aiohttp
import async_timeout
import asyncio
from functools import wraps
import json
import logging
import os
import sys
import unittest

from subiquitycore.utils import astart_command


logging.basicConfig(level=logging.DEBUG)
socket_path = '.subiquity/socket'


ver = sys.version_info
if ver.major < 3 or ver.minor < 8:
    raise Exception('skip asyncio testing')


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
    return json.loads(data) if data else None


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


async def guided(client):
    resp = await client.get('/storage/guided')
    disk_id = resp['disks'][0]['id']
    choice = {
            "disk_id": disk_id,
            "use_lvm": False,
            "password": None,
    }
    await client.post('/storage/v2/guided', choice=choice)
    await client.post('/storage/v2')


async def v2(client):
    storage_resp = await client.get('/storage/v2')
    disk = storage_resp['disks'][0]
    disk_id = disk['id']
    data = {
        'disk_id': disk_id,
        'partition': {
            'size': -1,
            'number': 4,
            'mount': '',
            'format': '',
        }
    }
    await client.post('/storage/v2/delete_partition', data)
    await client.post('/storage/v2/reformat_disk', disk_id=disk_id)
    data['partition']['number'] = 2
    data['partition']['format'] = 'ext3'
    await client.post('/storage/v2/add_partition', data)
    data['partition']['format'] = 'ext4'
    await client.post('/storage/v2/edit_partition', data)
    await client.post('/storage/v2/reset')
    choice = {
        "disk_id": disk_id,
        "use_lvm": False,
        "password": None,
    }
    await client.post('/storage/v2/guided', choice=choice)
    await client.post('/storage/v2')


class TestAPI(unittest.IsolatedAsyncioTestCase):
    machine_config = 'examples/simple.json'

    async def get(self, query, **kwargs):
        return await self.request('GET', query, **kwargs)

    async def post(self, query, data=None, **kwargs):
        return await self.request('POST', query, data, **kwargs)

    async def request(self, method, query, data=None, **kwargs):
        params = {}
        for key in kwargs:
            params[key] = dumps(kwargs[key])
        data = dumps(data)
        info = f'{method} {query}'
        if params:
            for i, key in enumerate(params):
                joiner = '?' if i == 0 else '&'
                info += f'{joiner}{key}={params[key]}'
        print(info)
        async with self.session.request(method, f'http://a{query}',
                                        data=data, params=params) as resp:
            content = await resp.content.read()
            content = content.decode()
            if resp.status != 200:
                raise ClientException(content)
            return loads(content)

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

    async def asyncSetUp(self):
        # start server process
        env = os.environ.copy()
        env['SUBIQUITY_REPLAY_TIMESCALE'] = '100'
        cmd = 'python3 -m subiquity.cmd.server --dry-run --bootloader uefi' \
              + ' --machine-config ' + self.machine_config
        cmd = cmd.split(' ')
        self.proc = await astart_command(cmd, env=env)
        self.server = asyncio.create_task(self.proc.communicate())

        # setup client
        conn = aiohttp.UnixConnector(path=socket_path)
        self.session = aiohttp.ClientSession(connector=conn)
        await self.server_startup()

    async def asyncTearDown(self):
        await self.server_shutdown()
        await self.session.close()
        await self.server
        try:
            self.proc.kill()
        except ProcessLookupError:
            pass


class TestSimple(TestAPI):
    @timeout(5)
    async def test_not_bitlocker(self):
        resp = await self.get('/storage/has_bitlocker')
        json_print(resp)
        self.assertEqual(len(resp), 0)

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
        await guided(self)
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


class TestBitlocker(TestAPI):
    machine_config = 'examples/win10.json'

    @timeout(5)
    async def test_bitlocker(self):
        resp = await self.get('/storage/has_bitlocker')
        json_print(resp)
        self.assertEqual(resp[0]['partitions'][2]['format'], 'BitLocker')
