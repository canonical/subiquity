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

import asyncio
import contextlib
import itertools
import json
import os
import re
import tempfile
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch
from urllib.parse import unquote

import aiohttp
import async_timeout
import yaml
from aiohttp.client_exceptions import ClientResponseError

from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized
from subiquitycore.utils import astart_command, matching_dicts

default_timeout = 10


def match(items, **kw):
    typename = kw.pop("_type", None)
    if typename is not None:
        kw["$type"] = typename
    return matching_dicts(items, **kw)


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
        if data == "" or data is None:  # json.loads likes neither of these
            return None
        return json.loads(data)

    def dumps(self, data):
        # if the data we're dumping is literally False,
        # we want that to be 'false'
        if data or isinstance(data, bool):
            return json.dumps(data, separators=(",", ":"))
        elif data is not None:
            return '""'
        else:
            return data

    async def get(self, query, **kwargs):
        return await self.request("GET", query, **kwargs)

    async def post(self, query, data=None, **kwargs):
        return await self.request("POST", query, data, **kwargs)

    async def request(
        self, method, query, data=None, full_response=False, headers=None, **kwargs
    ):
        """send a GET or POST to the test instance
        args:
            method: 'GET' or 'POST'
            query: endpoint, such as '/locale'

        keyword arguments:
            data: body of request
            full_response: if True, change the return value to a tuple of
                           (response content, raw response object)
            headers: dict of custom headers to include in request
            all other keyword arguments are turned into query arguments

            get('/meta/status', cur='WAITING') is equivalent to
            get('/meta/status?cur="WAITING"')

        returns:
            python data of response content (see also full_response arg)
        """
        params = {k: self.dumps(v) for k, v in kwargs.items()}
        data = self.dumps(data)
        async with self.session.request(
            method, f"http://a{query}", data=data, params=params, headers=headers
        ) as resp:
            print(unquote(str(resp.url)))
            content = await resp.content.read()
            content = content.decode()
            if 400 <= resp.status:
                print(content)
                resp.raise_for_status()
            if full_response:
                return (self.loads(content), resp)
            return self.loads(content)

    async def poll_startup(self, allow_error: bool = False):
        for _ in range(default_timeout * 10):
            try:
                resp = await self.get("/meta/status")
                if resp["state"] in (
                    "STARTING_UP",
                    "CLOUD_INIT_WAIT",
                    "EARLY_COMMANDS",
                ):
                    await asyncio.sleep(0.5)
                    continue
                if resp["state"] == "ERROR" and not allow_error:
                    raise Exception("server in error state")
                return
            except aiohttp.client_exceptions.ClientConnectorError:
                await asyncio.sleep(0.5)
        raise Exception("timeout on server startup")


class Server(Client):
    async def server_shutdown(self, immediate=True):
        try:
            await self.post("/shutdown", mode="POWEROFF", immediate=immediate)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            return

    async def spawn(
        self, output_base, socket, machine_config, bootloader="uefi", extra_args=None
    ):
        env = os.environ.copy()
        env["SUBIQUITY_REPLAY_TIMESCALE"] = "100"
        cmd = [
            "python3",
            "-m",
            "subiquity.cmd.server",
            "--dry-run",
            "--bootloader",
            bootloader,
            "--socket",
            socket,
            "--output-base",
            output_base,
            "--machine-config",
            machine_config,
        ]
        if extra_args is not None:
            cmd.extend(extra_args)
        self.proc = await astart_command(cmd, env=env)
        self._output_base = output_base

    def output_base(self) -> Optional[str]:
        return self._output_base

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
            # https://github.com/python/cpython/issues/88050
            # fixed in python 3.11
            self.proc._transport.close()


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
            with open(self.orig_path, "r") as fp:
                data = json.load(fp)
            yield data
            self.path = self.outer.tmp_path("machine-config.json")
            with open(self.path, "w") as fp:
                json.dump(data, fp)

    def machineConfig(self, path):
        return self._MachineConfig(self, path)

    def assertDictSubset(self, expected, actual, msg=None):
        """All keys in dictionary expected, and matching values, must match
        keys and values in actual.  Actual may contain additional keys and
        values that don't appear in expected, and this is not a failure."""

        if msg is None:
            msg = ""
        else:
            msg = " " + msg
        for k, v in expected.items():
            self.assertEqual(v, actual[k], msg=k + msg)


async def poll_for_socket_exist(socket_path):
    for _ in range(default_timeout * 5):
        # test level timeout will trigger first, this loop is just a fallback
        if os.path.exists(socket_path):
            return
        await asyncio.sleep(0.1)
    raise Exception("timeout looking for socket to exist")


@contextlib.contextmanager
def tempdirs(*args, **kwargs):
    # This does the following:
    # * drop in replacement for TemporaryDirectory that doesn't cleanup, so
    #   that the log files can be examined later
    # * make it an otherwise-unnecessary contextmanager so that the indentation
    #   of the caller can be preserved
    prefix = "/tmp/testapi/"
    os.makedirs(prefix, exist_ok=True)
    tempdir = tempfile.mkdtemp(prefix=prefix)
    print(tempdir)
    yield tempdir


@contextlib.asynccontextmanager
async def start_server_factory(factory, *args, allow_error: bool = False, **kwargs):
    with tempfile.TemporaryDirectory() as tempdir:
        socket_path = f"{tempdir}/socket"
        conn = aiohttp.UnixConnector(path=socket_path)
        async with aiohttp.ClientSession(connector=conn) as session:
            server = factory(session)
            try:
                await server.spawn(tempdir, socket_path, *args, **kwargs)
                await poll_for_socket_exist(socket_path)
                await server.poll_startup(allow_error=allow_error)
                yield server
            finally:
                await server.close()


@contextlib.asynccontextmanager
async def start_server(*args, set_first_source=True, source=None, **kwargs):
    async with start_server_factory(Server, *args, **kwargs) as instance:
        if set_first_source:
            sources = await instance.get("/source")
            if sources is None:
                raise Exception("unexpected /source response")
            await instance.post("/source", source_id=sources["sources"][0]["id"])
        while True:
            resp = await instance.get("/storage/v2")
            print(resp)
            if resp["status"] != "PROBING":
                break
            await asyncio.sleep(0.5)
        yield instance


@contextlib.asynccontextmanager
async def connect_server(*args, **kwargs):
    # This is not used by the tests directly, but can be convenient when
    # wanting to debug the server process.  Change a test's start_server
    # to connect_server, disable the test timeout, and run just that test.
    socket_path = ".subiquity/socket"
    conn = aiohttp.UnixConnector(path=socket_path)
    async with aiohttp.ClientSession(connector=conn) as session:
        yield Client(session)


class TestBitlocker(TestAPI):
    @timeout()
    async def test_has_bitlocker(self):
        async with start_server("examples/machines/win10.json") as inst:
            resp = await inst.get("/storage/has_bitlocker")
            self.assertEqual(1, len(resp))

    @timeout()
    async def test_not_bitlocker(self):
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/storage/has_bitlocker")
            self.assertEqual(0, len(resp))


class TestFlow(TestAPI):
    @timeout(2)
    async def test_serverish_flow(self):
        async with start_server("examples/machines/simple.json") as inst:
            await inst.post("/locale", "en_US.UTF-8")
            keyboard = {"layout": "us", "variant": "", "toggle": None}
            await inst.post("/keyboard", keyboard)
            await inst.post("/source", source_id="ubuntu-server", search_drivers=True)
            await inst.post("/network")
            await inst.post("/proxy", "")
            await inst.post(
                "/mirror", {"elected": "http://us.archive.ubuntu.com/ubuntu"}
            )

            resp = await inst.get("/storage/v2/guided?wait=true")
            [reformat, manual] = resp["targets"]
            self.assertEqual("DIRECT", reformat["allowed"][0])
            await inst.post(
                "/storage/v2/guided",
                {
                    "target": reformat,
                    "capability": reformat["allowed"][0],
                },
            )
            await inst.post("/storage/v2")
            await inst.get("/meta/status", cur="WAITING")
            await inst.post("/meta/confirm", tty="/dev/tty1")
            await inst.get("/meta/status", cur="NEEDS_CONFIRMATION")
            identity = {
                "realname": "ubuntu",
                "username": "ubuntu",
                "hostname": "ubuntu-server",
                "crypted_password": "$6$exDY1mhS4KUYCE/2$zmn9ToZwTKLhCw.b4/"
                + "b.ZRTIZM30JZ4QrOQ2aOXJ8yk96xpcCof0kx"
                + "KwuX1kqLG/ygbJ1f8wxED22bTL4F46P0",
            }
            await inst.post("/identity", identity)
            ssh = {"install_server": False, "allow_pw": False, "authorized_keys": []}
            await inst.post("/ssh", ssh)
            await inst.post("/snaplist", [])
            await inst.post("/drivers", {"install": False})
            ua_params = {
                "token": "a1b2c3d4e6f7g8h9I0K1",
            }
            await inst.post("/ubuntu_pro", ua_params)
            for state in "RUNNING", "WAITING", "RUNNING", "UU_RUNNING":
                await inst.get("/meta/status", cur=state)

    @timeout()
    async def test_v2_flow(self):
        cfg = self.machineConfig("examples/machines/simple.json")
        with cfg.edit() as data:
            attrs = data["storage"]["blockdev"]["/dev/sda"]["attrs"]
            attrs["size"] = str(10 << 30)
        extra_args = ["--source-catalog", "examples/sources/desktop.yaml"]
        async with start_server(cfg, extra_args=extra_args) as inst:
            disk_id = "disk-sda"
            orig_resp = await inst.get("/storage/v2")
            [sda] = match(orig_resp["disks"], id=disk_id)
            self.assertTrue(len(sda["partitions"]) > 0)

            data = {"disk_id": disk_id}
            resp = await inst.post("/storage/v2/reformat_disk", data)
            [sda] = match(resp["disks"], id=disk_id)
            [gap] = sda["partitions"]
            self.assertEqual("Gap", gap["$type"])

            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "format": "ext3",
                    "mount": "/",
                },
            }
            add_resp = await inst.post("/storage/v2/add_partition", data)
            [sda] = add_resp["disks"]
            [root] = match(sda["partitions"], mount="/")
            self.assertEqual("ext3", root["format"])

            data = {
                "disk_id": disk_id,
                "partition": {
                    "number": root["number"],
                    "format": "ext4",
                    "wipe": "superblock",
                },
            }
            edit_resp = await inst.post("/storage/v2/edit_partition", data)

            [add_sda] = add_resp["disks"]
            [add_root] = match(add_sda["partitions"], mount="/")

            [edit_sda] = edit_resp["disks"]
            [edit_root] = match(edit_sda["partitions"], mount="/")

            for key in "size", "number", "mount", "boot":
                self.assertEqual(add_root[key], edit_root[key], key)
            self.assertEqual("ext4", edit_root["format"])

            del_resp = await inst.post("/storage/v2/delete_partition", data)
            [sda] = del_resp["disks"]
            [p, g] = sda["partitions"]
            self.assertEqual("Partition", p["$type"])
            self.assertEqual("Gap", g["$type"])

            reset_resp = await inst.post("/storage/v2/reset")
            self.assertEqual(orig_resp, reset_resp)

            resp = await inst.get("/storage/v2/guided")
            [reformat] = match(resp["targets"], _type="GuidedStorageTargetReformat")
            data = {
                "target": reformat,
                "capability": reformat["allowed"][0],
            }
            await inst.post("/storage/v2/guided", data)
            after_guided_resp = await inst.get("/storage/v2")
            post_resp = await inst.post("/storage/v2")
            # posting to the endpoint shouldn't change the answer
            self.assertEqual(after_guided_resp, post_resp)


class TestGuided(TestAPI):
    @timeout()
    async def test_guided_v2_reformat(self):
        cfg = "examples/machines/win10-along-ubuntu.json"
        async with start_server(cfg) as inst:
            resp = await inst.get("/storage/v2/guided")
            [reformat] = match(resp["targets"], _type="GuidedStorageTargetReformat")
            resp = await inst.post(
                "/storage/v2/guided",
                {
                    "target": reformat,
                    "capability": reformat["allowed"][0],
                },
            )
            self.assertEqual(reformat, resp["configured"]["target"])
            resp = await inst.get("/storage/v2")
            [p1, p2] = resp["disks"][0]["partitions"]
            expected_p1 = {
                "$type": "Partition",
                "boot": True,
                "format": "fat32",
                "grub_device": True,
                "mount": "/boot/efi",
                "number": 1,
                "preserve": False,
                "wipe": "superblock",
            }
            self.assertDictSubset(expected_p1, p1)
            expected_p2 = {
                "number": 2,
                "mount": "/",
                "format": "ext4",
                "preserve": False,
                "wipe": "superblock",
            }
            self.assertDictSubset(expected_p2, p2)

            v1resp = await inst.get("/storage")
            parts = match(v1resp["config"], type="partition")
            for p in parts:
                self.assertFalse(p["preserve"], p)
                self.assertEqual("superblock", p.get("wipe"), p)

    @timeout()
    async def test_guided_v2_resize(self):
        cfg = "examples/machines/win10-along-ubuntu.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            orig_resp = await inst.get("/storage/v2")
            [orig_p1, orig_p2, orig_p3, orig_p4, orig_p5] = orig_resp["disks"][0][
                "partitions"
            ]
            resp = await inst.get("/storage/v2/guided")
            [resize_ntfs, resize_ext4] = match(
                resp["targets"], _type="GuidedStorageTargetResize"
            )
            resize_ntfs["new_size"] = 30 << 30
            data = {
                "target": resize_ntfs,
                "capability": resize_ntfs["allowed"][0],
            }
            resp = await inst.post("/storage/v2/guided", data)
            self.assertEqual(resize_ntfs, resp["configured"]["target"])
            resp = await inst.get("/storage/v2")
            [p1, p2, p3, p6, p4, p5] = resp["disks"][0]["partitions"]
            expected_p1 = {
                "$type": "Partition",
                "boot": True,
                "format": "vfat",
                "grub_device": True,
                "mount": "/boot/efi",
                "number": 1,
                "size": orig_p1["size"],
                "resize": None,
                "wipe": None,
            }
            self.assertDictSubset(expected_p1, p1)
            self.assertEqual(orig_p2, p2)
            self.assertEqual(orig_p4, p4)
            self.assertEqual(orig_p5, p5)
            expected_p6 = {
                "number": 6,
                "mount": "/",
                "format": "ext4",
            }
            self.assertDictSubset(expected_p6, p6)

    @timeout()
    async def test_guided_v2_use_gap(self):
        cfg = self.machineConfig("examples/machines/win10-along-ubuntu.json")
        with cfg.edit() as data:
            pt = data["storage"]["blockdev"]["/dev/sda"]["partitiontable"]
            [node] = match(pt["partitions"], node="/dev/sda5")
            pt["partitions"].remove(node)
            del data["storage"]["blockdev"]["/dev/sda5"]
            del data["storage"]["filesystem"]["/dev/sda5"]
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            orig_resp = await inst.get("/storage/v2")
            [orig_p1, orig_p2, orig_p3, orig_p4, gap] = orig_resp["disks"][0][
                "partitions"
            ]
            resp = await inst.get("/storage/v2/guided")
            [use_gap] = match(resp["targets"], _type="GuidedStorageTargetUseGap")
            data = {
                "target": use_gap,
                "capability": use_gap["allowed"][0],
            }
            resp = await inst.post("/storage/v2/guided", data)
            self.assertEqual(use_gap, resp["configured"]["target"])
            resp = await inst.get("/storage/v2")
            [p1, p2, p3, p4, p5] = resp["disks"][0]["partitions"]
            expected_p1 = {
                "$type": "Partition",
                "boot": True,
                "format": "vfat",
                "grub_device": True,
                "mount": "/boot/efi",
                "number": 1,
                "size": orig_p1["size"],
                "resize": None,
                "wipe": None,
            }
            self.assertDictSubset(expected_p1, p1)
            self.assertEqual(orig_p2, p2)
            self.assertEqual(orig_p3, p3)
            self.assertEqual(orig_p4, p4)
            expected_p5 = {
                "number": 5,
                "mount": "/",
                "format": "ext4",
            }
            self.assertDictSubset(expected_p5, p5)

    @timeout()
    async def test_guided_v2_resize_logical(self):
        cfg = "examples/machines/threebuntu-on-msdos.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get("/storage/v2/guided")
            [resize] = match(
                resp["targets"], _type="GuidedStorageTargetResize", partition_number=6
            )
            data = {
                "target": resize,
                "capability": resize["allowed"][0],
            }
            resp = await inst.post("/storage/v2/guided", data)
            self.assertEqual(resize, resp["configured"]["target"])
            # should not throw a Gap Not Found exception


class TestCore(TestAPI):
    @timeout()
    async def test_basic_core_boot(self):
        cfg = self.machineConfig("examples/machines/simple.json")
        with cfg.edit() as data:
            attrs = data["storage"]["blockdev"]["/dev/sda"]["attrs"]
            attrs["size"] = str(25 << 30)
        kw = dict(
            bootloader="uefi",
            extra_args=[
                "--storage-version",
                "2",
                "--source-catalog",
                "examples/sources/install-canary.yaml",
                "--dry-run-config",
                "examples/dry-run-configs/tpm.yaml",
            ],
        )
        async with start_server(cfg, **kw) as inst:
            await inst.post("/source", source_id="ubuntu-desktop")
            resp = await inst.get("/storage/v2/guided", wait=True)
            [reformat, manual] = resp["targets"]
            self.assertIn("CORE_BOOT_PREFER_ENCRYPTED", reformat["allowed"])
            data = dict(target=reformat, capability="CORE_BOOT_ENCRYPTED")
            await inst.post("/storage/v2/guided", data)
            v2resp = await inst.get("/storage/v2")
            [d] = v2resp["disks"]
            pgs = d["partitions"]
            [p4] = match(pgs, number=4)
            # FIXME The current model has a ~13GiB gap between p1 and p2.
            #       Presumably this will be removed later.
            [p1, g1, p2, p3, p4] = d["partitions"]
            e1 = dict(offset=1 << 20, mount="/boot/efi")
            self.assertDictSubset(e1, p1)
            self.assertDictSubset(dict(mount="/boot"), p2)
            self.assertDictSubset(dict(mount=None), p3)
            self.assertDictSubset(dict(mount="/"), p4)

    @timeout()
    async def test_basic_core_boot_cmdline_disable(self):
        cfg = self.machineConfig("examples/machines/simple.json")
        with cfg.edit() as data:
            attrs = data["storage"]["blockdev"]["/dev/sda"]["attrs"]
            attrs["size"] = str(25 << 30)
        kw = dict(
            bootloader="uefi",
            extra_args=[
                "--storage-version",
                "2",
                "--source-catalog",
                "examples/sources/install-canary.yaml",
                "--dry-run-config",
                "examples/dry-run-configs/tpm.yaml",
                "--no-enhanced-secureboot",
            ],
        )
        async with start_server(cfg, **kw) as inst:
            await inst.post("/source", source_id="ubuntu-desktop")
            resp = await inst.get("/storage/v2/guided", wait=True)
            [reformat, manual] = resp["targets"]
            for capability in reformat["allowed"]:
                self.assertNotIn("CORE_BOOT", capability)
            data = dict(target=reformat, capability="CORE_BOOT_ENCRYPTED")
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/guided", data)

    @timeout()
    async def test_basic_no_core_boot_bios(self):
        cfg = self.machineConfig("examples/machines/simple.json")
        with cfg.edit() as data:
            attrs = data["storage"]["blockdev"]["/dev/sda"]["attrs"]
            attrs["size"] = str(25 << 30)
        kw = dict(
            bootloader="bios",
            extra_args=[
                "--storage-version",
                "2",
                "--source-catalog",
                "examples/sources/install-canary.yaml",
                "--dry-run-config",
                "examples/dry-run-configs/tpm.yaml",
            ],
        )
        async with start_server(cfg, **kw) as inst:
            await inst.post("/source", source_id="ubuntu-desktop")
            resp = await inst.get("/storage/v2/guided", wait=True)
            [reformat, manual] = resp["targets"]
            for capability in reformat["allowed"]:
                self.assertNotIn("CORE_BOOT", capability)
            data = dict(target=reformat, capability="CORE_BOOT_ENCRYPTED")
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/guided", data)


class TestAdd(TestAPI):
    @timeout()
    async def test_v2_add_boot_partition(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"

            resp = await inst.post("/storage/v2")
            [sda] = match(resp["disks"], id=disk_id)
            [gap] = match(sda["partitions"], _type="Gap")

            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                },
            }
            single_add = await inst.post("/storage/v2/add_partition", data)
            self.assertEqual(2, len(single_add["disks"][0]["partitions"]))
            self.assertTrue(single_add["disks"][0]["boot_device"])

            await inst.post("/storage/v2/reset")

            # these manual steps are expected to be mostly equivalent to just
            # adding the single partition and getting the automatic boot
            # partition
            resp = await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)
            [sda] = match(resp["disks"], id=disk_id)
            [gap] = match(sda["partitions"], _type="Gap")
            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                },
            }
            manual_add = await inst.post("/storage/v2/add_partition", data)

            # the only difference is the partition number assigned - when we
            # explicitly add_boot_partition, that is the first partition
            # created, versus when we add_partition and get a boot partition
            # implicitly
            for resp in single_add, manual_add:
                for part in resp["disks"][0]["partitions"]:
                    part.pop("number")
                    part.pop("path")

            self.assertEqual(single_add, manual_add)

    @timeout()
    async def test_v2_deny_multiple_add_boot_partition(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)

    @timeout()
    async def test_v2_deny_multiple_add_boot_partition_BIOS(self):
        cfg = "examples/machines/simple.json"
        async with start_server(cfg, "bios") as inst:
            disk_id = "disk-sda"
            await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)

    @timeout()
    async def test_add_format_required(self):
        disk_id = "disk-sda"
        async with start_server("examples/machines/simple.json") as inst:
            bad_partitions = [
                {},
                {"mount": "/"},
            ]
            for partition in bad_partitions:
                data = {"disk_id": disk_id, "partition": partition}
                with self.assertRaises(ClientResponseError, msg=f"data {data}"):
                    await inst.post("/storage/v2/add_partition", data)

    @timeout()
    async def test_add_unformatted_ok(self):
        disk_id = "disk-sda"
        async with start_server("examples/machines/simple.json") as inst:
            for fmt in ("", None):
                await inst.post("/storage/v2/reset")
                disk_id = "disk-sda"
                resp = await inst.get("/storage/v2")
                [sda] = match(resp["disks"], id=disk_id)
                [gap] = sda["partitions"]

                data = {
                    "disk_id": disk_id,
                    "gap": gap,
                    "partition": dict(format=fmt, mount="/"),
                }
                await inst.post("/storage/v2/add_partition", data)

                v1resp = await inst.get("/storage")
                empties = match(v1resp["config"], type="format", fstype="")
                self.assertEqual(0, len(empties), "invalid format object")

    @timeout()
    async def test_add_default_size_handling(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id=disk_id)
            [gap] = sda["partitions"]

            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [sda] = match(resp["disks"], id=disk_id)
            [sda1, sda2] = sda["partitions"]
            self.assertEqual(gap["size"], sda1["size"] + sda2["size"])

    @timeout()
    async def test_v2_add_boot_BIOS(self):
        cfg = "examples/machines/simple.json"
        async with start_server(cfg, "bios") as inst:
            disk_id = "disk-sda"
            resp = await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)
            [sda] = match(resp["disks"], id=disk_id)
            [sda1] = match(sda["partitions"], number=1)
            self.assertTrue(sda["boot_device"])
            self.assertTrue(sda1["boot"])

    @timeout()
    async def test_v2_blank_is_not_boot(self):
        cfg = "examples/machines/simple.json"
        async with start_server(cfg, "bios") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id=disk_id)
            self.assertFalse(sda["boot_device"])

    @timeout()
    async def test_v2_multi_disk_multi_boot(self):
        cfg = "examples/machines/many-nics-and-disks.json"
        async with start_server(cfg) as inst:
            resp = await inst.get("/storage/v2")
            [d1] = match(resp["disks"], id="disk-vda")
            [d2] = match(resp["disks"], id="disk-vdb")
            await inst.post("/storage/v2/reformat_disk", {"disk_id": d1["id"]})
            await inst.post("/storage/v2/reformat_disk", {"disk_id": d2["id"]})
            await inst.post("/storage/v2/add_boot_partition", disk_id=d1["id"])
            await inst.post("/storage/v2/add_boot_partition", disk_id=d2["id"])
            # should allow both disks to get a boot partition with no Exception


class TestDelete(TestAPI):
    @timeout()
    async def test_v2_delete_without_reformat(self):
        cfg = "examples/machines/win10.json"
        extra = ["--storage-version", "1"]
        async with start_server(cfg, extra_args=extra) as inst:
            data = {"disk_id": "disk-sda", "partition": {"number": 1}}
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/delete_partition", data)

    @timeout()
    async def test_v2_delete_without_reformat_is_ok_with_sv2(self):
        cfg = "examples/machines/win10.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            data = {"disk_id": "disk-sda", "partition": {"number": 1}}
            await inst.post("/storage/v2/delete_partition", data)

    @timeout()
    async def test_v2_delete_with_reformat(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.post("/storage/v2/reformat_disk", {"disk_id": disk_id})
            [sda] = resp["disks"]
            [gap] = sda["partitions"]
            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "mount": "/",
                    "format": "ext4",
                },
            }
            await inst.post("/storage/v2/add_partition", data)
            data = {"disk_id": disk_id, "partition": {"number": 1}}
            await inst.post("/storage/v2/delete_partition", data)

    @timeout()
    async def test_delete_nonexistant(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            await inst.post("/storage/v2/reformat_disk", {"disk_id": disk_id})
            data = {"disk_id": disk_id, "partition": {"number": 1}}
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/delete_partition", data)


class TestEdit(TestAPI):
    @timeout()
    async def test_edit_no_change_size(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")

            [sda] = match(resp["disks"], id=disk_id)
            [sda3] = match(sda["partitions"], number=3)
            data = {
                "disk_id": disk_id,
                "partition": {"number": 3, "size": sda3["size"] - (1 << 30)},
            }
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/edit_partition", data)

    @timeout()
    async def test_edit_no_change_grub(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            data = {
                "disk_id": disk_id,
                "partition": {
                    "number": 3,
                    "boot": True,
                },
            }
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/edit_partition", data)

    @timeout()
    async def test_edit_no_change_pname(self):
        async with start_server("examples/machines/win11-along-ubuntu.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")

            [sda] = match(resp["disks"], id=disk_id)
            [sda2] = match(sda["partitions"], number=2)

            self.assertIsNotNone(sda2["name"])

            # This should be a no-op since "name" is not present.
            data = {
                "disk_id": disk_id,
                "partition": {
                    "number": 2,
                },
            }
            await inst.post("/storage/v2/edit_partition", data)

            # Now, it should refuse the update
            data["partition"]["name"] = "foo"
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/edit_partition", data)

    @timeout()
    async def test_edit_format(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            data = {
                "disk_id": disk_id,
                "partition": {
                    "number": 3,
                    "format": "btrfs",
                    "wipe": "superblock",
                },
            }
            resp = await inst.post("/storage/v2/edit_partition", data)

            [sda] = match(resp["disks"], id=disk_id)
            [sda3] = match(sda["partitions"], number=3)
            self.assertEqual("btrfs", sda3["format"])

    @timeout()
    async def test_edit_mount(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            data = {
                "disk_id": disk_id,
                "partition": {
                    "number": 3,
                    "mount": "/",
                },
            }
            resp = await inst.post("/storage/v2/edit_partition", data)

            [sda] = match(resp["disks"], id=disk_id)
            [sda3] = match(sda["partitions"], number=3)
            self.assertEqual("/", sda3["mount"])

    @timeout()
    async def test_edit_format_and_mount(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            data = {
                "disk_id": disk_id,
                "partition": {
                    "number": 3,
                    "format": "btrfs",
                    "mount": "/",
                    "wipe": "superblock",
                },
            }
            resp = await inst.post("/storage/v2/edit_partition", data)

            [sda] = match(resp["disks"], id=disk_id)
            [sda3] = match(sda["partitions"], number=3)
            self.assertEqual("btrfs", sda3["format"])
            self.assertEqual("/", sda3["mount"])

    @timeout()
    async def test_v2_reuse(self):
        async with start_server("examples/machines/win10.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")
            [orig_sda] = match(resp["disks"], id=disk_id)
            [_, orig_sda2, _, orig_sda4] = orig_sda["partitions"]

            data = {
                "disk_id": disk_id,
                "partition": {
                    "number": 3,
                    "format": "ext4",
                    "mount": "/",
                    "wipe": "superblock",
                },
            }
            resp = await inst.post("/storage/v2/edit_partition", data)
            [sda] = match(resp["disks"], id=disk_id)
            [sda1, sda2, sda3, sda4] = sda["partitions"]
            self.assertIsNone(sda1["wipe"])
            self.assertEqual("/boot/efi", sda1["mount"])
            self.assertEqual("vfat", sda1["format"])
            self.assertTrue(sda1["boot"])

            self.assertEqual(orig_sda2, sda2)

            self.assertIsNotNone(sda3["wipe"])
            self.assertEqual("/", sda3["mount"])
            self.assertEqual("ext4", sda3["format"])
            self.assertFalse(sda3["boot"])

            self.assertEqual(orig_sda4, sda4)


class TestReformat(TestAPI):
    @timeout()
    async def test_reformat_msdos(self):
        cfg = "examples/machines/simple.json"
        async with start_server(cfg) as inst:
            data = {
                "disk_id": "disk-sda",
                "ptable": "msdos",
            }
            resp = await inst.post("/storage/v2/reformat_disk", data)
            [sda] = resp["disks"]
            self.assertEqual("msdos", sda["ptable"])


class TestPartitionTableTypes(TestAPI):
    @timeout()
    async def test_ptable_gpt(self):
        async with start_server("examples/machines/win10.json") as inst:
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id="disk-sda")
            self.assertEqual("gpt", sda["ptable"])

    @timeout()
    async def test_ptable_msdos(self):
        cfg = "examples/machines/many-nics-and-disks.json"
        async with start_server(cfg) as inst:
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id="disk-sda")
            self.assertEqual("msdos", sda["ptable"])

    @timeout()
    async def test_ptable_none(self):
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id="disk-sda")
            self.assertEqual(None, sda["ptable"])


class TestTodos(TestAPI):  # server indicators of required client actions
    @timeout()
    async def test_todos_simple(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.post("/storage/v2/reformat_disk", {"disk_id": disk_id})
            self.assertTrue(resp["need_root"])
            self.assertTrue(resp["need_boot"])

            [sda] = resp["disks"]
            [gap] = sda["partitions"]
            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            self.assertFalse(resp["need_root"])
            self.assertFalse(resp["need_boot"])

    @timeout()
    async def test_todos_manual(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.post("/storage/v2/reformat_disk", {"disk_id": disk_id})
            self.assertTrue(resp["need_root"])
            self.assertTrue(resp["need_boot"])

            resp = await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)
            self.assertTrue(resp["need_root"])
            self.assertFalse(resp["need_boot"])

            [sda] = resp["disks"]
            [gap] = match(sda["partitions"], _type="Gap")
            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            self.assertFalse(resp["need_root"])
            self.assertFalse(resp["need_boot"])

    @timeout()
    async def test_todos_guided(self):
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.post("/storage/v2/reformat_disk", {"disk_id": "disk-sda"})
            self.assertTrue(resp["need_root"])
            self.assertTrue(resp["need_boot"])

            resp = await inst.get("/storage/v2/guided")
            [reformat, manual] = resp["targets"]
            data = {
                "target": reformat,
                "capability": reformat["allowed"][0],
            }
            await inst.post("/storage/v2/guided", data)
            resp = await inst.get("/storage/v2")
            self.assertFalse(resp["need_root"])
            self.assertFalse(resp["need_boot"])


class TestInfo(TestAPI):
    @timeout()
    async def test_path(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id=disk_id)
            self.assertEqual("/dev/sda", sda["path"])

    @timeout()
    async def test_model_and_vendor(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id=disk_id)
            self.assertEqual("QEMU HARDDISK", sda["model"])
            self.assertEqual("ATA", sda["vendor"])

    @timeout()
    async def test_no_vendor(self):
        cfg = "examples/machines/many-nics-and-disks.json"
        async with start_server(cfg) as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id=disk_id)
            self.assertEqual("QEMU HARDDISK", sda["model"])
            self.assertEqual(None, sda["vendor"])


class TestFree(TestAPI):
    @timeout()
    async def test_free_only(self):
        async with start_server("examples/machines/simple.json") as inst:
            await inst.post("/meta/free_only", enable=True)
            components = await inst.get("/mirror/disable_components")
            components.sort()
            self.assertEqual(["multiverse", "restricted"], components)

    @timeout()
    async def test_not_free_only(self):
        async with start_server("examples/machines/simple.json") as inst:
            comps = ["universe", "multiverse"]
            await inst.post("/mirror/disable_components", comps)
            await inst.post("/meta/free_only", enable=False)
            components = await inst.get("/mirror/disable_components")
            self.assertEqual(["universe"], components)


class TestOSProbe(TestAPI):
    @timeout()
    async def test_win10(self):
        async with start_server("examples/machines/win10.json") as inst:
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id="disk-sda")
            [sda1] = match(sda["partitions"], number=1)
            expected = {
                "label": "Windows",
                "long": "Windows Boot Manager",
                "subpath": "/efi/Microsoft/Boot/bootmgfw.efi",
                "type": "efi",
                "version": None,
            }

            self.assertEqual(expected, sda1["os"])


class TestPartitionTableEditing(TestAPI):
    @timeout()
    async def test_use_free_space_after_existing(self):
        cfg = "examples/machines/ubuntu-and-free-space.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            # Disk has 3 existing partitions and free space.  Add one to end.
            # sda1 is an ESP, so that should get implicitly picked up.
            resp = await inst.get("/storage/v2")
            [sda] = resp["disks"]
            [e1, e2, e3, gap] = sda["partitions"]
            self.assertEqual("Gap", gap["$type"])

            data = {
                "disk_id": "disk-sda",
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [sda] = resp["disks"]
            [p1, p2, p3, p4] = sda["partitions"]
            e1.pop("annotations")
            e1.update(
                {
                    "mount": "/boot/efi",
                    "grub_device": True,
                    "effective_mount": "/boot/efi",
                }
            )
            self.assertDictSubset(e1, p1)
            self.assertEqual(e2, p2)
            self.assertEqual(e3, p3)
            e4 = {
                "$type": "Partition",
                "number": 4,
                "size": gap["size"],
                "offset": gap["offset"],
                "format": "ext4",
                "mount": "/",
            }
            self.assertDictSubset(e4, p4)

    @timeout()
    async def test_resize(self):
        cfg = self.machineConfig("examples/machines/ubuntu-and-free-space.json")
        with cfg.edit() as data:
            blockdev = data["storage"]["blockdev"]
            sizes = {k: int(v["attrs"]["size"]) for k, v in blockdev.items()}
            # expand sda3 to use the rest of the disk
            sda3_size = (
                sizes["/dev/sda"] - sizes["/dev/sda1"] - sizes["/dev/sda2"] - (2 << 20)
            )
            blockdev["/dev/sda3"]["attrs"]["size"] = str(sda3_size)

        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            # Disk has 3 existing partitions and no free space.
            resp = await inst.get("/storage/v2")
            [sda] = resp["disks"]
            [orig_p1, orig_p2, orig_p3] = sda["partitions"]

            p3 = orig_p3.copy()
            p3["size"] = 10 << 30
            data = {
                "disk_id": "disk-sda",
                "partition": p3,
            }
            resp = await inst.post("/storage/v2/edit_partition", data)
            [sda] = resp["disks"]
            [_, _, actual_p3, g1] = sda["partitions"]
            self.assertEqual(10 << 30, actual_p3["size"])
            self.assertEqual(True, actual_p3["resize"])
            self.assertIsNone(actual_p3["wipe"])
            end_size = orig_p3["size"] - (10 << 30)
            self.assertEqual(end_size, g1["size"])

            expected_p1 = orig_p1.copy()
            expected_p1.pop("annotations")
            expected_p1.update(
                {
                    "mount": "/boot/efi",
                    "grub_device": True,
                    "effective_mount": "/boot/efi",
                }
            )
            expected_p3 = actual_p3
            data = {
                "disk_id": "disk-sda",
                "gap": g1,
                "partition": {
                    "format": "ext4",
                    "mount": "/srv",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [sda] = resp["disks"]
            [actual_p1, actual_p2, actual_p3, actual_p4] = sda["partitions"]
            self.assertDictSubset(expected_p1, actual_p1)
            self.assertEqual(orig_p2, actual_p2)
            self.assertEqual(expected_p3, actual_p3)
            self.assertEqual(end_size, actual_p4["size"])
            self.assertEqual("Partition", actual_p4["$type"])

            v1resp = await inst.get("/storage")
            config = v1resp["config"]
            [sda3] = match(config, type="partition", number=3)
            [sda3_format] = match(config, type="format", volume=sda3["id"])
            self.assertTrue(sda3["preserve"])
            self.assertTrue(sda3["resize"])
            self.assertTrue(sda3_format["preserve"])

    @timeout()
    async def test_est_min_size(self):
        cfg = self.machineConfig("examples/machines/win10-along-ubuntu.json")
        with cfg.edit() as data:
            fs = data["storage"]["filesystem"]
            fs["/dev/sda1"]["ESTIMATED_MIN_SIZE"] = 0
            # data file has no sda2 in filesystem
            fs["/dev/sda3"]["ESTIMATED_MIN_SIZE"] = -1
            fs["/dev/sda4"]["ESTIMATED_MIN_SIZE"] = (1 << 20) + 1

        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get("/storage/v2")
            [sda] = resp["disks"]
            [p1, _, p3, p4, _] = sda["partitions"]
            self.assertEqual(1 << 20, p1["estimated_min_size"])
            self.assertEqual(-1, p3["estimated_min_size"])
            self.assertEqual(2 << 20, p4["estimated_min_size"])

    @timeout()
    async def test_v2_orig_config(self):
        cfg = "examples/machines/win10-along-ubuntu.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            start_resp = await inst.get("/storage/v2")
            resp = await inst.get("/storage/v2/guided")
            resize = match(resp["targets"], _type="GuidedStorageTargetResize")[0]
            resize["new_size"] = 30 << 30
            data = {
                "target": resize,
                "capability": resize["allowed"][0],
            }
            await inst.post("/storage/v2/guided", data)
            orig_config = await inst.get("/storage/v2/orig_config")
            end_resp = await inst.get("/storage/v2")
            self.assertEqual(start_resp, orig_config)
            self.assertNotEqual(start_resp, end_resp)


class TestGap(TestAPI):
    @timeout()
    async def test_blank_disk_is_one_big_gap(self):
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/storage/v2")
            [sda] = match(resp["disks"], id="disk-sda")
            gap = sda["partitions"][0]
            expected = (100 << 30) - (2 << 20)
            self.assertEqual(expected, gap["size"])
            self.assertEqual("YES", gap["usable"])

    @timeout()
    async def test_gap_at_end(self):
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/storage/v2")
            [sda] = resp["disks"]
            [gap] = match(sda["partitions"], _type="Gap")
            data = {
                "disk_id": "disk-sda",
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                    "size": 4 << 30,
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [sda] = resp["disks"]
            [boot] = match(sda["partitions"], mount="/boot/efi")
            [p1, p2, gap] = sda["partitions"]
            self.assertEqual("Gap", gap["$type"])
            expected = (100 << 30) - p1["size"] - p2["size"] - (2 << 20)
            self.assertEqual(expected, gap["size"])

    @timeout()
    async def SKIP_test_two_gaps(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.post("/storage/v2/add_boot_partition", disk_id=disk_id)
            json_print(resp)
            boot_size = resp["disks"][0]["partitions"][0]["size"]
            root_size = 4 << 30
            data = {
                "disk_id": disk_id,
                "partition": {
                    "format": "ext4",
                    "mount": "/",
                    "size": root_size,
                },
            }
            await inst.post("/storage/v2/add_partition", data)
            data = {"disk_id": disk_id, "partition": {"number": 1}}
            resp = await inst.post("/storage/v2/delete_partition", data)
            [sda] = match(resp["disks"], id=disk_id)
            self.assertEqual(3, len(sda["partitions"]))

            boot_gap = sda["partitions"][0]
            self.assertEqual(boot_size, boot_gap["size"])
            self.assertEqual("Gap", boot_gap["$type"])

            root = sda["partitions"][1]
            self.assertEqual(root_size, root["size"])
            self.assertEqual("Partition", root["$type"])

            end_gap = sda["partitions"][2]
            end_size = (10 << 30) - boot_size - root_size - (2 << 20)
            self.assertEqual(end_size, end_gap["size"])
            self.assertEqual("Gap", end_gap["$type"])


class TestRegression(TestAPI):
    @timeout()
    async def test_edit_not_trigger_boot_device(self):
        async with start_server("examples/machines/simple.json") as inst:
            disk_id = "disk-sda"
            resp = await inst.get("/storage/v2")
            [sda] = resp["disks"]
            [gap] = sda["partitions"]
            data = {
                "disk_id": disk_id,
                "gap": gap,
                "partition": {
                    "format": "ext4",
                    "mount": "/foo",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [sda] = resp["disks"]
            [part] = match(sda["partitions"], mount="/foo")
            part.update(
                {
                    "format": "ext3",
                    "mount": "/bar",
                    "wipe": "superblock",
                }
            )
            data["partition"] = part
            data.pop("gap")
            await inst.post("/storage/v2/edit_partition", data)
            # should not throw an exception complaining about boot

    @timeout()
    async def test_osprober_knames(self):
        cfg = "examples/machines/lp-1986676-missing-osprober.json"
        async with start_server(cfg) as inst:
            resp = await inst.get("/storage/v2")
            [nvme] = match(resp["disks"], id="disk-nvme0n1")
            [nvme_p2] = match(nvme["partitions"], path="/dev/nvme0n1p2")
            expected = {
                "long": "Ubuntu 22.04.1 LTS",
                "label": "Ubuntu",
                "type": "linux",
                "subpath": None,
                "version": "22.04.1",
            }
            self.assertEqual(expected, nvme_p2["os"])

    @timeout()
    async def test_edit_should_trigger_wipe_when_requested(self):
        # LP: #1983036 - a partition wipe was requested but didn't happen
        # The old way this worked was to use changes to the 'format' value to
        # decide if a wipe was happening or not, and now the client chooses so
        # explicitly.
        cfg = "examples/machines/win10-along-ubuntu.json"
        async with start_server(cfg) as inst:
            resp = await inst.get("/storage/v2")
            [d1] = resp["disks"]
            [p5] = match(d1["partitions"], number=5)
            p5.update(dict(mount="/home", wipe="superblock"))
            data = dict(disk_id=d1["id"], partition=p5)
            resp = await inst.post("/storage/v2/edit_partition", data)

            v1resp = await inst.get("/storage")
            [c_p5] = match(v1resp["config"], number=5)
            [c_p5fmt] = match(v1resp["config"], volume=c_p5["id"])
            self.assertEqual("superblock", c_p5["wipe"])
            self.assertFalse(c_p5fmt["preserve"])
            self.assertTrue(c_p5["preserve"])

            # then let's change our minds and not wipe it
            [d1] = resp["disks"]
            [p5] = match(d1["partitions"], number=5)
            p5["wipe"] = None
            data = dict(disk_id=d1["id"], partition=p5)
            resp = await inst.post("/storage/v2/edit_partition", data)

            v1resp = await inst.get("/storage")
            [c_p5] = match(v1resp["config"], number=5)
            [c_p5fmt] = match(v1resp["config"], volume=c_p5["id"])
            self.assertNotIn("wipe", c_p5)
            self.assertTrue(c_p5fmt["preserve"])
            self.assertTrue(c_p5["preserve"])

    @timeout()
    async def test_edit_should_leave_other_values_alone(self):
        cfg = "examples/machines/win10-along-ubuntu.json"
        async with start_server(cfg) as inst:

            async def check_preserve():
                v1resp = await inst.get("/storage")
                [c_p5] = match(v1resp["config"], number=5)
                [c_p5fmt] = match(v1resp["config"], volume=c_p5["id"])
                self.assertNotIn("wipe", c_p5)
                self.assertTrue(c_p5fmt["preserve"])
                self.assertTrue(c_p5["preserve"])

            resp = await inst.get("/storage/v2")
            d1 = resp["disks"][0]
            [p5] = match(resp["disks"][0]["partitions"], number=5)
            orig_p5 = p5.copy()
            self.assertEqual("ext4", p5["format"])
            self.assertIsNone(p5["mount"])

            data = {"disk_id": d1["id"], "partition": p5}
            resp = await inst.post("/storage/v2/edit_partition", data)
            [p5] = match(resp["disks"][0]["partitions"], number=5)
            self.assertEqual(orig_p5, p5)
            await check_preserve()

            p5.update({"mount": "/"})
            data = {"disk_id": d1["id"], "partition": p5}
            resp = await inst.post("/storage/v2/edit_partition", data)
            [p5] = match(resp["disks"][0]["partitions"], number=5)
            expected = orig_p5.copy()
            expected["mount"] = "/"
            expected["annotations"] = [
                "existing",
                "already formatted as ext4",
                "mounted at /",
            ]
            expected["effective_mount"] = "/"
            self.assertEqual(expected, p5)
            await check_preserve()

            data = {"disk_id": d1["id"], "partition": p5}
            resp = await inst.post("/storage/v2/edit_partition", data)
            [p5] = match(resp["disks"][0]["partitions"], number=5)
            self.assertEqual(expected, p5)
            await check_preserve()

    @timeout()
    async def test_no_change_edit(self):
        cfg = "examples/machines/simple.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get("/storage/v2")
            [d] = resp["disks"]
            [g] = d["partitions"]
            data = {
                "disk_id": "disk-sda",
                "gap": g,
                "partition": {
                    "size": 107372085248,
                    "format": "ext4",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [p] = resp["disks"][0]["partitions"]
            self.assertEqual("ext4", p["format"])

            orig_p = p.copy()

            data = {"disk_id": "disk-sda", "partition": p}
            resp = await inst.post("/storage/v2/edit_partition", data)
            [p] = resp["disks"][0]["partitions"]
            self.assertEqual(orig_p, p)

    @timeout()
    async def test_no_change_edit_swap(self):
        """LP: 2002413 - editing a swap partition would fail with
        > Exception: Filesystem(fstype='swap', ...) is already mounted
        Make sure editing the partition is ok now.
        """
        cfg = "examples/machines/simple.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get("/storage/v2")
            [d] = resp["disks"]
            [g] = d["partitions"]
            data = {
                "disk_id": "disk-sda",
                "gap": g,
                "partition": {
                    "size": 8589934592,  # 8 GiB
                    "format": "swap",
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [p, gap] = resp["disks"][0]["partitions"]
            self.assertEqual("swap", p["format"])

            orig_p = p.copy()

            data = {"disk_id": "disk-sda", "partition": p}
            resp = await inst.post("/storage/v2/edit_partition", data)
            [p, gap] = resp["disks"][0]["partitions"]
            self.assertEqual(orig_p, p)

    @timeout()
    async def test_can_create_unformatted_partition(self):
        """We want to offer the same list of fstypes for Subiquity and U-D-I,
        but the list is different today.  Verify that unformatted partitions
        may be created."""
        cfg = "examples/machines/simple.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get("/storage/v2")
            [d] = resp["disks"]
            [g] = d["partitions"]
            data = {
                "disk_id": "disk-sda",
                "gap": g,
                "partition": {
                    "size": -1,
                    "format": None,
                },
            }
            resp = await inst.post("/storage/v2/add_partition", data)
            [p] = resp["disks"][0]["partitions"]
            self.assertIsNone(p["format"])
            v1resp = await inst.get("/storage")
            self.assertEqual([], match(v1resp["config"], type="format"))

    @timeout()
    async def test_guided_v2_resize_logical_middle_partition(self):
        """LP: #2015521 - a logical partition that wasn't the physically last
        logical partition was resized to allow creation of more partitions, but
        the 1MiB space was not left between the newly created partition and the
        physically last partition."""
        cfg = "examples/machines/threebuntu-on-msdos.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get("/storage/v2/guided")
            [resize] = match(
                resp["targets"], partition_number=5, _type="GuidedStorageTargetResize"
            )
            data = {
                "target": resize,
                "capability": resize["allowed"][0],
            }
            resp = await inst.post("/storage/v2/guided", data)
            self.assertEqual(resize, resp["configured"]["target"])

            resp = await inst.get("/storage")
            parts = match(resp["config"], type="partition", flag="logical")
            logicals = []
            for part in parts:
                part["end"] = part["offset"] + part["size"]
                logicals.append(part)

            logicals.sort(key=lambda p: p["offset"])
            for i in range(len(logicals) - 1):
                cur, nxt = logicals[i : i + 2]
                self.assertLessEqual(
                    cur["end"] + (1 << 20),
                    nxt["offset"],
                    f"partition overlap {cur} {nxt}",
                )

    @timeout(multiplier=2)
    async def test_probert_result_during_partitioning(self):
        """LP: #2016901 - when a probert run finishes during manual
        partitioning, we used to load the probing data automatically ;
        essentially discarding any change made by the user so far. This test
        creates a new partition, simulates the end of a probert run, and then
        tries to edit the previously created partition.  The edit operation
        would fail in earlier versions because the new partition would have
        been discarded."""
        cfg = "examples/machines/simple.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            names = ["locale", "keyboard", "source", "network", "proxy", "mirror"]
            await inst.post("/meta/mark_configured", endpoint_names=names)
            resp = await inst.get("/storage/v2", wait=True)
            [d] = resp["disks"]
            [g] = d["partitions"]
            data = {
                "disk_id": "disk-sda",
                "gap": g,
                "partition": {
                    "size": -1,
                    "mount": "/",
                    "format": "ext4",
                },
            }
            add_resp = await inst.post("/storage/v2/add_partition", data)
            [sda] = add_resp["disks"]
            [root] = match(sda["partitions"], mount="/")

            # Now let's make sure we get the results from a probert run to kick
            # in.
            await inst.post("/storage/dry_run_wait_probe")
            data = {
                "disk_id": "disk-sda",
                "partition": {
                    "number": root["number"],
                },
            }
            # We should be able to modify the created partition.
            await inst.post("/storage/v2/edit_partition", data)


class TestCancel(TestAPI):
    @timeout()
    async def test_cancel_drivers(self):
        with patch.dict(os.environ, {"SUBIQUITY_DEBUG": "has-drivers"}):
            async with start_server("examples/machines/simple.json") as inst:
                await inst.post("/source", source_id="placeholder", search_drivers=True)
                # /drivers?wait=true is expected to block until APT is
                # configured.
                # Let's make sure we cancel it.
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(inst.get("/drivers", wait=True), 0.1)
                names = [
                    "locale",
                    "keyboard",
                    "source",
                    "network",
                    "proxy",
                    "mirror",
                    "storage",
                ]
                await inst.post("/meta/mark_configured", endpoint_names=names)
                await inst.get("/meta/status", cur="WAITING")
                await inst.post("/meta/confirm", tty="/dev/tty1")
                await inst.get("/meta/status", cur="NEEDS_CONFIRMATION")

                # should not raise ServerDisconnectedError
                resp = await inst.get("/drivers", wait=True)
                self.assertEqual(["nvidia-driver-470-server"], resp["drivers"])


class TestDrivers(TestAPI):
    async def _test_source(self, source_id, expected_driver):
        with patch.dict(os.environ, {"SUBIQUITY_DEBUG": "has-drivers"}):
            cfg = "examples/machines/simple.json"
            extra = ["--source-catalog", "examples/sources/mixed.yaml"]
            async with start_server(cfg, extra_args=extra) as inst:
                await inst.post("/source", source_id=source_id, search_drivers=True)

                names = [
                    "locale",
                    "keyboard",
                    "source",
                    "network",
                    "proxy",
                    "mirror",
                    "storage",
                ]
                await inst.post("/meta/mark_configured", endpoint_names=names)
                await inst.get("/meta/status", cur="WAITING")
                await inst.post("/meta/confirm", tty="/dev/tty1")
                await inst.get("/meta/status", cur="NEEDS_CONFIRMATION")

                resp = await inst.get("/drivers", wait=True)
                self.assertEqual([expected_driver], resp["drivers"])

    @timeout()
    async def test_server_source(self):
        await self._test_source("ubuntu-server-minimal", "nvidia-driver-470-server")

    @timeout()
    async def test_desktop_source(self):
        await self._test_source("ubuntu-desktop", "nvidia-driver-510")

    @timeout()
    async def test_listing_ongoing(self):
        """Ensure that the list of drivers returned by /drivers is null while
        the list has not been retrieved."""
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/drivers", wait=False)
            self.assertIsNone(resp["drivers"])

            # POSTing to /source will restart the retrieval operation.
            await inst.post("/source", source_id="ubuntu-server", search_drivers=True)

            resp = await inst.get("/drivers", wait=False)
            self.assertIsNone(resp["drivers"])


class TestOEM(TestAPI):
    @timeout()
    async def test_listing_ongoing(self):
        """Ensure that the list of OEM metapackages returned by /oem is
        null while the list has not been retrieved."""
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/oem", wait=False)
            self.assertIsNone(resp["metapackages"])

    @timeout()
    async def test_listing_empty(self):
        expected_pkgs = []
        with patch.dict(os.environ, {"SUBIQUITY_DEBUG": "no-drivers"}):
            async with start_server("examples/machines/simple.json") as inst:
                await inst.post("/source", source_id="ubuntu-server")
                names = [
                    "locale",
                    "keyboard",
                    "source",
                    "network",
                    "proxy",
                    "mirror",
                    "storage",
                ]
                await inst.post("/meta/mark_configured", endpoint_names=names)
                await inst.get("/meta/status", cur="WAITING")
                await inst.post("/meta/confirm", tty="/dev/tty1")
                await inst.get("/meta/status", cur="NEEDS_CONFIRMATION")

                resp = await inst.get("/oem", wait=True)
                self.assertEqual(expected_pkgs, resp["metapackages"])

    async def _test_listing_certified(self, source_id: str, expected: List[str]):
        with patch.dict(os.environ, {"SUBIQUITY_DEBUG": "has-drivers"}):
            args = ["--source-catalog", "examples/sources/mixed.yaml"]
            config = "examples/machines/simple.json"
            async with start_server(config, extra_args=args) as inst:
                await inst.post("/source", source_id=source_id)
                names = [
                    "locale",
                    "keyboard",
                    "source",
                    "network",
                    "proxy",
                    "mirror",
                    "storage",
                ]
                await inst.post("/meta/mark_configured", endpoint_names=names)
                await inst.get("/meta/status", cur="WAITING")
                await inst.post("/meta/confirm", tty="/dev/tty1")
                await inst.get("/meta/status", cur="NEEDS_CONFIRMATION")

                resp = await inst.get("/oem", wait=True)
                self.assertEqual(expected, resp["metapackages"])

    @timeout()
    async def test_listing_certified_ubuntu_server(self):
        # Listing of OEM meta-packages is intentionally disabled on
        # ubuntu-server.
        await self._test_listing_certified(source_id="ubuntu-server", expected=[])

    @timeout()
    async def test_listing_certified_ubuntu_desktop(self):
        await self._test_listing_certified(
            source_id="ubuntu-desktop", expected=["oem-somerville-tentacool-meta"]
        )

    @timeout()
    async def test_confirmation_before_storage_configured(self):
        # On ubuntu-desktop, the confirmation event sometimes comes before the
        # storage configured event. This was known to cause OEM to fail with
        # the following error:
        #   File "server/controllers/oem.py", in load_metapackages_list
        #     if fs_controller.is_core_boot_classic():
        #   File "server/controllers/filesystem.py", in is_core_boot_classic
        #     return self._info.is_core_boot_classic()
        # AttributeError: 'NoneType' object has no attribute
        # 'is_core_boot_classic'
        with patch.dict(os.environ, {"SUBIQUITY_DEBUG": "has-drivers"}):
            config = "examples/machines/simple.json"
            args = ["--source-catalog", "examples/sources/mixed.yaml"]
            async with start_server(config, extra_args=args) as inst:
                await inst.post("/source", source_id="ubuntu-desktop")
                names = [
                    "locale",
                    "keyboard",
                    "source",
                    "network",
                    "proxy",
                    "mirror",
                    "storage",
                ]
                await inst.post("/meta/confirm", tty="/dev/tty1")
                await inst.post("/meta/mark_configured", endpoint_names=names)

                resp = await inst.get("/oem", wait=True)
                self.assertEqual(
                    ["oem-somerville-tentacool-meta"], resp["metapackages"]
                )


class TestSource(TestAPI):
    @timeout()
    async def test_optional_search_drivers(self):
        async with start_server("examples/machines/simple.json") as inst:
            await inst.post("/source", source_id="ubuntu-server")
            resp = await inst.get("/source")
            self.assertFalse(resp["search_drivers"])

            await inst.post("/source", source_id="ubuntu-server", search_drivers=True)
            resp = await inst.get("/source")
            self.assertTrue(resp["search_drivers"])

            await inst.post("/source", source_id="ubuntu-server", search_drivers=False)
            resp = await inst.get("/source")
            self.assertFalse(resp["search_drivers"])


class TestIdentityValidation(TestAPI):
    @timeout()
    async def test_username_validation(self):
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/identity/validate_username", username="plugdev")
            self.assertEqual(resp, "SYSTEM_RESERVED")

            resp = await inst.get("/identity/validate_username", username="root")
            self.assertEqual(resp, "ALREADY_IN_USE")

            resp = await inst.get("/identity/validate_username", username="r" * 33)
            self.assertEqual(resp, "TOO_LONG")

            resp = await inst.get("/identity/validate_username", username="01root")
            self.assertEqual(resp, "INVALID_CHARS")

            resp = await inst.get("/identity/validate_username", username="o#$%^&")
            self.assertEqual(resp, "INVALID_CHARS")


class TestManyPrimaries(TestAPI):
    @timeout()
    async def test_create_primaries(self):
        cfg = "examples/machines/simple.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            resp = await inst.get("/storage/v2")
            d1 = resp["disks"][0]

            data = {"disk_id": d1["id"], "ptable": "msdos"}
            resp = await inst.post("/storage/v2/reformat_disk", data)
            [gap] = match(resp["disks"][0]["partitions"], _type="Gap")

            for _ in range(4):
                self.assertEqual("YES", gap["usable"])
                data = {
                    "disk_id": d1["id"],
                    "gap": gap,
                    "partition": {
                        "size": 1 << 30,
                        "format": "ext4",
                    },
                }
                resp = await inst.post("/storage/v2/add_partition", data)
                [gap] = match(resp["disks"][0]["partitions"], _type="Gap")

            self.assertEqual("TOO_MANY_PRIMARY_PARTS", gap["usable"])

            data = {
                "disk_id": d1["id"],
                "gap": gap,
                "partition": {
                    "size": 1 << 30,
                    "format": "ext4",
                },
            }
            with self.assertRaises(ClientResponseError):
                await inst.post("/storage/v2/add_partition", data)


class TestKeyboard(TestAPI):
    @timeout()
    async def test_input_source(self):
        async with start_server("examples/machines/simple.json") as inst:
            data = {"layout": "fr", "variant": "latin9"}
            await inst.post("/keyboard/input_source", data, user="foo")


class TestUbuntuProContractSelection(TestAPI):
    @timeout()
    async def test_upcs_flow(self):
        async with start_server("examples/machines/simple.json") as inst:
            # Wait should fail if no initiate first.
            with self.assertRaises(Exception):
                await inst.get("/ubuntu_pro/contract_selection/wait")

            # Cancel should fail if no initiate first.
            with self.assertRaises(Exception):
                await inst.post("/ubuntu_pro/contract_selection/cancel")

            await inst.post("/ubuntu_pro/contract_selection/initiate")
            # Double initiate should fail
            with self.assertRaises(Exception):
                await inst.post("/ubuntu_pro/contract_selection/initiate")

            # This call should block for long enough.
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    inst.get("/ubuntu_pro/contract_selection/wait"), timeout=0.5
                )

            await inst.post("/ubuntu_pro/contract_selection/cancel")
            with self.assertRaises(Exception):
                await inst.get("/ubuntu_pro/contract_selection/wait")


class TestAutoinstallServer(TestAPI):
    @timeout(2)
    async def test_make_view_requests(self):
        cfg = "examples/machines/simple.json"
        extra = [
            "--autoinstall",
            "examples/autoinstall/short.yaml",
            "--source-catalog",
            "examples/sources/install.yaml",
        ]
        async with start_server(cfg, extra_args=extra, set_first_source=False) as inst:
            view_request_unspecified, resp = await inst.get(
                "/locale", full_response=True
            )
            self.assertEqual("en_US.UTF-8", view_request_unspecified)
            self.assertEqual("ok", resp.headers["x-status"])

            view_request_no, resp = await inst.get(
                "/locale", headers={"x-make-view-request": "no"}, full_response=True
            )
            self.assertEqual("en_US.UTF-8", view_request_no)
            self.assertEqual("ok", resp.headers["x-status"])

            view_request_yes, resp = await inst.get(
                "/locale", headers={"x-make-view-request": "yes"}, full_response=True
            )
            self.assertIsNone(view_request_yes)
            self.assertEqual("skip", resp.headers["x-status"])

    @timeout()
    async def test_interactive(self):
        cfg = "examples/machines/simple.json"
        with tempfile.NamedTemporaryFile(mode="w") as tf:
            tf.write(
                """
                version: 1
                interactive-sections: ['*']
            """
            )
            tf.flush()
            extra = ["--autoinstall", tf.name]
            async with start_server(cfg, extra_args=extra) as inst:
                resp = await inst.get("/meta/interactive_sections")
                expected = set(
                    [
                        "locale",
                        "refresh-installer",
                        "keyboard",
                        "source",
                        "network",
                        "ubuntu-pro",
                        "proxy",
                        "apt",
                        "storage",
                        "identity",
                        "ssh",
                        "snaps",
                        "codecs",
                        "drivers",
                        "timezone",
                        "updates",
                        "shutdown",
                    ]
                )
                self.assertTrue(expected.issubset(resp))

    @timeout(multiplier=2)
    async def test_autoinstall_validation_error(self):
        cfg = "examples/machines/simple.json"
        extra = [
            "--autoinstall",
            "test_data/autoinstall/invalid-early.yaml",
        ]
        # bare server factory for early fail
        async with start_server_factory(
            Server, cfg, extra_args=extra, allow_error=True
        ) as inst:
            resp = await inst.get("/meta/status")

            error = resp["nonreportable_error"]
            self.assertIsNone(resp["error"])

            self.assertIsNotNone(error)
            self.assertIn("cause", error)
            self.assertIn("message", error)
            self.assertIn("details", error)
            self.assertEqual(error["cause"], "AutoinstallValidationError")

    # This test isn't perfect, because in the future we should
    # really throw an AutoinstallError when a user provided
    # command fails, but this is the simplest way to test
    # the non-reportable errors are still reported correctly.
    # This has the added bonus of failing in the future when
    # we want to implement this behavior in the command
    # controllers
    @timeout(multiplier=2)
    async def test_autoinstall_not_autoinstall_error(self):
        cfg = "examples/machines/simple.json"
        extra = [
            "--autoinstall",
            "test_data/autoinstall/bad-early-command.yaml",
        ]
        # bare server factory for early fail
        async with start_server_factory(
            Server, cfg, extra_args=extra, allow_error=True
        ) as inst:
            resp = await inst.get("/meta/status")

            error = resp["error"]
            self.assertIsNone(resp["nonreportable_error"])

            self.assertIsNotNone(error)
            self.assertNotEqual(error, None)
            self.assertEqual(error["kind"], "UNKNOWN")


class TestActiveDirectory(TestAPI):
    @timeout()
    async def test_ad(self):
        # Few tests to assert that the controller is properly wired.
        # Exhaustive validation test cases are in the unit tests.
        cfg = "examples/machines/simple.json"
        async with start_server(cfg) as instance:
            endpoint = "/active_directory"
            ad_dict = await instance.get(endpoint)
            # Starts with the detected domain.
            self.assertEqual("ubuntu.com", ad_dict["domain_name"])

            # Post works by "returning None"
            ad_dict = {
                "admin_name": "Ubuntu",
                "domain_name": "ubuntu.com",
                "password": "u",
            }
            result = await instance.post(endpoint, ad_dict)
            self.assertIsNone(result)

            # Rejects empty password.
            result = await instance.post(endpoint + "/check_password", data="")
            self.assertEqual("EMPTY", result)

            # Rejects invalid domain controller names.
            result = await instance.post(
                endpoint + "/check_domain_name", data="..ubuntu.com"
            )

            self.assertIn("MULTIPLE_DOTS", result)

            # Rejects invalid usernames.
            result = await instance.post(
                endpoint + "/check_admin_name", data="ubuntu;pro"
            )
            self.assertEqual("INVALID_CHARS", result)

            # Notice that lowercase is not required.
            result = await instance.post(endpoint + "/check_admin_name", data="$Ubuntu")
            self.assertEqual("OK", result)

            # Leverages the stub ping strategy
            result = await instance.post(
                endpoint + "/ping_domain_controller", data="rockbuntu.com"
            )
            self.assertEqual("REALM_NOT_FOUND", result)

            # Attempts to join with the info supplied above.
            ad_dict = {
                "admin_name": "Ubuntu",
                "domain_name": "jubuntu.com",
                "password": "u",
            }
            result = await instance.post(endpoint, ad_dict)
            self.assertIsNone(result)
            join_result_ep = endpoint + "/join_result"
            # Without wait this shouldn't block but the result is unknown until
            # the install controller runs.
            join_result = await instance.get(join_result_ep, wait=False)
            self.assertEqual("UNKNOWN", join_result)
            # And without the installer controller running, a blocking call
            # should timeout since joining never happens.
            with self.assertRaises(asyncio.exceptions.TimeoutError):
                join_result = instance.get(join_result_ep, wait=True)
                await asyncio.wait_for(join_result, timeout=1.5)

    # Helper method
    @staticmethod
    async def target_packages() -> List[str]:
        """Returns the list of packages the AD Model wants to install in the
        target system."""
        from subiquity.models.ad import AdModel

        model = AdModel()
        model.do_join = True
        return await model.target_packages()

    async def packages_lookup(self, log_dir: str) -> Dict[str, bool]:
        """Returns a dictionary mapping the additional packages expected
        to be installed in the target system and whether they were
        referred to or not in the server log."""
        expected_packages = await self.target_packages()
        packages_lookup = {p.name: False for p in expected_packages}
        log_path = os.path.join(log_dir, "subiquity-server-debug.log")
        find_start = "finish: subiquity/Install/install/postinstall/install_{}:"
        log_status = " SUCCESS: installing {}"

        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines:
                for pack in packages_lookup:
                    find_line = find_start.format(pack) + log_status.format(pack)
                    pack_found = re.search(find_line, line) is not None
                    if pack_found:
                        packages_lookup[pack] = True

        return packages_lookup

    @timeout()
    async def test_ad_autoinstall(self):
        cfg = "examples/machines/simple.json"
        extra = [
            "--autoinstall",
            "examples/autoinstall/ad.yaml",
            "--source-catalog",
            "examples/sources/mixed.yaml",
            "--kernel-cmdline",
            "autoinstall",
        ]
        try:
            async with start_server(
                cfg, extra_args=extra, set_first_source=False
            ) as inst:
                endpoint = "/active_directory"
                logdir = inst.output_base()
                self.assertIsNotNone(logdir)
                await inst.post("/meta/client_variant", variant="desktop")
                ad_info = await inst.get(endpoint)
                self.assertIsNotNone(ad_info["admin_name"])
                self.assertIsNotNone(ad_info["domain_name"])
                self.assertEqual("", ad_info["password"])
                ad_info["password"] = "passw0rd"

                # This should be enough to configure AD controller and cause it
                # to install packages into and try joining the target system.
                await inst.post(endpoint, ad_info)
                # Now this shouldn't hang or timeout
                join_result = await inst.get(endpoint + "/join_result", wait=True)
                self.assertEqual("OK", join_result)
                packages = await self.packages_lookup(logdir)
                for k, v in packages.items():
                    print(f"Checking package {k}")
                    self.assertTrue(v, f"package {k} not found in the target")

        # By the time we reach here the server already exited and the context
        # manager will fail to POST /shutdown.
        except aiohttp.client_exceptions.ClientOSError:
            pass


class TestMountDetection(TestAPI):
    @timeout()
    async def test_mount_detection(self):
        # Test that the partition the installer is running from is
        # correctly identified as mounted.
        cfg = "examples/machines/booted-from-rp.json"
        async with start_server(cfg) as instance:
            result = await instance.get("/storage/v2")
            [disk1] = result["disks"]
            self.assertTrue(disk1["has_in_use_partition"])
            disk1p2 = disk1["partitions"][1]
            self.assertTrue(disk1p2["is_in_use"])


class TestFilesystemUserErrors(TestAPI):
    @timeout()
    async def test_add_boot_partition__with_error_report(self):
        cfg = "examples/machines/simple.json"
        extra = ["--storage-version", "2"]
        async with start_server(cfg, extra_args=extra) as inst:
            await inst.post("/storage/v2/add_boot_partition", disk_id="disk-sda")
            try:
                await inst.post("/storage/v2/add_boot_partition", disk_id="disk-sda")
            except ClientResponseError as cre:
                self.assertEqual(500, cre.status)
                self.assertIn("x-error-report", cre.headers)
                self.assertEqual(
                    "device already has bootloader partition",
                    json.loads(cre.headers["x-error-msg"]),
                )

    @timeout()
    async def test_add_boot_partition__no_error_report(self):
        cfg = "examples/machines/simple.json"
        extra = ["--storage-version", "2", "--no-report-storage-user-error"]
        async with start_server(cfg, extra_args=extra) as inst:
            await inst.post("/storage/v2/add_boot_partition", disk_id="disk-sda")
            try:
                await inst.post("/storage/v2/add_boot_partition", disk_id="disk-sda")
            except ClientResponseError as cre:
                self.assertEqual(422, cre.status)
                self.assertNotIn("x-error-report", cre.headers)
                self.assertEqual(
                    "device already has bootloader partition",
                    json.loads(cre.headers["x-error-msg"]),
                )


class TestNetwork(TestAPI):
    @timeout()
    async def test_disable_dead_NICS_on_view(self):
        """Test that NICs with no global IP are disabled on first GET."""
        # Due to LP: #2063331 we want to make sure that NICs without a
        # global IP address by the time we get to the networking screen
        # are automatically disabled.

        # First NIC "ens3" is connected, second NIC "ens4" is not
        cfg = "examples/machines/two-nics-one-up-one-down.json"
        async with start_server(cfg) as inst:
            # Make sure ens4 is disabled on first view
            resp = await inst.get("/network")
            devs = dict((dev["name"], dev) for dev in resp["devices"])
            self.assertEqual(devs["ens3"]["disabled_reason"], None)
            self.assertEqual(
                devs["ens4"]["disabled_reason"], "autoconfiguration failed"
            )

            conf = Path(inst.output_base()) / "etc/netplan/00-installer-config.yaml"

            await asyncio.sleep(1)  # wait for _write_config step to update the config

            with open(conf) as f:
                conf_data = yaml.safe_load(f)

            ethernets = conf_data["network"]["ethernets"]
            self.assertIn("ens3", ethernets)
            self.assertNotIn("ens4", ethernets)

            # Don't disable on successive GETs (e.g. manually changed back to
            # dhcp but still hasn't come online).
            await inst.post("/network/enable_dhcp", dev_name="ens4", ip_version=4)
            resp = await inst.get("/network")
            devs = dict((dev["name"], dev) for dev in resp["devices"])
            # Bug: disabled_reason doesn't get unset so check dhcp4 status
            self.assertTrue(devs["ens4"]["dhcp4"]["enabled"])

            await asyncio.sleep(1)  # another wait for _write_config

            with open(conf) as f:
                conf_data = yaml.safe_load(f)

            ethernets = conf_data["network"]["ethernets"]
            self.assertIn("ens4", ethernets)


class TestServerVariantSupport(TestAPI):
    @parameterized.expand(
        (
            ("server", True),
            ("desktop", True),
            ("core", True),
            ("foo-bar", False),
        )
    )
    @timeout()
    async def test_supported_variants(self, variant, is_supported):
        async with start_server("examples/machines/simple.json") as inst:
            if is_supported:
                await inst.post("/meta/client_variant", variant=variant)
            else:
                with self.assertRaises(ClientResponseError) as ctx:
                    await inst.post("/meta/client_variant", variant=variant)
                cre = ctx.exception
                self.assertEqual(500, cre.status)
                self.assertIn("x-error-report", cre.headers)
                self.assertEqual(
                    "unrecognized client variant foo-bar",
                    json.loads(cre.headers["x-error-msg"]),
                )

    @timeout()
    async def test_post_source_update_server_variant(self):
        """Test POSTing to source will correctly update Server variant."""

        extra_args = ["--source-catalog", "examples/sources/mixed.yaml"]
        async with start_server(
            "examples/machines/simple.json",
            extra_args=extra_args,
        ) as inst:
            resp = await inst.get("/meta/client_variant")
            self.assertEqual(resp, "server")

            await inst.post("/source", source_id="ubuntu-desktop")

            resp = await inst.get("/meta/client_variant")
            self.assertEqual(resp, "desktop")


class TestLabels(TestAPI):
    @parameterized.expand(
        (
            (
                "DIRECT",
                None,
                (
                    {
                        "number": 1,
                        "boot": True,
                        "grub_device": True,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "fat32",
                        "mount": "/boot/efi",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 2,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "ext4",
                        "mount": "/",
                        "effectively_encrypted": False,
                    },
                ),
            ),
            (
                "LVM",
                None,
                (
                    {
                        "number": 1,
                        "boot": True,
                        "grub_device": True,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "fat32",
                        "mount": "/boot/efi",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 2,
                        "boot": False,  # really
                        "grub_device": None,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "ext4",
                        "mount": "/boot",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 3,
                        "preserve": False,
                        "wipe": "superblock",
                        "effective_format": "ext4",
                        "effective_mount": "/",
                        "effectively_encrypted": False,
                    },
                ),
            ),
            (
                "LVM_LUKS",
                "passw0rd",
                (
                    {
                        "number": 1,
                        "boot": True,
                        "grub_device": True,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "fat32",
                        "mount": "/boot/efi",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 2,
                        "boot": False,
                        "grub_device": None,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "ext4",
                        "mount": "/boot",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 3,
                        "preserve": False,
                        "wipe": "superblock",
                        "effective_format": "ext4",
                        "effective_mount": "/",
                        "effectively_encrypted": True,
                    },
                ),
            ),
            (
                "ZFS",
                None,
                (
                    {
                        "number": 1,
                        "boot": True,
                        "grub_device": True,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "fat32",
                        "mount": "/boot/efi",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 2,
                        "boot": False,
                        "grub_device": None,
                        "preserve": False,
                        "wipe": None,
                        "effective_format": "zfs",
                        "effective_mount": "/boot",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 3,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "swap",
                        "mount": "",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 4,
                        "preserve": False,
                        "wipe": None,
                        "effective_format": "zfs",
                        "effective_mount": "/",
                        "effectively_encrypted": False,
                    },
                ),
            ),
            (
                "ZFS_LUKS_KEYSTORE",
                "passw0rd",
                (
                    {
                        "number": 1,
                        "boot": True,
                        "grub_device": True,
                        "preserve": False,
                        "wipe": "superblock",
                        "format": "fat32",
                        "mount": "/boot/efi",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 2,
                        "boot": False,
                        "grub_device": None,
                        "preserve": False,
                        "wipe": None,
                        "effective_format": "zfs",
                        "effective_mount": "/boot",
                        "effectively_encrypted": False,
                    },
                    {
                        "number": 3,
                        "preserve": False,
                        "wipe": None,
                        "effective_format": "swap",
                        "effective_mount": "",
                        "effectively_encrypted": True,
                    },
                    {
                        "number": 4,
                        "preserve": False,
                        "wipe": None,
                        "effective_format": "zfs",
                        "effective_mount": "/",
                        "effectively_encrypted": True,
                    },
                ),
            ),
        )
    )
    @timeout()
    async def test_labels(self, capability, password, partitions):
        async with start_server("examples/machines/simple.json") as inst:
            resp = await inst.get("/storage/v2/guided?wait=true")
            [reformat, manual] = resp["targets"]

            await inst.post(
                "/storage/v2/guided",
                {
                    "target": reformat,
                    "capability": capability,
                    "password": password,
                },
            )
            resp = await inst.get("/storage/v2")
            [d] = resp["disks"]
            for expected, actual in itertools.zip_longest(partitions, d["partitions"]):
                self.assertDictSubset(expected, actual, f"partnum {actual['number']}")
