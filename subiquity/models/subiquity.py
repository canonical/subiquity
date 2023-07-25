# Copyright 2015 Canonical, Ltd.
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
import functools
import json
import logging
import os
import uuid
from collections import OrderedDict
from typing import Any, Dict, Set

import yaml
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)

try:
    from cloudinit.config.schema import SchemaProblem
except ImportError:

    def SchemaProblem(x, y):
        return (x, y)  # TODO(drop on cloud-init 22.3 SRU)


from curtin.config import merge_config

from subiquity.common.resources import get_users_and_groups
from subiquity.server.types import InstallerChannels
from subiquitycore.file_util import generate_timestamped_header, write_file
from subiquitycore.lsb_release import lsb_release

from .ad import AdModel
from .codecs import CodecsModel
from .drivers import DriversModel
from .filesystem import FilesystemModel
from .identity import IdentityModel
from .integrity import IntegrityModel
from .kernel import KernelModel
from .keyboard import KeyboardModel
from .locale import LocaleModel
from .mirror import MirrorModel
from .network import NetworkModel
from .oem import OEMModel
from .proxy import ProxyModel
from .snaplist import SnapListModel
from .source import SourceModel
from .ssh import SSHModel
from .timezone import TimeZoneModel
from .ubuntu_pro import UbuntuProModel
from .updates import UpdatesModel

log = logging.getLogger("subiquity.models.subiquity")


def merge_cloud_init_config(target, source):
    # type: (dict, dict) -> None
    """
    Merges the ``source`` dictionary into the ``target`` dictionary:

    * If both items are dictionaries, they are merged recursively.
    * If both items are lists, contents of the source list are appended
    to the target list.
    * Otherwise, the source item overwrites the target item.

    Based on the ``curtin.config.merge_config`` function.
    """
    for k, v in source.items():
        if isinstance(v, dict) and isinstance(target.get(k, None), dict):
            merge_cloud_init_config(target[k], v)
        elif isinstance(v, list) and isinstance(target.get(k, None), list):
            target[k].extend(v)
        else:
            target[k] = v


def _represent_dict_order(self, data):
    """http://stackoverflow.com/a/8661021"""
    return self.represent_mapping("tag:yaml.org,2002:map", data.items())


def setup_yaml():
    yaml.add_representer(OrderedDict, _represent_dict_order)


setup_yaml()

HOSTS_CONTENT = """\
127.0.0.1 localhost
127.0.1.1 {hostname}

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
"""

CLOUDINIT_CLEAN_FILE_TMPL = """\
#!/usr/bin/env python3
# Remove live-installer config artifacts when running: sudo cloud-init clean
{header}

import os

for cfg_file in {cfg_files}:
    try:
        os.remove(cfg_file)
    except FileNotFoundError:
        pass
"""

# Emit #cloud-config write_files entry to disable cloud-init after install
CLOUDINIT_DISABLE_AFTER_INSTALL = {
    "path": "/etc/cloud/cloud-init.disabled",
    "defer": True,
    "content": (
        "Disabled by Ubuntu live installer after first boot.\n"
        "To re-enable cloud-init on this image run:\n"
        "  sudo cloud-init clean --machine-id\n"
    ),
}


class ModelNames:
    def __init__(self, default_names, **per_variant_names):
        self.default_names = default_names
        self.per_variant_names = per_variant_names

    def for_variant(self, variant):
        return self.default_names | self.per_variant_names.get(variant, set())

    def all(self):
        r = set(self.default_names)
        for v in self.per_variant_names.values():
            r |= v
        return r


class DebconfSelectionsModel:
    def __init__(self):
        self.selections = ""

    def render(self):
        return {}

    def get_apt_config(self, final: bool, has_network: bool) -> Dict[str, Any]:
        return {"debconf_selections": {"subiquity": self.selections}}


class SubiquityModel:
    """The overall model for subiquity."""

    target = "/target"
    chroot_prefix = ["chroot", target]

    def __init__(self, root, hub, install_model_names, postinstall_model_names):
        self.root = root
        self.hub = hub
        if root != "/":
            self.target = root
            self.chroot_prefix = []

        self.active_directory = AdModel()
        self.codecs = CodecsModel()
        self.debconf_selections = DebconfSelectionsModel()
        self.drivers = DriversModel()
        self.filesystem = FilesystemModel()
        self.identity = IdentityModel()
        self.integrity = IntegrityModel()
        self.kernel = KernelModel()
        self.keyboard = KeyboardModel(self.root)
        self.locale = LocaleModel(self.chroot_prefix)
        self.mirror = MirrorModel()
        self.network = NetworkModel()
        self.oem = OEMModel()
        self.packages = []
        self.proxy = ProxyModel()
        self.snaplist = SnapListModel()
        self.ssh = SSHModel()
        self.source = SourceModel()
        self.timezone = TimeZoneModel()
        self.ubuntu_pro = UbuntuProModel()
        self.updates = UpdatesModel()
        self.userdata = {}

        self._confirmation = asyncio.Event()
        self._confirmation_task = None

        self._configured_names = set()
        self._install_model_names = install_model_names
        self._postinstall_model_names = postinstall_model_names
        self._cur_install_model_names = install_model_names.default_names
        self._cur_postinstall_model_names = postinstall_model_names.default_names
        self._install_event = asyncio.Event()
        self._postinstall_event = asyncio.Event()
        all_names = set()
        all_names.update(install_model_names.all())
        all_names.update(postinstall_model_names.all())
        for name in all_names:
            hub.subscribe(
                (InstallerChannels.CONFIGURED, name),
                functools.partial(self._configured, name),
            )

    def set_source_variant(self, variant):
        self._cur_install_model_names = self._install_model_names.for_variant(variant)
        self._cur_postinstall_model_names = self._postinstall_model_names.for_variant(
            variant
        )
        unconfigured_install_model_names = (
            self._cur_install_model_names - self._configured_names
        )
        if unconfigured_install_model_names:
            if self._install_event.is_set():
                self._install_event = asyncio.Event()
            if self._confirmation_task is not None:
                self._confirmation_task.cancel()
        else:
            self._install_event.set()
        unconfigured_postinstall_model_names = (
            self._cur_postinstall_model_names - self._configured_names
        )
        if unconfigured_postinstall_model_names:
            if self._postinstall_event.is_set():
                self._postinstall_event = asyncio.Event()
        else:
            self._postinstall_event.set()

    def _configured(self, model_name):
        """Add the model to the set of models that have been configured. If
        there is no more model to configure in the relevant section(s) (i.e.,
        INSTALL or POSTINSTALL), we trigger the associated event(s)."""

        def log_and_trigger(stage: str, names: Set[str], event: asyncio.Event) -> None:
            unconfigured = names - self._configured_names
            log.debug(
                "model %s for %s stage is configured, to go %s",
                model_name,
                stage,
                unconfigured,
            )
            if not unconfigured:
                event.set()

        self._configured_names.add(model_name)
        if model_name in self._cur_install_model_names:
            log_and_trigger(
                stage="install",
                names=self._cur_install_model_names,
                event=self._install_event,
            )
        if model_name in self._cur_postinstall_model_names:
            log_and_trigger(
                stage="postinstall",
                names=self._cur_postinstall_model_names,
                event=self._postinstall_event,
            )

    async def wait_install(self):
        if len(self._cur_install_model_names) == 0:
            self._install_event.set()
        await self._install_event.wait()

    async def wait_postinstall(self):
        if len(self._cur_postinstall_model_names) == 0:
            self._postinstall_event.set()
        await self._postinstall_event.wait()

    async def wait_confirmation(self):
        if self._confirmation_task is None:
            self._confirmation_task = asyncio.create_task(self._confirmation.wait())
        try:
            await self._confirmation_task
        except asyncio.CancelledError:
            return False
        else:
            return True
        finally:
            self._confirmation_task = None

    def is_postinstall_only(self, model_name):
        return (
            model_name in self._cur_postinstall_model_names
            and model_name not in self._cur_install_model_names
        )

    async def confirm(self):
        self._confirmation.set()
        await self.hub.abroadcast(InstallerChannels.INSTALL_CONFIRMED)

    def validate_cloudconfig_schema(self, data: dict, data_source: str):
        """Validate data config adheres to strict cloud-config schema

        Log warnings on any deprecated cloud-config keys used.

        :param data: dict of valid cloud-config
        :param data_source: str to present in logs/errors describing
            where this config came from: autoinstall.user-data or system info

        :raise SchemaValidationError: on invalid cloud-config schema
        """
        # cloud-init v. 22.3 will allow for log_deprecations=True to avoid
        # raising errors on deprecated keys.
        # In the meantime, iterate over schema_deprecations to log warnings.
        try:
            validate_cloudconfig_schema(data, schema=get_schema(), strict=True)
        except SchemaValidationError as e:
            if hasattr(e, "schema_deprecations"):
                warnings = []
                deprecations = getattr(e, "schema_deprecations")
                if deprecations:
                    for schema_path, message in deprecations:
                        warnings.append(message)
                if warnings:
                    log.warning(
                        "The cloud-init configuration for %s contains"
                        " deprecated values:\n%s",
                        data_source,
                        "\n".join(warnings),
                    )
            if e.schema_errors:
                if data_source == "autoinstall.user-data":
                    errors = [
                        SchemaProblem(f"{data_source}.{path}", message)
                        for (path, message) in e.schema_errors
                    ]
                else:
                    errors = e.schema_errors
                raise SchemaValidationError(schema_errors=errors)

    def _cloud_init_config(self):
        config = {
            "growpart": {
                "mode": "off",
            },
            "resize_rootfs": False,
        }
        if self.identity.hostname is not None:
            config["preserve_hostname"] = True
        user = self.identity.user
        if user:
            groups = get_users_and_groups(self.chroot_prefix)
            user_info = {
                "name": user.username,
                "gecos": user.realname,
                "passwd": user.password,
                "shell": "/bin/bash",
                "groups": ",".join(sorted(groups)),
                "lock_passwd": False,
            }
            if self.ssh.authorized_keys:
                user_info["ssh_authorized_keys"] = self.ssh.authorized_keys
            config["users"] = [user_info]
        else:
            if self.ssh.authorized_keys:
                config["ssh_authorized_keys"] = self.ssh.authorized_keys
        if self.ssh.install_server:
            config["ssh_pwauth"] = self.ssh.pwauth
        for model_name in self._postinstall_model_names.all():
            model = getattr(self, model_name)
            if getattr(model, "make_cloudconfig", None):
                merge_config(config, model.make_cloudconfig())
        merge_cloud_init_config(config, self.userdata)
        if lsb_release()["release"] not in ("20.04", "22.04"):
            config.setdefault("write_files", []).append(CLOUDINIT_DISABLE_AFTER_INSTALL)
        self.validate_cloudconfig_schema(data=config, data_source="system install")
        return config

    async def target_packages(self):
        packages = list(self.packages)
        for model_name in self._postinstall_model_names.all():
            meth = getattr(getattr(self, model_name), "target_packages", None)
            if meth is not None:
                packages.extend(await meth())
        return packages

    def _cloud_init_files(self):
        # TODO, this should be moved to the in-target cloud-config seed so on
        # first boot of the target, it reconfigures datasource_list to none
        # for subsequent boots.
        # (mwhudson does not entirely know what the above means!)
        userdata = "#cloud-config\n" + yaml.dump(self._cloud_init_config())
        metadata = {"instance-id": str(uuid.uuid4())}
        config = yaml.dump(
            {
                "datasource_list": ["None"],
                "datasource": {
                    "None": {
                        "userdata_raw": userdata,
                        "metadata": metadata,
                    },
                },
            }
        )
        files = [
            ("etc/cloud/cloud.cfg.d/99-installer.cfg", config, 0o600),
            ("etc/cloud/ds-identify.cfg", "policy: enabled\n", 0o644),
        ]
        # Add cloud-init clean hooks to support golden-image creation.
        cfg_files = ["/" + path for (path, _content, _cmode) in files]
        cfg_files.extend(self.network.rendered_config_paths())
        if lsb_release()["release"] not in ("20.04", "22.04"):
            cfg_files.append("/etc/cloud/cloud-init.disabled")

        if self.identity.hostname is not None:
            hostname = self.identity.hostname.strip()
            files.extend(
                [
                    ("etc/hostname", hostname + "\n", 0o644),
                    ("etc/hosts", HOSTS_CONTENT.format(hostname=hostname), 0o644),
                ]
            )

        files.append(
            (
                "etc/cloud/clean.d/99-installer",
                CLOUDINIT_CLEAN_FILE_TMPL.format(
                    header=generate_timestamped_header(),
                    cfg_files=json.dumps(sorted(cfg_files)),
                ),
                0o755,
            )
        )
        return files

    def configure_cloud_init(self):
        if self.target is None:
            # i.e. reset_partition_only
            return
        if self.source.current.variant == "core":
            # can probably be supported but requires changes
            return
        for path, content, cmode in self._cloud_init_files():
            path = os.path.join(self.target, path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write_file(path, content, cmode=cmode)

    def _media_info(self):
        if os.path.exists("/cdrom/.disk/info"):
            with open("/cdrom/.disk/info") as fp:
                return fp.read()
        else:
            return "media-info"

    def _machine_id(self):
        with open("/etc/machine-id") as fp:
            return fp.read()

    def render(self):
        config = {
            "grub": {
                "terminal": "unmodified",
                "probe_additional_os": True,
                "reorder_uefi": False,
            },
            "install": {
                "unmount": "disabled",
                "save_install_config": False,
                "save_install_log": False,
            },
            "pollinate": {
                "user_agent": {
                    "subiquity": "%s_%s"
                    % (
                        os.environ.get("SNAP_VERSION", "dry-run"),
                        os.environ.get("SNAP_REVISION", "dry-run"),
                    ),
                },
            },
            "write_files": {
                "etc_machine_id": {
                    "path": "etc/machine-id",
                    "content": self._machine_id(),
                    "permissions": 0o444,
                },
                "media_info": {
                    "path": "var/log/installer/media-info",
                    "content": self._media_info(),
                    "permissions": 0o644,
                },
            },
        }

        if os.path.exists("/run/casper-md5check.json"):
            with open("/run/casper-md5check.json") as fp:
                config["write_files"]["md5check"] = {
                    "path": "var/log/installer/casper-md5check.json",
                    "content": fp.read(),
                    "permissions": 0o644,
                }

        for model_name in self._install_model_names.all():
            model = getattr(self, model_name)
            log.debug("merging config from %s", model)
            merge_config(config, model.render())

        return config
