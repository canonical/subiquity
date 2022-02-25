# Copyright 2020 Canonical, Ltd.
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
import fcntl
import json
import logging
import os
import sys
import time
import traceback

import apport
import apport.crashdb
import apport.hookutils

import attr

import bson

import requests

import urwid

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )

from subiquity.common.types import (
    ErrorReportKind,
    ErrorReportRef,
    ErrorReportState,
    )


log = logging.getLogger('subiquity.common.errorreport')


@attr.s(eq=False)
class Upload(metaclass=urwid.MetaSignals):
    signals = ['progress']

    bytes_to_send = attr.ib()
    bytes_sent = attr.ib(default=0)
    pipe_r = attr.ib(default=None)
    pipe_w = attr.ib(default=None)
    cancelled = attr.ib(default=False)

    def start(self):
        self.pipe_r, self.pipe_w = os.pipe()
        fcntl.fcntl(self.pipe_r, fcntl.F_SETFL, os.O_NONBLOCK)
        asyncio.get_event_loop().add_reader(self.pipe_r, self._progress)

    def _progress(self):
        os.read(self.pipe_r, 4096)
        urwid.emit_signal(self, 'progress')

    def _bg_update(self, sent, to_send=None):
        self.bytes_sent = sent
        if to_send is not None:
            self.bytes_to_send = to_send
        os.write(self.pipe_w, b'x')

    def stop(self):
        asyncio.get_event_loop().remove_reader(self.pipe_r)
        os.close(self.pipe_w)
        os.close(self.pipe_r)


@attr.s(eq=False)
class ErrorReport(metaclass=urwid.MetaSignals):

    signals = ["changed"]

    reporter = attr.ib()
    base = attr.ib()
    pr = attr.ib()
    state: ErrorReportState = attr.ib()
    _file = attr.ib()
    _context = attr.ib()
    _info_task = attr.ib(default=None)

    meta = attr.ib(default=attr.Factory(dict))
    uploader = attr.ib(default=None)

    @classmethod
    def new(cls, reporter, kind):
        base = "{:.9f}.{}".format(time.time(), kind.name.lower())
        crash_file = open(
            os.path.join(reporter.crash_directory, base + ".crash"),
            'wb')

        pr = apport.Report('Bug')
        pr['CrashDB'] = repr(reporter.crashdb_spec)

        r = cls(
            reporter=reporter, base=base, pr=pr, file=crash_file,
            state=ErrorReportState.INCOMPLETE,
            context=reporter.context.child(base))
        r.set_meta("kind", kind.name)
        return r

    @classmethod
    def from_file(cls, reporter, fpath):
        base = os.path.splitext(os.path.basename(fpath))[0]
        report = cls(
            reporter, base, pr=apport.Report(date='???'),
            state=ErrorReportState.LOADING, file=open(fpath, 'rb'),
            context=reporter.context.child(base))
        try:
            fp = open(report.meta_path, 'r')
        except FileNotFoundError:
            pass
        else:
            with fp:
                report.meta = json.load(fp)
        return report

    def add_info(self, _bg_attach_hook, wait=False):
        def _bg_add_info():
            _bg_attach_hook()
            # Add basic info to report.
            self.pr.add_proc_info()
            self.pr.add_os_info()
            if not self.reporter.dry_run:
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

        async def add_info():
            with self._context.child("add_info") as context:
                try:
                    await run_in_thread(_bg_add_info)
                except Exception:
                    self.state = ErrorReportState.ERROR_GENERATING
                    log.exception("adding info to problem report failed")
                else:
                    context.description = "written to " + self.path
                    self.state = ErrorReportState.DONE
                self._file.close()
                self._file = None
                urwid.emit_signal(self, "changed")
        if wait:
            with self._context.child("add_info") as context:
                _bg_add_info()
                context.description = "written to " + self.path
        else:
            self._info_task = asyncio.get_event_loop().create_task(add_info())

    async def load(self):
        with self._context.child("load"):
            # Load report from disk in background.
            try:
                await run_in_thread(self.pr.load, self._file)
            except Exception:
                log.exception("loading problem report failed")
                self.state = ErrorReportState.ERROR_LOADING
            else:
                self.state = ErrorReportState.DONE
        self._file.close()
        self._file = None
        urwid.emit_signal(self, "changed")

    def upload(self):
        uploader = self.uploader = Upload(bytes_to_send=1)

        url = "https://daisy.ubuntu.com"
        if self.reporter.dry_run:
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
                if len(v) < 1024 or k in {
                        "InstallerLogInfo",
                        "Traceback",
                        "ProcCpuinfoMinimal",
                        }:
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

        async def upload():
            with self._context.child("upload") as context:
                try:
                    oops_id = await run_in_thread(_bg_upload)
                except requests.exceptions.RequestException:
                    log.exception("upload for %s failed", self.base)
                else:
                    self.set_meta("oops-id", oops_id)
                    context.description = oops_id
                uploader.stop()
                self.uploader = None
                urwid.emit_signal(self, 'changed')

        urwid.emit_signal(self, 'changed')
        uploader.start()

        schedule_task(upload())

    def _path_with_ext(self, ext):
        return os.path.join(
            self.reporter.crash_directory, self.base + '.' + ext)

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
            os.path.normpath(self.reporter.crash_directory))
        for line in open('/proc/self/mountinfo').readlines():
            parts = line.strip().split()
            if os.path.normpath(parts[4]) == looking_for:
                devname = parts[9]
                root = parts[3]
                break
        else:
            if self.reporter.dry_run:
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

    def ref(self):
        return ErrorReportRef(
            state=self.state,
            base=self.base,
            kind=self.kind,
            seen=self.seen,
            oops_id=self.oops_id,
            )


class ErrorReporter(object):

    def __init__(self, context, dry_run, root, client=None):
        self.context = context
        self.dry_run = dry_run
        self.crash_directory = os.path.join(root, 'var/crash')
        self.client = client

        self.reports = []
        self._reports_by_base = {}
        self._reports_by_exception = {}
        self.crashdb_spec = {
            'impl': 'launchpad',
            'project': 'subiquity',
            }
        if dry_run:
            self.crashdb_spec['launchpad_instance'] = 'staging'
        self._apport_data = []
        self._apport_files = []

    def load_reports(self):
        os.makedirs(self.crash_directory, exist_ok=True)
        filenames = os.listdir(self.crash_directory)
        to_load = []
        for filename in sorted(filenames, reverse=True):
            base, ext = os.path.splitext(filename)
            if ext != ".crash":
                continue
            if base not in self._reports_by_base:
                path = os.path.join(self.crash_directory, filename)
                r = ErrorReport.from_file(self, path)
                self.reports.append(r)
                self._reports_by_base[base] = r
                to_load.append(r)
        schedule_task(self._load_reports(to_load))

    async def _load_reports(self, to_load):
        for report in to_load:
            await report.load()

    def note_file_for_apport(self, key, path):
        self._apport_files.append((key, path))

    def note_data_for_apport(self, key, value):
        self._apport_data.append((key, value))

    def report_for_exc(self, exc):
        return self._reports_by_exception.get(exc)

    def make_apport_report(self, kind, thing, *, wait=False, exc=None, **kw):
        if not self.dry_run and not os.path.exists('/cdrom/.disk/info'):
            return None

        log.debug("generating crash report")
        os.makedirs(self.crash_directory, exist_ok=True)

        try:
            report = ErrorReport.new(self, kind)
            self.reports.insert(0, report)
            self._reports_by_base[report.base] = report
        except Exception:
            log.exception("creating crash report failed")
            return

        if exc is None:
            exc = sys.exc_info()[1]
        if exc is not None:
            report.pr["Title"] = "{} crashed with {}".format(
                thing, type(exc).__name__)
            tb = traceback.TracebackException.from_exception(exc)
            report.pr['Traceback'] = "".join(tb.format())
            self._reports_by_exception[exc] = report
        else:
            report.pr["Title"] = thing

        log.info(
            "saving crash report %r to %s", report.pr["Title"], report.path)

        apport_files = self._apport_files[:]
        apport_data = self._apport_data.copy()

        def _bg_attach_hook():
            # Attach any stuff other parts of the code think we should know
            # about.
            for key, path in apport_files:
                apport.hookutils.attach_file_if_exists(report.pr, path, key)
            for key, value in apport_data:
                report.pr[key] = value
            for key, value in kw.items():
                report.pr[key] = value

        report.add_info(_bg_attach_hook, wait)

        # In the fullness of time we should do the signature thing here.
        return report

    def get(self, error_ref):
        return self._reports_by_base.get(error_ref.base)

    async def get_wait(self, error_ref):
        report = self._reports_by_base.get(error_ref.base)
        if report is not None:
            return report

        loop = asyncio.get_event_loop()

        await self.client.errors.wait.GET(error_ref)

        path = os.path.join(
            self.crash_directory, error_ref.base + '.crash')
        report = ErrorReport.from_file(self, path)
        self.reports.insert(0, report)
        self._reports_by_base[error_ref.base] = report

        loop.call_soon(loop.create_task, report.load())

        return report
