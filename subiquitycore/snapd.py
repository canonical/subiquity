# Copyright 2019 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import contextlib
import glob
import json
import logging
import os
import time
from functools import partial
from typing import Any
from urllib.parse import quote_plus, urlencode

import attrs
import requests_unixsocket

from subiquitycore.async_helpers import run_in_thread
from subiquitycore.utils import run_command

log = logging.getLogger("subiquitycore.snapd")

# Every method in this module blocks. Do not call them from the main thread!


class SnapdConnection:
    # In LP: #2034715, we found that while some requests should be
    # non-blocking, they are actually blocking and exceeding one minute.
    # Extending the timeout helps.
    default_timeout_seconds = 600

    def __init__(self, root, sock):
        self.root = root
        self.url_base = "http+unix://{}/".format(quote_plus(sock))

    def get(self, path, **args):
        if args:
            path += "?" + urlencode(args)
        with requests_unixsocket.Session() as session:
            return session.get(
                self.url_base + path, timeout=self.default_timeout_seconds
            )

    def post(self, path, body, **args):
        if args:
            path += "?" + urlencode(args)
        with requests_unixsocket.Session() as session:
            return session.post(
                self.url_base + path,
                json=body,
                timeout=self.default_timeout_seconds,
            )

    def configure_proxy(self, proxy):
        log.debug("restarting snapd to pick up proxy config")
        dropin_dir = os.path.join(self.root, "etc/systemd/system/snapd.service.d")
        os.makedirs(dropin_dir, exist_ok=True)
        with open(os.path.join(dropin_dir, "snap_proxy.conf"), "w") as fp:
            fp.write(proxy.proxy_systemd_dropin())
        if self.root == "/":
            cmds = [
                ["systemctl", "daemon-reload"],
                ["systemctl", "restart", "snapd.service"],
            ]
        else:
            cmds = [["sleep", "2"]]
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


@attrs.define
class _FakeMemoryResponse:
    data: Any

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


class MemoryResponseSet:
    """Set of response for an endpoint which returns data stored in memory."""

    def __init__(self, data):
        self.data = data
        self.index = 0

    def next(self):
        d = self.data[self.index]
        self.index += 1
        return _FakeMemoryResponse(d)


class FakeSnapdConnection:
    def __init__(self, snap_data_dir, scale_factor, output_base):
        self.snap_data_dir = snap_data_dir
        self.scale_factor = scale_factor
        self.response_sets = {}
        self.output_base = output_base
        self.post_cb = {}

    def configure_proxy(self, proxy):
        log.debug("pretending to restart snapd to pick up proxy config")
        time.sleep(2 / self.scale_factor)

    def _fake_entropy(self, body) -> _FakeMemoryResponse:
        if body["action"] == "check-passphrase":
            entropy_bits = len(body["passphrase"])
            min_entropy_bits = 8
            optimal_entropy_bits = 10
            kind = "invalid-passphrase"
        else:
            entropy_bits = len(body["pin"])
            min_entropy_bits = 4
            optimal_entropy_bits = 6
            kind = "invalid-pin"

        if entropy_bits < min_entropy_bits:
            return _FakeMemoryResponse(
                {
                    "type": "error",
                    "status-code": 400,
                    "status": "Bad Request",
                    "result": {
                        "kind": kind,
                        "message": "did not pass quality checks",
                        "value": {
                            "entropy-bits": entropy_bits,
                            "min-entropy-bits": min_entropy_bits,
                            "optimal-entropy-bits": optimal_entropy_bits,
                            "reasons": ["low-entropy"],
                        },
                    },
                }
            )

        return _FakeMemoryResponse(
            {
                "type": "sync",
                "status-code": 200,
                "status": "OK",
                "result": {
                    "entropy-bits": entropy_bits,
                    "min-entropy-bits": min_entropy_bits,
                    "optimal-entropy-bits": optimal_entropy_bits,
                },
            }
        )

    def post(self, path, body, *, raise_for_status=True, **args):
        if path == "v2/snaps/subiquity" and body["action"] == "refresh":
            # The post-refresh hook does this in the real world.
            update_marker_file = self.output_base + "/run/subiquity/updating"
            open(update_marker_file, "w").close()
            return _FakeMemoryResponse(
                {
                    "type": "async",
                    "change": "7",
                    "status-code": 200,
                    "status": "OK",
                }
            )
        change = None
        sync_result = None
        if path == "v2/snaps/subiquity" and body["action"] == "switch":
            change = "8"
        if path.startswith("v2/systems/") and body["action"] == "install":
            system = path.split("/")[2]
            step = body["step"]
            if step == "finish":
                if system == "finish-fail":
                    change = "15"
                else:
                    change = "5"
            elif step == "setup-storage-encryption":
                change = "6"
            elif step == "generate-recovery-key":
                sync_result = {"recovery-key": "my-recovery-key"}
        elif path.startswith("v2/systems/") and body["action"] in (
            "check-passphrase",
            "check-pin",
        ):
            return self._fake_entropy(body)

        if change is not None:
            return _FakeMemoryResponse(
                {
                    "type": "async",
                    "change": change,
                    "status-code": 200,
                    "status": "Accepted",
                }
            )
        elif sync_result:
            return _FakeMemoryResponse(
                {
                    "type": "sync",
                    "status-code": 200,
                    "status": "OK",
                    "result": sync_result,
                }
            )
        if path in self.post_cb:
            return _FakeMemoryResponse(self.post_cb[path](path, body, **args))

        raise Exception(
            "Don't know how to fake POST response to {}".format((path, args))
        )

    def get(self, path, *, raise_for_status=True, **args):
        if "change" not in path:
            time.sleep(1 / self.scale_factor)
        filename = path.replace("/", "-")
        if args:
            filename += "-" + urlencode(sorted(args.items()))
        if filename in self.response_sets:
            return self.response_sets[filename].next()
        filepath = os.path.join(self.snap_data_dir, filename)
        if os.path.exists(filepath + ".json"):
            return _FakeFileResponse(filepath + ".json")
        if os.path.isdir(filepath):
            files = sorted(glob.glob(os.path.join(filepath, "*.json")))
            rs = self.response_sets[filename] = ResponseSet(files)
            return rs.next()
        raise Exception(
            "Don't know how to fake GET response to {}".format((path, args))
        )


def get_fake_connection(scale_factor=1000, output_base=None):
    proj_dir = os.path.dirname(os.path.dirname(__file__))
    if output_base is None:
        output_base = os.path.join(proj_dir, ".subiquity")
    return FakeSnapdConnection(
        os.path.join(proj_dir, "examples", "snaps"), scale_factor, output_base
    )


class AsyncSnapd:
    def __init__(self, connection):
        self.connection = connection

    async def get(self, path, raise_for_status=True, **args):
        response = await run_in_thread(partial(self.connection.get, path, **args))
        if raise_for_status:
            response.raise_for_status()
        return response.json()

    async def post(self, path, body, raise_for_status=True, **args):
        response = await run_in_thread(
            partial(self.connection.post, path, body, **args)
        )
        if raise_for_status:
            response.raise_for_status()
        return response.json()

    async def post_and_wait(self, path, body, **args):
        change = (await self.post(path, body, **args))["change"]
        change_path = "v2/changes/{}".format(change)
        get_kwargs = {}
        with contextlib.suppress(KeyError):
            get_kwargs["raise_for_status"] = args["raise_for_status"]
        while True:
            result = await self.get(change_path, **get_kwargs)
            if result["result"]["status"] == "Done":
                break
            await asyncio.sleep(0.1)
