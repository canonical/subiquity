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

import bson

import attr

import requests

import urwid

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

from subiquity.async_helpers import (
    run_in_thread,
    schedule_task,
    )


log = logging.getLogger('subiquity.controllers.error')


class ErrorReportState(enum.Enum):
    INCOMPLETE = enum.auto()
    LOADING = enum.auto()
    DONE = enum.auto()
    ERROR_GENERATING = enum.auto()
    ERROR_LOADING = enum.auto()


class ErrorReportKind(enum.Enum):
    BLOCK_PROBE_FAIL = _("Block device probe failure")
    DISK_PROBE_FAIL = _("Disk probe failure")
    INSTALL_FAIL = _("Install failure")
    UI = _("Installer crash")
    UNKNOWN = _("Unknown error")


@attr.s(cmp=False)
class Upload(metaclass=urwid.MetaSignals):
    signals = ['progress']

    controller = attr.ib()
    bytes_to_send = attr.ib()
    bytes_sent = attr.ib(default=0)
    pipe_w = attr.ib(default=None)
    cancelled = attr.ib(default=False)

    def start(self):
        self.pipe_w = self.controller.loop.watch_pipe(self._progress)

    def _progress(self, x):
        urwid.emit_signal(self, 'progress')

    def _bg_update(self, sent, to_send=None):
        self.bytes_sent = sent
        if to_send is not None:
            self.bytes_to_send = to_send
        os.write(self.pipe_w, b'x')

    def stop(self):
        self.controller.loop.remove_watch_pipe(self.pipe_w)
        os.close(self.pipe_w)


@attr.s(cmp=False)
class ErrorReport(metaclass=urwid.MetaSignals):

    signals = ["changed"]

    controller = attr.ib()
    base = attr.ib()
    pr = attr.ib()
    state = attr.ib()
    _file = attr.ib()

    meta = attr.ib(default=attr.Factory(dict))
    uploader = attr.ib(default=None)

    @classmethod
    def new(cls, controller, kind):
        base = "{:.9f}.{}".format(time.time(), kind.name.lower())
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

    @classmethod
    def from_file(cls, controller, fpath):
        base = os.path.splitext(os.path.basename(fpath))[0]
        report = cls(
            controller, base, pr=apport.Report(date='???'),
            state=ErrorReportState.LOADING, file=open(fpath, 'rb'))
        try:
            fp = open(report.meta_path, 'r')
        except FileNotFoundError:
            pass
        else:
            with fp:
                report.meta = json.load(fp)
        return report

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
                self.state = ErrorReportState.ERROR_GENERATING
                log.exception("adding info to problem report failed")
            else:
                self.state = ErrorReportState.DONE
            self._file.close()
            self._file = None
            urwid.emit_signal(self, "changed")
        if wait:
            _bg_add_info()
        else:
            self.controller.run_in_bg(_bg_add_info, added_info)

    async def load(self):
        log.debug("loading report %s", self.base)
        # Load report from disk in background.
        try:
            await run_in_thread(self.pr.load, self._file)
        except Exception:
            log.exception("loading problem report failed")
            self.state = ErrorReportState.ERROR_LOADING
        else:
            log.debug("done loading report %s", self.base)
            self.state = ErrorReportState.DONE
        self._file.close()
        self._file = None
        urwid.emit_signal(self, "changed")

    def upload(self):
        log.debug("starting upload for %s", self.base)
        uploader = self.uploader = Upload(
            controller=self.controller, bytes_to_send=1)

        url = "https://daisy.ubuntu.com"
        if self.controller.opts.dry_run:
            url = "https://daisy.staging.ubuntu.com"

        chunk_size = 1024

        def chunk(data):
            for i in range(0, len(data), chunk_size):
                if uploader.cancelled:
                    log.debug("upload for %s cancelled", self.base)
                    return
                yield data[i:i+chunk_size]
                uploader._bg_update(uploader.bytes_sent + chunk_size)

        def _bg_upload():
            for_upload = {
                "Kind": self.kind.value
                }
            for k, v in self.pr.items():
                if len(v) < 1024 or k in {"Traceback", "ProcCpuinfoMinimal"}:
                    for_upload[k] = v
                else:
                    log.debug("dropping %s of length %s", k, len(v))
            if "CurtinLog" in self.pr:
                logtail = []
                for line in self.pr["CurtinLog"].splitlines():
                    logtail.append(line.strip())
                    while sum(map(len, logtail)) > 2048:
                        logtail.pop(0)
                for_upload["CurtinLogTail"] = "\n".join(logtail)
            data = bson.BSON().encode(for_upload)
            self.uploader._bg_update(0, len(data))
            headers = {
                'user-agent': 'subiquity/{}'.format(
                    os.environ.get("SNAP_VERSION", "SNAP_VERSION")),
                }
            response = requests.post(url, data=chunk(data), headers=headers)
            response.raise_for_status()
            return response.text.split()[0]

        def uploaded(fut):
            try:
                oops_id = fut.result()
            except requests.exceptions.RequestException:
                log.exception("upload for %s failed", self.base)
            else:
                log.debug("finished upload for %s, %r", self.base, oops_id)
                self.set_meta("oops-id", oops_id)
            uploader.stop()
            self.uploader = None
            urwid.emit_signal(self, 'changed')

        urwid.emit_signal(self, 'changed')
        uploader.start()
        self.controller.run_in_bg(_bg_upload, uploaded)

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

    def mark_seen(self):
        self.set_meta("seen", True)
        urwid.emit_signal(self, "changed")

    @property
    def kind(self):
        k = self.meta.get("kind", "UNKNOWN")
        return getattr(ErrorReportKind, k, ErrorReportKind.UNKNOWN)

    @property
    def seen(self):
        return self.meta.get("seen", False)

    @property
    def oops_id(self):
        return self.meta.get("oops-id")

    @property
    def persistent_details(self):
        """Return fs-label, path-on-fs to report."""
        # Not sure if this is more or less sane than shelling out to
        # findmnt(1).
        looking_for = os.path.abspath(
            os.path.normpath(self.controller.crash_directory))
        for line in open('/proc/self/mountinfo').readlines():
            parts = line.strip().split()
            if os.path.normpath(parts[4]) == looking_for:
                devname = parts[9]
                root = parts[3]
                break
        else:
            if self.controller.opts.dry_run:
                path = ('install-logs/2019-11-06.0/crash/' +
                        self.base +
                        '.crash')
                return "casper-rw", path
            return None, None
        import pyudev
        c = pyudev.Context()
        devs = list(c.list_devices(
            subsystem='block', DEVNAME=os.path.realpath(devname)))
        if not devs:
            return None, None
        label = devs[0].get('ID_FS_LABEL_ENC', '')
        return label, root[1:] + '/' + self.base + '.crash'


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
        # scan for pre-existing crash reports and start loading them
        # in the background
        self.scan_crash_dir()

    async def _load_reports(self, to_load):
        for report in to_load:
            await report.load()

    def scan_crash_dir(self):
        filenames = os.listdir(self.crash_directory)
        to_load = []
        for filename in sorted(filenames, reverse=True):
            base, ext = os.path.splitext(filename)
            if ext != ".crash":
                continue
            path = os.path.join(self.crash_directory, filename)
            r = ErrorReport.from_file(self, path)
            self.reports.append(r)
            to_load.append(r)
        schedule_task(self._load_reports(to_load))

    def create_report(self, kind):
        r = ErrorReport.new(self, kind)
        self.reports.insert(0, r)
        return r

    def start_ui(self):
        raise Skip

    def cancel(self):
        pass
