#!/usr/bin/env python3

""" Makes sure system_setup is only listening to the loopback interface. """

import argparse
import asyncio
from dataclasses import dataclass
import json
import logging
import subprocess
from typing import List


class FailedTestCase(Exception):
    pass


@dataclass
class Test:
    interface: str
    url: str
    family: int
    expect_success: bool


def read_network_interfaces() -> List[str]:
    """ Return a list of network interfaces that are up. """
    cmd = ["ip", "--json", "link", "show", "up"]
    output = subprocess.check_output(cmd, text=True)
    data = json.loads(output)
    return [iface["ifname"] for iface in data if iface.get("ifname")]


async def test_connect(cmd: List[str]) -> bool:
    """ Return true if the command specified exits with status 0 within 10
    seconds. """
    proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        await asyncio.wait_for(proc.wait(), 10)
    except asyncio.TimeoutError:
        return False
    return proc.returncode == 0


async def run_test(test: Test) -> None:
    """ Execute a test and raise a FailedTestCase if it fails. """
    logging.debug("Test: %s", test)
    cmd = ["curl", f"-{test.family}", test.url, "--interface", test.interface]
    status = await test_connect(cmd)
    if status != test.expect_success:
        logging.error("cmd %s exited %s but we expected %s", cmd,
                      "successfully" if status else "unsuccessfully",
                      "success" if test.expect_success else "failure")
        raise FailedTestCase


async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--port", type=int, default=50321)

    args = vars(parser.parse_args())

    if args["debug"]:
        logging.getLogger().level = logging.DEBUG

    interfaces = read_network_interfaces()
    logging.debug("interfaces = %s", interfaces)

    coroutines = []

    url = f"http://localhost:{args['port']}/meta/status"
    for iface in interfaces:
        for family in 4, 6:
            if family == 4 and iface == "lo":
                # Loopback should succeed on IPv4
                expect_success=True
            else:
                # Everything else should not
                expect_success = False
            coroutines.append(run_test(Test(
                interface=iface, url=url, family=family,
                expect_success=expect_success)))

    results = await asyncio.gather(*coroutines, return_exceptions=True)
    if any(map(lambda x: isinstance(x, FailedTestCase), results)):
        raise FailedTestCase


if __name__ == "__main__":
    asyncio.run(main())
