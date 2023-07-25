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
import logging
from typing import Callable, Optional

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.filesystem import gaps
from subiquity.common.filesystem.manipulator import FilesystemManipulator
from subiquity.common.types import (
    GuidedCapability,
    GuidedChoiceV2,
    GuidedStorageResponseV2,
    GuidedStorageTargetManual,
    ProbeStatus,
    StorageResponseV2,
)
from subiquity.models.filesystem import Bootloader, FilesystemModel, raidlevels_by_value
from subiquity.ui.views import FilesystemView, GuidedDiskSelectionView
from subiquity.ui.views.filesystem.probing import ProbingFailed, SlowProbing
from subiquitycore.async_helpers import run_bg_task
from subiquitycore.lsb_release import lsb_release
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.client.controllers.filesystem")


class FilesystemController(SubiquityTuiController, FilesystemManipulator):
    endpoint_name = "storage"

    def __init__(self, app):
        super().__init__(app)
        self.model = None
        self.answers.setdefault("guided", False)
        self.answers.setdefault("tpm-default", False)
        self.answers.setdefault("guided-index", 0)
        self.answers.setdefault("manual", [])
        self.current_view: Optional[BaseView] = None

    async def make_ui(self) -> Callable[[], BaseView]:
        def get_current_view() -> BaseView:
            assert self.current_view is not None
            return self.current_view

        status: GuidedStorageResponseV2 = await self.endpoint.v2.guided.GET()
        if status.status == ProbeStatus.PROBING:
            run_bg_task(self._wait_for_probing())
            self.current_view = SlowProbing(self)
        else:
            self.current_view = await self.make_guided_ui(status)
        # NOTE: If we return a BaseView instance directly here, we have no
        # guarantee that it will be displayed on the screen by the time the
        # probing operation finishes. Therefore, to allow us to reliably
        # replace the screen by the "Guided Storage" when the probing operation
        # finishes, we add a level of indirection.
        # In essence, this allows us to make modifications to the screen
        # that eventually will be displayed.
        # This is mostly a workaround for the issue described in LP #1968161
        return get_current_view

    async def _wait_for_probing(self):
        status = await self.endpoint.v2.guided.GET(wait=True)
        self.current_view = await self.make_guided_ui(status)
        if isinstance(self.ui.body, SlowProbing):
            self.ui.set_body(self.current_view)
        else:
            log.debug("not refreshing the display. Current display is %r", self.ui.body)

    async def make_guided_ui(
        self,
        status: GuidedStorageResponseV2,
    ) -> GuidedDiskSelectionView:
        if status.status == ProbeStatus.FAILED:
            self.app.show_error_report(status.error_report)
            return ProbingFailed(self, status.error_report)

        response: StorageResponseV2 = await self.endpoint.v2.GET(include_raid=True)

        disk_by_id = {disk.id: disk for disk in response.disks}

        if status.error_report:
            self.app.show_error_report(status.error_report)

        return GuidedDiskSelectionView(self, status.targets, disk_by_id)

    async def run_answers(self):
        # Wait for probing to finish.
        while not isinstance(self.ui.body, GuidedDiskSelectionView):
            await asyncio.sleep(0.1)

        if self.answers["tpm-default"]:
            self.app.answers["filesystem-confirmed"] = True
            self.ui.body.done(self.ui.body.form)
        if self.answers["guided"]:
            targets = self.ui.body.form.targets
            if "guided-index" in self.answers:
                target = targets[self.answers["guided-index"]]
            elif "guided-label" in self.answers:
                label = self.answers["guided-label"]
                disk_by_id = self.ui.body.form.disk_by_id
                [target] = [t for t in targets if disk_by_id[t.disk_id].label == label]
            method = self.answers.get("guided-method")
            value = {
                "disk": target,
                "use_lvm": method == "lvm",
            }
            passphrase = self.answers.get("guided-passphrase")
            if passphrase is not None:
                value["lvm_options"] = {
                    "encrypt": True,
                    "luks_options": {
                        "passphrase": passphrase,
                        "confirm_passphrase": passphrase,
                    },
                }
            self.ui.body.form.guided_choice.value = value
            self.ui.body.done(None)
            self.app.answers["filesystem-confirmed"] = True
            while not isinstance(self.ui.body, FilesystemView):
                await asyncio.sleep(0.1)
            self.finish()
        elif self.answers["manual"]:
            await self._guided_choice(
                GuidedChoiceV2(
                    target=GuidedStorageTargetManual(),
                    capability=GuidedCapability.MANUAL,
                )
            )
            await self._run_actions(self.answers["manual"])
            self.answers["manual"] = []

    def _action_get(self, id):
        dev_spec = id[0].split()
        dev = None
        if dev_spec[0] == "disk":
            if dev_spec[1] == "index":
                dev = self.model.all_disks()[int(dev_spec[2])]
            elif dev_spec[1] == "serial":
                dev = self.model._one(type="disk", serial=dev_spec[2])
        elif dev_spec[0] == "raid":
            if dev_spec[1] == "name":
                for r in self.model.all_raids():
                    if r.name == dev_spec[2]:
                        dev = r
                        break
        elif dev_spec[0] == "volgroup":
            if dev_spec[1] == "name":
                for r in self.model.all_volgroups():
                    if r.name == dev_spec[2]:
                        dev = r
                        break
        if dev is None:
            raise Exception("could not resolve {}".format(id))
        if len(id) > 1:
            part, index = id[1].split()
            if part == "part":
                return dev.partitions()[int(index)]
        else:
            return dev
        raise Exception("could not resolve {}".format(id))

    def _action_clean_devices_raid(self, devices):
        r = {self._action_get(d): v for d, v in zip(devices[::2], devices[1::2])}
        for d in r:
            assert d.ok_for_raid
        return r

    def _action_clean_devices_vg(self, devices):
        r = {self._action_get(d): "active" for d in devices}
        for d in r:
            assert d.ok_for_lvm_vg
        return r

    def _action_clean_level(self, level):
        return raidlevels_by_value[level]

    async def _answers_action(self, action):
        from subiquity.ui.views.filesystem.delete import ConfirmDeleteStretchy
        from subiquitycore.ui.stretchy import StretchyOverlay

        log.debug("_answers_action %r", action)
        if "obj" in action:
            obj = self._action_get(action["obj"])
            action_name = action["action"]
            if action_name == "MAKE_BOOT":
                action_name = "TOGGLE_BOOT"
            if action_name == "CREATE_LV":
                action_name = "PARTITION"
            if action_name == "PARTITION":
                obj = gaps.largest_gap(obj)
            meth = getattr(
                self.ui.body.avail_list, "_{}_{}".format(obj.type, action_name)
            )
            meth(obj)
            yield
            body = self.ui.body._w
            if not isinstance(body, StretchyOverlay):
                return
            if isinstance(body.stretchy, ConfirmDeleteStretchy):
                if action.get("submit", True):
                    body.stretchy.done()
            else:
                async for _ in self._enter_form_data(
                    body.stretchy.form, action["data"], action.get("submit", True)
                ):
                    pass
        elif action["action"] == "create-raid":
            self.ui.body.create_raid()
            yield
            body = self.ui.body._w
            async for _ in self._enter_form_data(
                body.stretchy.form,
                action["data"],
                action.get("submit", True),
                clean_suffix="raid",
            ):
                pass
        elif action["action"] == "create-vg":
            self.ui.body.create_vg()
            yield
            body = self.ui.body._w
            async for _ in self._enter_form_data(
                body.stretchy.form,
                action["data"],
                action.get("submit", True),
                clean_suffix="vg",
            ):
                pass
        elif action["action"] == "done":
            if not self.ui.body.done_btn.enabled:
                raise Exception("answers did not provide complete fs config")
            self.app.answers["filesystem-confirmed"] = True
            self.finish()
        else:
            raise Exception("could not process action {}".format(action))

    async def _guided_choice(self, choice: GuidedChoiceV2):
        coro = self.endpoint.guided.POST(choice)
        if not choice.capability.supports_manual_customization():
            self.app.next_screen(coro)
            return
        status = await self.app.wait_with_progress(coro)
        self.model = FilesystemModel(status.bootloader)
        self.model.load_server_data(status)
        if self.model.bootloader == Bootloader.PREP:
            self.supports_resilient_boot = False
        else:
            release = lsb_release(dry_run=self.app.opts.dry_run)["release"]
            self.supports_resilient_boot = release >= "20.04"
        self.ui.set_body(FilesystemView(self.model, self))

    def guided_choice(self, choice):
        run_bg_task(self._guided_choice(choice))

    async def _guided(self):
        self.ui.set_body((await self.make_ui())())

    def guided(self):
        run_bg_task(self._guided())

    def reset(self, refresh_view):
        log.info("Resetting Filesystem model")
        self.app.ui.block_input = True
        run_bg_task(self._reset(refresh_view))

    async def _reset(self, refresh_view):
        status = await self.endpoint.reset.POST()
        self.app.ui.block_input = False
        self.model.load_server_data(status)
        if refresh_view:
            self.ui.set_body(FilesystemView(self.model, self))

    def cancel(self):
        self.app.prev_screen()

    def finish(self):
        log.debug("FilesystemController.finish next_screen")
        self.app.next_screen(self.endpoint.POST(self.model._render_actions()))
