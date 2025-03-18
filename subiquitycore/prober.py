# Copyright 2015 Canonical, Ltd.
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
import logging
from typing import Any

import yaml
from probert.network import StoredDataObserver, UdevObserver

from subiquitycore.async_helpers import run_in_thread

log = logging.getLogger("subiquitycore.prober")


class Prober:
    def __init__(self, machine_config, debug_flags):
        self.saved_config = None
        if machine_config:
            self.saved_config = yaml.safe_load(machine_config)
        self.debug_flags = debug_flags
        log.debug("Prober() init finished, data:{}".format(self.saved_config))

    def probe_network(self, receiver, *, with_wlan_listener: bool):
        if self.saved_config is not None:
            observer = StoredDataObserver(
                self.saved_config["network"],
                receiver,
                with_wlan_listener=with_wlan_listener,
            )
        else:
            observer = UdevObserver(receiver, with_wlan_listener=with_wlan_listener)
        return observer, observer.start()

    async def get_storage(self, probe_types=None):
        if self.saved_config is not None:
            flag = "bpfail-full"
            if probe_types is not None:
                flag = "bpfail-restricted"
            if flag in self.debug_flags:
                await asyncio.sleep(2)
                1 / 0
            r = self.saved_config["storage"].copy()
            if probe_types is not None and "defaults" not in probe_types:
                for k in self.saved_config["storage"]:
                    if k not in probe_types:
                        r[k] = {}
            return r

        from probert.storage import Storage

        # Until probert is completely free of blocking IO, we should continue
        # running it in a separate thread.
        def run_probert(probe_types):
            return asyncio.run(
                Storage().probe(probe_types=probe_types, parallelize=True)
            )

        return await run_in_thread(run_probert, probe_types)

    async def get_firmware(self) -> dict[str, Any]:
        from probert.firmware import FirmwareProber

        prober = FirmwareProber()
        return await prober.probe()
