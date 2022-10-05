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

import asyncio
from functools import partial
import glob
import json
import logging
import os
import time
from urllib.parse import (
    quote_plus,
    urlencode,
    )

from subiquitycore.async_helpers import run_in_thread
from subiquitycore.utils import run_command

import requests_unixsocket


log = logging.getLogger('subiquitycore.snapd')

# Every method in this module blocks. Do not call them from the main thread!


class SnapdConnection:
    def __init__(self, root, sock):
        self.root = root
        self.url_base = "http+unix://{}/".format(quote_plus(sock))

    def get(self, path, **args):
        if args:
            path += '?' + urlencode(args)
        with requests_unixsocket.Session() as session:
            return session.get(self.url_base + path, timeout=60)

    def post(self, path, body, **args):
        if args:
            path += '?' + urlencode(args)
        with requests_unixsocket.Session() as session:
            return session.post(
                self.url_base + path, data=json.dumps(body),
                timeout=60)

    def configure_proxy(self, proxy):
        log.debug("restarting snapd to pick up proxy config")
        dropin_dir = os.path.join(
            self.root, 'etc/systemd/system/snapd.service.d')
        os.makedirs(dropin_dir, exist_ok=True)
        with open(os.path.join(dropin_dir, 'snap_proxy.conf'), 'w') as fp:
            fp.write(proxy.proxy_systemd_dropin())
        if self.root == '/':
            cmds = [
                ['systemctl', 'daemon-reload'],
                ['systemctl', 'restart', 'snapd.service'],
                ]
        else:
            cmds = [['sleep', '2']]
        for cmd in cmds:
            run_command(cmd)


class _FakeFileResponse:

    def __init__(self, path):
        self.path = path

    def raise_for_status(self):
        pass

    def json(self):
        with open(self.path) as fp:
            return json.load(fp)


class _FakeMemoryResponse:

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class ResponseSet:
    """Responses for a endpoint that returns different data each time.

    Motivating example is v2/changes/$change_id."""

    def __init__(self, files):
        self.files = files
        self.index = 0

    def next(self):
        f = self.files[self.index]
        d = int(os.environ.get("SUBIQUITY_REPLAY_TIMESCALE", 1))
        # Make sure we return the last response even when we skip most
        # of them.
        if d > 1 and self.index + d >= len(self.files):
            self.index = len(self.files) - 1
        else:
            self.index += d
        return _FakeFileResponse(f)


class FakeSnapdConnection:
    def __init__(self, snap_data_dir, scale_factor, output_base):
        self.snap_data_dir = snap_data_dir
        self.scale_factor = scale_factor
        self.response_sets = {}
        self.output_base = output_base

    def configure_proxy(self, proxy):
        log.debug("pretending to restart snapd to pick up proxy config")
        time.sleep(2/self.scale_factor)

    def post(self, path, body, **args):
        if path == "v2/snaps/subiquity" and body['action'] == 'refresh':
            # The post-refresh hook does this in the real world.
            update_marker_file = self.output_base + '/run/subiquity/updating'
            open(update_marker_file, 'w').close()
            return _FakeMemoryResponse({
                "type": "async",
                "change": "7",
                "status-code": 200,
                "status": "OK",
                })
        if path == "v2/snaps/subiquity" and body['action'] == 'switch':
            return _FakeMemoryResponse({
                "type": "async",
                "change": "8",
                "status-code": 200,
                "status": "Accepted",
                })
        raise Exception(
            "Don't know how to fake POST response to {}".format((path, args)))

    def get(self, path, **args):
        time.sleep(1/self.scale_factor)
        filename = path.replace('/', '-')
        if args:
            filename += '-' + urlencode(sorted(args.items()))
        if filename in self.response_sets:
            return self.response_sets[filename].next()
        filepath = os.path.join(self.snap_data_dir, filename)
        if os.path.exists(filepath + '.json'):
            return _FakeFileResponse(filepath + '.json')
        if os.path.isdir(filepath):
            files = sorted(glob.glob(os.path.join(filepath, '*.json')))
            rs = self.response_sets[filename] = ResponseSet(files)
            return rs.next()
        raise Exception(
            "Don't know how to fake GET response to {}".format((path, args)))


class AsyncSnapd:

    def __init__(self, connection):
        self.connection = connection

    async def get(self, path, **args):
        response = await run_in_thread(
            partial(self.connection.get, path, **args))
        response.raise_for_status()
        return response.json()

    async def post(self, path, body, **args):
        response = await run_in_thread(
            partial(self.connection.post, path, body, **args))
        response.raise_for_status()
        return response.json()['change']

    async def post_and_wait(self, path, body, **args):
        change = await self.post(path, body, **args)
        change_path = 'v2/changes/{}'.format(change)
        while True:
            result = await self.get(change_path)
            if result["result"]["status"] == "Done":
                break
            await asyncio.sleep(0.1)
