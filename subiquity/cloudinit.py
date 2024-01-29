"""Shared cloudinit utility functions"""

import asyncio
import json
import logging
import re
from typing import Optional

from subiquitycore.utils import arun_command, run_command

log = logging.getLogger("subiquity.cloudinit")


def get_host_combined_cloud_config() -> dict:
    """Return the host system /run/cloud-init/combined-cloud-config.json"""
    try:
        with open("/run/cloud-init/combined-cloud-config.json") as fp:
            config = json.load(fp)
            log.debug(
                "Loaded cloud config from /run/cloud-init/combined-cloud-config.json"
            )
            return config
    except FileNotFoundError:
        log.debug(
            "Failed to load combined-cloud-config, file not found. "
            "This is expected for cloud-init <= v23.2.1."
        )
        return {}
    except (IOError, OSError, AttributeError, json.decoder.JSONDecodeError) as ex:
        log.debug("Failed to load combined-cloud-config: %s", ex)
        return {}


def cloud_init_version() -> str:
    # looks like 24.1~3gb729a4c4-0ubuntu1
    cmd = ["dpkg-query", "-W", "-f=${Version}", "cloud-init"]
    sp = run_command(cmd, check=False)
    version = re.split("[-~]", sp.stdout)[0]
    log.debug(f"cloud-init version: {version}")
    return version


def supports_format_json() -> bool:
    return cloud_init_version() >= "22.4"


def supports_recoverable_errors() -> bool:
    return cloud_init_version() >= "23.4"


def read_json_extended_status(stream):
    try:
        status = json.loads(stream)
    except json.JSONDecodeError:
        return None

    return status.get("extended_status", status.get("status", None))


def read_legacy_status(stream):
    for line in stream.splitlines():
        if line.startswith("status:"):
            try:
                return line.split()[1]
            except IndexError:
                pass
    return None


async def cloud_init_status_wait() -> (bool, Optional[str]):
    """Wait for cloud-init completion, and return if timeout ocurred and best
    available status information.
    :return: tuple of (ok, status string or None)
    """
    cmd = ["cloud-init", "status", "--wait"]
    if format_json := supports_format_json():
        cmd += ["--format=json"]
    status_coro = arun_command(cmd)
    try:
        sp = await asyncio.wait_for(status_coro, 600)
    except asyncio.TimeoutError:
        return (False, "timeout")

    if format_json:
        status = read_json_extended_status(sp.stdout)
    else:
        status = read_legacy_status(sp.stdout)
    return (True, status)
