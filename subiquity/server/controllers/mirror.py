# Copyright 2018 Canonical, Ltd.
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
import io
import logging
from typing import List, Optional

import attr

from subiquity.common.apidef import API
from subiquity.common.types import (
    MirrorCheckResponse,
    MirrorCheckStatus,
    MirrorGet,
    MirrorPost,
    MirrorPostResponse,
    MirrorSelectionFallback,
)
from subiquity.models.mirror import filter_candidates
from subiquity.server.apt import AptConfigCheckError, AptConfigurer, get_apt_configurer
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels
from subiquitycore.context import with_context

log = logging.getLogger("subiquity.server.controllers.mirror")


class NoUsableMirrorError(Exception):
    """Exception to be raised when none of the candidate mirrors passed the
    test."""


class MirrorCheckNotStartedError(Exception):
    """Exception to be raised when trying to cancel a mirror
    check that was not started."""


@attr.s(auto_attribs=True)
class MirrorCheck:
    task: asyncio.Task
    output: io.StringIO
    uri: str


class MirrorController(SubiquityController):
    endpoint = API.mirror

    autoinstall_key = "apt"
    autoinstall_schema = {  # This is obviously incomplete.
        "type": "object",
        "properties": {
            "preserve_sources_list": {"type": "boolean"},
            "primary": {"type": "array"},  # Legacy format defined by curtin.
            "mirror-selection": {
                "type": "object",
                "properties": {
                    "primary": {
                        "type": "array",
                        "items": {
                            "anyOf": [
                                {
                                    "type": "string",
                                    "const": "country-mirror",
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "uri": {"type": "string"},
                                        "arches": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": ["uri"],
                                },
                            ],
                        },
                    },
                },
            },
            "geoip": {"type": "boolean"},
            "sources": {"type": "object"},
            "disable_components": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "universe",
                        "multiverse",
                        "restricted",
                        "contrib",
                        "non-free",
                    ],
                },
            },
            "preferences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "package": {
                            "type": "string",
                        },
                        "pin": {
                            "type": "string",
                        },
                        "pin-priority": {
                            "type": "integer",
                        },
                    },
                    "required": [
                        "package",
                        "pin",
                        "pin-priority",
                    ],
                },
            },
            "fallback": {
                "type": "string",
                "enum": [fb.value for fb in MirrorSelectionFallback],
            },
        },
    }
    model_name = "mirror"

    def __init__(self, app):
        super().__init__(app)
        self.geoip_enabled = True
        self.cc_event = asyncio.Event()
        self.source_configured_event = asyncio.Event()
        self.network_configured_event = asyncio.Event()
        self.proxy_configured_event = asyncio.Event()
        self.app.hub.subscribe(InstallerChannels.GEOIP, self.on_geoip)
        self.app.hub.subscribe((InstallerChannels.CONFIGURED, "source"), self.on_source)
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, "network"), self.network_configured_event.set
        )
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, "proxy"), self.proxy_configured_event.set
        )
        self._apt_config_key = None
        self.test_apt_configurer: Optional[AptConfigurer] = None
        self.final_apt_configurer: Optional[AptConfigurer] = None
        self.mirror_check: Optional[MirrorCheck] = None
        self.autoinstall_apply_started = False

    def load_autoinstall_data(self, data):
        if data is None:
            return
        geoip = data.pop("geoip", True)
        self.model.load_autoinstall_data(data)
        self.geoip_enabled = geoip and self.model.wants_geoip()

    async def try_mirror_checking_once(self) -> None:
        """Try mirror checking and log result."""
        output = io.StringIO()
        try:
            await self.run_mirror_testing(output)
        except AptConfigCheckError:
            log.warning("Mirror checking failed")
            raise
        else:
            log.debug("Mirror checking successful")
        finally:
            log.debug("APT output follows")
            for line in output.getvalue().splitlines():
                log.debug("%s", line)

    async def find_and_elect_candidate_mirror(self, context):
        # Ensure we block until the proxy and network models have been
        # configured. This is particularly important in partially-automated
        # installs.
        await self.network_configured_event.wait()
        await self.proxy_configured_event.wait()
        if self.geoip_enabled:
            try:
                with context.child("waiting"):
                    await asyncio.wait_for(self.cc_event.wait(), 10)
            except asyncio.TimeoutError:
                pass

        if not self.app.base_model.network.has_network:
            log.debug("Skipping mirror check since network is not available.")
            return

        # Try each mirror one after another.
        compatibles = self.model.compatible_primary_candidates()
        for idx, candidate in enumerate(compatibles):
            log.debug("Iterating over %s", candidate.serialize_for_ai())
            if idx != 0:
                # Sleep before testing the next candidate..
                log.debug("Will check next candiate mirror after 10 seconds.")
                await asyncio.sleep(10 / self.app.scale_factor)
            if candidate.uri is None:
                log.debug("Skipping unresolved country mirror")
                continue
            candidate.stage()
            try:
                await self.try_mirror_checking_once()
            except AptConfigCheckError:
                log.debug("Retrying in 10 seconds...")
            else:
                break
            await asyncio.sleep(10 / self.app.scale_factor)
            # If the test fails a second time, give up on this mirror.
            try:
                await self.try_mirror_checking_once()
            except AptConfigCheckError:
                log.debug("Mirror is not usable.")
            else:
                break
        else:
            raise NoUsableMirrorError

        candidate.elect()

    async def apply_fallback(self):
        fallback = self.model.fallback

        if fallback == MirrorSelectionFallback.ABORT:
            log.error("aborting the install since no primary mirror is" " usable")
            # TODO there is no guarantee that raising this exception will
            # actually abort the install. If this is raised from a request
            # handler, for instance, it will just return a HTTP 500 error. For
            # now, this is acceptable since we do not call apply_fallback from
            # request handlers.
            raise RuntimeError("aborting install since no mirror is usable")
        elif fallback == MirrorSelectionFallback.OFFLINE_INSTALL:
            log.warning(
                "reverting to an offline install since no primary" " mirror is usable"
            )
            self.app.base_model.network.force_offline = True
        elif fallback == MirrorSelectionFallback.CONTINUE_ANYWAY:
            log.warning("continuing the install despite no usable mirror")
            # Pick a candidate that is supposedly compatible and that has a
            # URI. If it does not work, well that's too bad.
            filters = [
                lambda c: c.uri is not None,
                lambda c: c.supports_arch(self.model.architecture),
            ]
            try:
                candidate = next(
                    filter_candidates(self.model.primary_candidates, filters=filters)
                )
            except StopIteration:
                candidate = next(
                    filter_candidates(
                        self.model.get_default_primary_candidates(), filters=filters
                    )
                )
            log.warning(
                "deciding to elect primary mirror %s", candidate.serialize_for_ai()
            )
            candidate.elect()
        else:
            raise RuntimeError(f"invalid fallback value: {fallback}")

    async def run_mirror_selection_or_fallback(self, context):
        """Perform the mirror selection and apply the configured fallback
        method if no mirror is usable."""
        try:
            await self.find_and_elect_candidate_mirror(context=context)
        except NoUsableMirrorError:
            await self.apply_fallback()

    @with_context()
    async def apply_autoinstall_config(self, context):
        self.autoinstall_apply_started = True
        await self.run_mirror_selection_or_fallback(context)

    def on_geoip(self):
        if self.geoip_enabled:
            self.model.set_country(self.app.geoip.countrycode)
        self.cc_event.set()

    async def on_source(self):
        if self.autoinstall_apply_started:
            # Alternatively, we should cancel and restart the
            # apply_autoinstall_config but this is out of scope.
            raise RuntimeError(
                "source model has changed but autoinstall"
                " configuration is already being applied"
            )
        source_entry = self.app.base_model.source.current
        if source_entry.variant == "core":
            self.test_apt_configurer = None
        else:
            self.test_apt_configurer = get_apt_configurer(
                self.app, self.app.controllers.Source.get_handler()
            )
        self.source_configured_event.set()

    def serialize(self):
        # TODO what to do with the candidates?
        if self.model.primary_elected is not None:
            return self.model.primary_elected.uri
        return None

    def deserialize(self, data):
        # TODO what to do with the candidates?
        if data is not None:
            self.model.create_primary_candidate(data).elect()

    def make_autoinstall(self):
        config = self.model.make_autoinstall()
        config["geoip"] = self.geoip_enabled
        return config

    async def _promote_mirror(self):
        if self.model.primary_elected is None:
            # NOTE: In practice, this should only happen if the mirror was
            # marked configured using a POST to mark_configured ; which is not
            # recommended. Clients should do a POST request to /mirror with
            # null as the body instead.
            await self.run_mirror_selection_or_fallback(self.context)
        assert self.final_apt_configurer is not None
        await self.final_apt_configurer.apply_apt_config(self.context, final=True)

    async def run_mirror_testing(self, output: io.StringIO) -> None:
        await self.source_configured_event.wait()
        # If the source model changes at the wrong time, there is a chance that
        # self.test_apt_configurer will be replaced between the call to
        # apply_apt_config and run_apt_config_check. Just make sure we still
        # use the original one.
        configurer = self.test_apt_configurer
        if configurer is None:
            # i.e. core
            return
        await configurer.apply_apt_config(self.context, final=False)
        await configurer.run_apt_config_check(output)

    async def wait_config(self, variation_name: str) -> AptConfigurer:
        self.final_apt_configurer = get_apt_configurer(
            self.app, self.app.controllers.Source.get_handler(variation_name)
        )
        await self._promote_mirror()
        assert self.final_apt_configurer is not None
        return self.final_apt_configurer

    async def GET(self) -> MirrorGet:
        elected: Optional[str] = None
        staged: Optional[str] = None
        candidates: List[str] = []
        source_entry = self.app.base_model.source.current
        if source_entry.variant == "core":
            relevant = False
        else:
            relevant = True
            if self.model.primary_elected is not None:
                elected = self.model.primary_elected.uri
            if self.model.primary_staged is not None:
                staged = self.model.primary_staged.uri

            compatibles = self.model.compatible_primary_candidates()
            # Skip the country-mirrors if they have not been resolved yet.
            candidates = [c.uri for c in compatibles if c.uri is not None]
        return MirrorGet(
            relevant=relevant, elected=elected, candidates=candidates, staged=staged
        )

    async def POST(self, data: Optional[MirrorPost]) -> MirrorPostResponse:
        log.debug(data)
        if data is None:
            # If this call fails with NoUsableMirrorError, we do not
            # automatically apply the fallback method. Instead, we let the
            # client know that they need to adjust something. Disabling the
            # network would be one way to do it. The client can also consider
            # this a fatal error and give up on the install.
            try:
                await self.find_and_elect_candidate_mirror(self.context)
            except NoUsableMirrorError:
                log.warning(
                    "found no usable mirror, expecting the client to"
                    " give up or to adjust the settings and retry"
                )
                return MirrorPostResponse.NO_USABLE_MIRROR
            else:
                await self.configured()
                return MirrorPostResponse.OK

        if data.candidates is not None:
            if not data.candidates:
                raise ValueError("cannot specify an empty list of candidates")
            uris = data.candidates
            self.model.primary_candidates = [
                self.model.create_primary_candidate(uri) for uri in uris
            ]

        if data.staged is not None:
            self.model.create_primary_candidate(data.staged).stage()

        if data.elected is not None:
            self.model.create_primary_candidate(data.elected).elect()

            # NOTE we could also do this unconditionally when generating the
            # autoinstall configuration. But doing it here gives the user the
            # ability to use a mirror for one install without it ending up in
            # the autoinstall config. Is it worth it though?
            def ensure_elected_in_candidates():
                if any(
                    map(lambda c: c.uri == data.elected, self.model.primary_candidates)
                ):
                    return
                self.model.primary_candidates.insert(0, self.model.primary_elected)

            if data.candidates is None:
                ensure_elected_in_candidates()

            await self.configured()
        return MirrorPostResponse.OK

    async def disable_components_GET(self) -> List[str]:
        return sorted(self.model.disabled_components)

    async def disable_components_POST(self, data: List[str]):
        log.debug(data)
        self.model.disabled_components = set(data)

    async def check_mirror_start_POST(self, cancel_ongoing: bool = False) -> None:
        if self.mirror_check is not None and not self.mirror_check.task.done():
            if cancel_ongoing:
                await self.check_mirror_abort_POST()
            else:
                assert False
        output = io.StringIO()
        self.mirror_check = MirrorCheck(
            uri=self.model.primary_staged.uri,
            task=asyncio.create_task(self.run_mirror_testing(output)),
            output=output,
        )

    async def check_mirror_progress_GET(self) -> Optional[MirrorCheckResponse]:
        if self.mirror_check is None:
            return None
        if self.mirror_check.task.done():
            if self.mirror_check.task.exception():
                log.warning(
                    "Mirror check failed: %r", self.mirror_check.task.exception()
                )
                status = MirrorCheckStatus.FAILED
            else:
                status = MirrorCheckStatus.OK
        else:
            status = MirrorCheckStatus.RUNNING

        return MirrorCheckResponse(
            url=self.mirror_check.uri,
            status=status,
            output=self.mirror_check.output.getvalue(),
        )

    async def check_mirror_abort_POST(self) -> None:
        if self.mirror_check is None:
            raise MirrorCheckNotStartedError
        self.mirror_check.task.cancel()
        self.mirror_check = None

    async def fallback_GET(self) -> MirrorSelectionFallback:
        return self.model.fallback

    async def fallback_POST(self, data: MirrorSelectionFallback):
        self.model.fallback = data
