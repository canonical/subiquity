"""Shared cloudinit utility functions"""

import asyncio
import json
import logging
import re
import secrets
import tempfile
from collections.abc import Awaitable, Sequence
from pathlib import Path
from string import ascii_letters, digits
from subprocess import CalledProcessError, CompletedProcess
from typing import Any, Optional

import yaml

from subiquity.server.nonreportable import NonReportableException
from subiquitycore.utils import (
    arun_command,
    log_process_streams,
    run_command,
    system_scripts_env,
)

log = logging.getLogger("subiquity.cloudinit")

# We are removing certain 'painful' letters/numbers
# Set copied from cloud-init
# https://github.com/canonical/cloud-init/blob/6e4153b346bc0d3f3422c01a3f93ecfb28269da2/cloudinit/config/cc_set_passwords.py#L33  # noqa: E501
CLOUD_INIT_PW_SET = "".join([x for x in ascii_letters + digits if x not in "loLOI01"])


class CloudInitSchemaValidationError(NonReportableException):
    """Exception for cloud config schema validation failure."""


class CloudInitSchemaTopLevelKeyError(CloudInitSchemaValidationError):
    """Exception for when cloud-config top level keys fail to validate.

    Attributes:
        keys -- List of keys which are the cause of the failure
    """

    def __init__(
        self,
        keys: list[str],
        message: str = "Cloud config schema failed to validate top-level keys.",
    ) -> None:
        super().__init__(message)
        self.keys = keys


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
    for pkg in "cloud-init", "cloud-init-base":
        cmd = ["dpkg-query", "-W", "-f=${Version}", pkg]
        sp = run_command(cmd, check=False)
        if version := re.split("[-~]", sp.stdout)[0]:
            log.debug(f"{pkg} version: {version}")
            return version
    log.debug("cloud-init not installed")
    return ""


def supports_format_json() -> bool:
    return cloud_init_version() >= "22.4"


def supports_recoverable_errors() -> bool:
    return cloud_init_version() >= "23.4"


def supports_schema_subcommand() -> bool:
    return cloud_init_version() >= "22.2"


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


async def get_unknown_keys() -> list[str]:
    """Retrieve top-level keys causing schema failures, if any."""

    cmd: list[str] = ["cloud-init", "schema", "--system"]
    status_coro: Awaitable = arun_command(
        cmd,
        clean_locale=True,
        env=system_scripts_env(),
    )
    try:
        sp: CompletedProcess = await asyncio.wait_for(status_coro, 10)
    except asyncio.TimeoutError:
        log.warning("cloud-init schema --system timed out")
        return []

    error: str = sp.stderr  # Relies on arun_command decoding to utf-8 str by default

    # Matches:
    # ('some-key' was unexpected)
    # ('some-key', 'another-key' were unexpected)
    pattern = r"\((?P<args>'[^']+'(,\s'[^']+')*) (?:was|were) unexpected\)"
    search_result = re.search(pattern, error)

    if search_result is None:
        return []

    args_list: list[str] = search_result.group("args").split(", ")
    no_quotes: list[str] = [arg.strip("'") for arg in args_list]

    return no_quotes


async def cloud_init_status_wait() -> (bool, Optional[str]):
    """Wait for cloud-init completion, and return if timeout occurred and best
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


async def validate_cloud_init_top_level_keys() -> None:
    """Check for cloud-init schema errors in top-level keys.
    Returns (None) if the cloud-config schema validated OK according to
    cloud-init. Otherwise, a CloudInitSchemaTopLevelKeyError is thrown
    which contains a list of the top-level keys which failed to validate.
    Requires cloud-init supporting recoverable errors and extended status.

    :return: None if cloud-init schema validated successfully.
    :rtype: None
    :raises CloudInitSchemaTopLevelKeyError: If cloud-init schema did not
            validate successfully.
    """
    if not supports_schema_subcommand():
        log.debug(
            "Host cloud-config doesn't support 'schema' subcommand. "
            "Skipping top-level key cloud-config validation."
        )
        return None

    causes: list[str] = await get_unknown_keys()

    if causes:
        raise CloudInitSchemaTopLevelKeyError(keys=causes)

    return None


def validate_cloud_config_schema(data: dict[str, Any], data_source: str) -> None:
    """Validate data config adheres to strict cloud-config schema

    Log warnings on any deprecated cloud-config keys used.

    :param data: dict of cloud-config
    :param data_source: str to present in logs/errors describing
        where this config came from: autoinstall.user-data or system info
    :raises CloudInitSchemaValidationError: If cloud-config did not validate
        successfully.
    :raises CalledProcessError: In the legacy code path if calling the helper
        script fails.
    """
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "test-cloud-config.yaml"
        path.write_text(yaml.dump(data))
        # Eventually we may want to move to using the CLI when available,
        # but we can rely on the "legacy" script for now.
        legacy_cloud_init_validation(str(path), data_source)


def legacy_cloud_init_validation(config_path: str, data_source: str) -> None:
    """Validate cloud-config using helper script.

    :param config_path: path to cloud-config to validate
    :param data_source: str to present in logs/errors describing
        where this config came from: autoinstall.user-data or system info
    :raises CloudInitSchemaValidationError: If cloud-config did not validate
        successfully.
    :raises CalledProcessError: If calling the helper script fails.
    """

    try:
        proc: CompletedProcess = run_command(
            [
                "subiquity-legacy-cloud-init-validate",
                "--config",
                config_path,
                "--source",
                data_source,
            ],
            env=system_scripts_env(),
            check=True,
        )
    except CalledProcessError as cpe:
        log_process_streams(
            logging.DEBUG,
            cpe,
            "subiquity-legacy-cloud-init-validate",
        )
        raise cpe

    results: dict[str, str] = yaml.safe_load(proc.stdout)

    if warnings := results.get("warnings"):
        log.warning(warnings)

    if errors := results.get("errors"):
        raise CloudInitSchemaValidationError(errors)


async def legacy_cloud_init_extract() -> tuple[dict[str, Any], str]:
    """Load cloud-config from stages.Init() using helper script."""

    try:
        proc: CompletedProcess = await arun_command(
            ["subiquity-legacy-cloud-init-extract"],
            env=system_scripts_env(),
            check=True,
        )
    except CalledProcessError as cpe:
        log_process_streams(logging.DEBUG, cpe, "subiquity-legacy-cloud-init-extract")
        raise cpe

    extract: dict[str, Any] = yaml.safe_load(proc.stdout)

    return (extract["cloud_cfg"], extract["installer_user_name"])


def rand_password(strlen: int = 32, select_from: Optional[Sequence] = None) -> str:
    r: secrets.SystemRandom = secrets.SystemRandom()
    if not select_from:
        select_from: str = ascii_letters + digits
    return "".join([r.choice(select_from) for _x in range(strlen)])


# Generate random user passwords the same way cloud-init does
# https://github.com/canonical/cloud-init/blob/6e4153b346bc0d3f3422c01a3f93ecfb28269da2/cloudinit/config/cc_set_passwords.py#L249  # noqa: E501
def rand_user_password(pwlen: int = 20) -> str:
    return rand_password(strlen=pwlen, select_from=CLOUD_INIT_PW_SET)
