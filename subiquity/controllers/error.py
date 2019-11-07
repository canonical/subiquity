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
import json
import logging
import os
import time

import apport
import apport.crashdb
import apport.hookutils

import attr

from subiquitycore.controller import BaseController


log = logging.getLogger('subiquity.controllers.error')


class ErrorReportState(enum.Enum):
    INCOMPLETE = _("INCOMPLETE")
    DONE = _("DONE")
    ERROR = _("ERROR")


class ErrorReportKind(enum.Enum):
    BLOCK_PROBE_FAIL = _("Block device probe failure")
    DISK_PROBE_FAIL = _("Disk probe failure")
    INSTALL_FAIL = _("Install failure")
    UI = _("Installer crash")
    UNKNOWN = _("Unknown error")


@attr.s(cmp=False)
class ErrorReport:
    controller = attr.ib()
    base = attr.ib()
    pr = attr.ib()
    state = attr.ib()
    _file = attr.ib()

    meta = attr.ib(default=attr.Factory(dict))

    @classmethod
    def new(cls, controller, kind):
        base = "installer.{:.9f}.{}".format(time.time(), kind.name.lower())
        crash_file = open(
            os.path.join(controller.crash_directory, base + ".crash"),
            'wb')

        pr = apport.Report('Bug')
        pr['CrashDB'] = repr(controller.crashdb_spec)

        r = cls(
            controller=controller, base=base, pr=pr, file=crash_file,
            state=ErrorReportState.INCOMPLETE)
        r.set_meta("kind", kind.name)
        return r

    def add_info(self, _bg_attach_hook, wait=False):
        log.debug("begin adding info for report %s", self.base)

        def _bg_add_info():
            _bg_attach_hook()
            # Add basic info to report.
            self.pr.add_proc_info()
            self.pr.add_os_info()
            self.pr.add_hooks_info(None)
            apport.hookutils.attach_hardware(self.pr)
            # Because apport-cli will in general be run on a different
            # machine, we make some slightly obscure alterations to the report
            # to make this go better.

            # apport-cli gets upset if neither of these are present.
            self.pr['Package'] = 'subiquity ' + os.environ.get(
                "SNAP_REVISION", "SNAP_REVISION")
            self.pr['SourcePackage'] = 'subiquity'

            # If ExecutableTimestamp is present, apport-cli will try to check
            # that ExecutablePath hasn't changed. But it won't be there.
            del self.pr['ExecutableTimestamp']
            # apport-cli gets upset at the probert C extensions it sees in
            # here.  /proc/maps is very unlikely to be interesting for us
            # anyway.
            del self.pr['ProcMaps']
            self.pr.write(self._file)

        def added_info(fut):
            log.debug("done adding info for report %s", self.base)
            try:
                fut.result()
            except Exception:
                self.state = ErrorReportState.ERROR
                log.exception("adding info to problem report failed")
            else:
                self.state = ErrorReportState.DONE
            self._file.close()
            self._file = None
        if wait:
            _bg_add_info()
        else:
            self.controller.run_in_bg(_bg_add_info, added_info)

    def _path_with_ext(self, ext):
        return os.path.join(
            self.controller.crash_directory, self.base + '.' + ext)

    @property
    def meta_path(self):
        return self._path_with_ext('meta')

    @property
    def path(self):
        return self._path_with_ext('crash')

    def set_meta(self, key, value):
        self.meta[key] = value
        with open(self.meta_path, 'w') as fp:
            json.dump(self.meta, fp, indent=4)

    @property
    def kind(self):
        k = self.meta.get("kind", "UNKNOWN")
        return getattr(ErrorReportKind, k, ErrorReportKind.UNKNOWN)


class ErrorController(BaseController):

    def __init__(self, app):
        super().__init__(app)
        self.crash_directory = os.path.join(self.app.root, 'var/crash')
        self.crashdb_spec = {
            'impl': 'launchpad',
            'project': 'subiquity',
            }
        if self.app.opts.dry_run:
            self.crashdb_spec['launchpad_instance'] = 'staging'
        self.reports = []

    def start(self):
        os.makedirs(self.crash_directory, exist_ok=True)

    def create_report(self, kind):
        r = ErrorReport.new(self, kind)
        self.reports.insert(0, r)
        return r

    def start_ui(self):
        pass

    def cancel(self):
        pass
