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

import enum
import logging
import os

import requests.exceptions

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

log = logging.getLogger('subiquity.controllers.refresh')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()

    AVAILABLE = enum.auto()
    UNAVAILABLE = enum.auto()

    def is_definite(self):
        return self in [self.AVAILABLE, self.UNAVAILABLE]


class RefreshController(BaseController):

    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.snap_name = os.environ.get("SNAP_NAME", "subiquity")
        self.check_state = CheckState.NOT_STARTED
        self.view = None
        self.offered_first_time = False

    def snapd_network_changed(self):
        # If we restarted into this version, don't check for a new version.
        if self.updated:
            return
        # If we got an answer, don't check again.
        if self.check_state.is_definite():
            return
        self.check_state = CheckState.CHECKING
        self.run_in_bg(self._bg_check_for_update, self._check_result)

    def _bg_check_for_update(self):
        return self.snapd_connection.get('v2/find', select='refresh')

    def _check_result(self, fut):
        # If we managed to send concurrent requests and one has
        # already provided an answer, just forget all about the other
        # one!
        if self.check_state.is_definite():
            return
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.exception("checking for update")
            self.check_state = CheckState.FAILED
            return
        result = response.json()
        log.debug("_check_result %s", result)
        for snap in result["result"]:
            if snap["name"] == self.snap_name:
                self.check_state = CheckState.AVAILABLE
                break
        else:
            self.check_state = CheckState.UNAVAILABLE
        if self.view:
            self.view.update_check_state()

    def start_update(self, callback):
        update_marker = os.path.join(self.application.state_dir, 'updating')
        open(update_marker, 'w').close()
        self.run_in_bg(
            self._bg_start_update,
            lambda fut: self.update_started(fut, callback))

    def _bg_start_update(self):
        return self.snapd_connection.post(
            'v2/snaps/subiquity', {'action': 'refresh'})

    def update_started(self, fut, callback):
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.exception("requesting update")
            self.update_state = CheckState.FAILED
            self.update_failure = e
            return
        result = response.json()
        log.debug("%s", result)
        callback(result['change'])

    def get_progress(self, change, callback):
        self.run_in_bg(
            lambda: self._bg_get_progress(change),
            lambda fut: self.got_progress(fut, callback))

    def _bg_get_progress(self, change):
        return self.snapd_connection.get('v2/changes/{}'.format(change))

    def got_progress(self, fut, callback):
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.exception("checking for progress")
            self.update_state = CheckState.FAILED
            self.update_failure = e
            return
        result = response.json()
        callback(result['result'])

    def default(self, index=1):
        from subiquity.ui.views.refresh import RefreshView
        if self.updated:
            raise Skip()
        show = False
        if index == 1:
            if self.check_state == CheckState.AVAILABLE:
                show = True
                self.offered_first_time = True
        elif index == 2:
            if not self.offered_first_time:
                if self.check_state in [CheckState.AVAILABLE,
                                        CheckState.CHECKING]:
                    show = True
        else:
            raise AssertionError("unexpected index {}".format(index))
        if show:
            self.view = RefreshView(self)
            self.ui.set_body(self.view)
        else:
            raise Skip()

    def done(self, sender=None):
        self.signal.emit_signal('next-screen')

    def cancel(self, sender=None):
        self.signal.emit_signal('prev-screen')
