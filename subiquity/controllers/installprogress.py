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

import copy
import fcntl
from http import server
import logging
import os
import shutil
import subprocess
import threading

from subiquitycore import utils
from subiquitycore.controller import BaseController

from subiquity.curtin import (
    curtin_install_cmd,
    curtin_write_network_config,
    curtin_write_postinst_config,
    curtin_write_storage_actions,
    )
from subiquity.models import InstallProgressModel
from subiquity.ui.views import ProgressView

log = logging.getLogger("subiquitycore.controller.installprogress")


class _Handler(server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/report":
            if self.server.crash_file is None:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'No crash report yet!\n')
            else:
                f = open(self.server.crash_file, 'rb')
                fs = os.fstat(f.fileno())
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(fs.st_size))
                self.send_header("Content-Disposition", 'attachment; filename="subiquity.crash"')
                self.end_headers()
                shutil.copyfileobj(f, self.wfile)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(("content of %s\n" % self.path).encode('utf-8'))

    def log_message(self, format, *args):
        log.debug(format, *args)

class BackgroundServer:
    def __init__(self, port, run_in_main_thread):
        self.port = port
        self.run_in_main_thread = run_in_main_thread
        self._server_thread = None

    def start(self):
        """Return URL to pass to curtin."""
        self._httpd = server.HTTPServer(("", self.port), _Handler)
        self._httpd.crash_file = None
        port = self._httpd.server_address[1]
        self._server_thread = threading.Thread(target=self._httpd.serve_forever)
        self._server_thread.setDaemon(True)
        self._server_thread.start()
        return "http://localhost:{}/".format(port)

    def stop(self):
        self._httpd.shutdown()
        self._server_thread.join()


class InstallState:
    NOT_STARTED = 0
    RUNNING_INSTALL = 1
    DONE_INSTALL = 2
    RUNNING_POSTINSTALL = 3
    DONE_POSTINSTALL = 4
    ERROR_INSTALL = -1
    ERROR_POSTINSTALL = -2

class InstallProgressController(BaseController):
    signals = [
        ('fs-config-complete',       'fs_config_complete'),
        ('identity-config-complete', 'identity_config_complete'),
        ('network-config-written',   'network_config_written'),
    ]

    root = '/var/log/installer'

    def __init__(self, common):
        super().__init__(common)
        self.model = InstallProgressModel()
        self.progress_view = None
        self.install_state = InstallState.NOT_STARTED
        self.postinstall_written = False
        self.tail_proc = None
        self.current_log_file = None
        self.server = BackgroundServer(0, self.call_from_thread)
        self.server.start()
        self.server_port = self.server._httpd.server_address[1]
        log.debug("listening on %s", self.server_port)
        if self.opts.dry_run:
            self.root = os.path.abspath('.subiquity')

    def network_config_written(self, path):
        curtin_write_network_config(self._curtin_config('network'), open(path).read())

    def fs_config_complete(self, actions):
        log.info("Rendering curtin config from user choices")
        curtin_write_storage_actions(self._curtin_config('storage'), actions)
        log.info("Rendering preserved config for post install")
        preserved_actions = copy.deepcopy(actions)
        for a in preserved_actions:
            a['preserve'] = True
        curtin_write_storage_actions(self._curtin_config('preserved-storage'), preserved_actions)
        self.curtin_start_install()

    def identity_config_complete(self, userinfo):
        curtin_write_postinst_config(self._curtin_config('postinstall'), userinfo)
        self.postinstall_written = True
        if self.install_state == InstallState.DONE_INSTALL:
            self.curtin_start_postinstall()

    def _curtin_config(self, config):
        return os.path.join(self.root, 'subiquity-config-{}.yaml'.format(config))

    def _curtin_logfile(self, stage):
        return os.path.join(self.root, 'subiquity-curtin-{}.log'.format(stage))

    def curtin_error(self):
        log.debug('curtin_error')
        title = ('An error occurred during installation')
        self.ui.set_header(title, 'Please report this error in Launchpad')
        self.ui.set_footer("An error has occurred.", 100)
        if self.progress_view is not None:
            self.progress_view.set_status(('info_error', "An error has occurred"))
            self.progress_view.show_error()
            self.run_in_bg(lambda :utils.run_command(['apport-cli', '--save=/tmp/crash', 'subiquity']),
                           lambda fut:self._apport_complete(fut, "/tmp/crash"))
        else:
            self.default()

    def _apport_complete(self, fut, filename):
        result = fut.result()
        if result['status'] > 0:
            log.debug("Error running apport:\nstdout:\n%s\nstderr:\n%s", result['output'], result['err'])
            self.progress_view.apport_status_text.set_text("Error running apport, see log for more.")
        else:
            self.server._httpd.crash_file = filename
            ips = []
            lines = ["Download the crash file from:"]
            net_model = self.controllers['Network'].model
            for dev in net_model.get_all_netdevs():
                ips.extend(dev.actual_global_ip_addresses)
            for ip in ips:
                if ip.version == 6:
                    ip = "[{}]".format(ip)
                lines.append("http://{}:{}/report".format(ip, self.server_port))
            lines.append("You can file a bug by running")
            lines.append("$ ubuntu-bug -c subiquity.crash")

            self.progress_view.apport_status_text.set_text("\n".join(lines))

    def run_command_logged(self, cmd, logfile_location):
        with open(logfile_location, 'wb', buffering=0) as logfile:
            log.debug("running %s", cmd)
            cp = subprocess.run(
                cmd, stdout=logfile, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            log.debug("completed %s", cmd)
        return cp.returncode

    def curtin_start_install(self):
        log.debug('Curtin Install: calling curtin with '
                  'storage/net/postinstall config')

        self.install_state = InstallState.RUNNING_INSTALL
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "bash", "-c",
                "{ i=0;while [ $i -le 25 ];do i=$((i+1)); echo install line $i; sleep 1; done; false; }"]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [self._curtin_config('storage'), self._curtin_config('network')]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        self.current_log_file = self._curtin_logfile('install')
        self.run_in_bg(lambda: self.run_command_logged(curtin_cmd, self.current_log_file), self.curtin_install_completed)

    def curtin_install_completed(self, fut):
        returncode = fut.result()
        log.debug('curtin_install: returncode: {}'.format(returncode))
        self.stop_tail_proc()
        if returncode > 0:
            self.install_state = InstallState.ERROR_INSTALL
            self.curtin_error()
            return
        self.current_log_file = None
        self.install_state = InstallState.DONE_INSTALL
        log.debug('After curtin install OK')
        if self.postinstall_written:
            self.curtin_start_postinstall()

    def cancel(self):
        pass

    def curtin_start_postinstall(self):
        log.debug('Curtin Post Install: calling curtin '
                  'with postinstall config')

        if not self.postinstall_written:
            log.error('Attempting to spawn curtin install without a config')
            raise Exception('AIEEE!')

        self.install_state = InstallState.RUNNING_POSTINSTALL
        self.current_log_file = self._curtin_logfile('postinstall')
        if self.progress_view is not None:
            self.progress_view.clear_log_tail()
            self.progress_view.set_status("Running postinstall step")
            self.start_tail_proc()
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "bash", "-c",
                "{ i=0;while [ $i -le 10 ];do i=$((i+1)); echo postinstall line $i; sleep 1; done; }"]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [self._curtin_config('postinstall'), self._curtin_config('preserved-storage')]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin postinstall cmd: {}'.format(curtin_cmd))
        self.run_in_bg(lambda: self.run_command_logged(curtin_cmd, self.current_log_file), self.curtin_postinstall_completed)

    def curtin_postinstall_completed(self, fut):
        returncode = fut.result()
        log.debug('curtin_postinstall: returncode: {}'.format(returncode))
        self.stop_tail_proc()
        if returncode > 0:
            self.install_state = InstallState.ERROR_POSTINSTALL
            self.curtin_error()
            return
        log.debug('After curtin postinstall OK')
        self.install_state = InstallState.DONE_POSTINSTALL
        self.ui.set_header("Installation complete!", "")
        self.ui.set_footer("", 100)
        self.progress_view.set_status("Finished install!")
        self.progress_view.show_complete()

    def update_log_tail(self):
        if self.tail_proc is None:
            return
        tail = self.tail_proc.stdout.read().decode('utf-8', 'replace')
        self.progress_view.add_log_tail(tail)

    def start_tail_proc(self):
        self.progress_view.clear_log_tail()
        tail_cmd = ['tail', '-n', '1000', '-F', self.current_log_file]
        log.debug('tail cmd: {}'.format(" ".join(tail_cmd)))
        self.tail_proc = utils.run_command_start(tail_cmd)
        stdout_fileno = self.tail_proc.stdout.fileno()
        fcntl.fcntl(
            stdout_fileno, fcntl.F_SETFL,
            fcntl.fcntl(stdout_fileno, fcntl.F_GETFL) | os.O_NONBLOCK)
        self.tail_watcher_handle = self.loop.watch_file(stdout_fileno, self.update_log_tail)

    def stop_tail_proc(self):
        if self.tail_proc is not None:
            self.loop.remove_watch_file(self.tail_watcher_handle)
            self.tail_proc.terminate()
            self.tail_proc = None

    def reboot(self):
        if self.opts.dry_run:
            log.debug('dry-run enabled, skipping reboot, quiting instead')
            self.signal.emit_signal('quit')
        else:
            utils.run_command(["/sbin/reboot"])

    def quit(self):
        if not self.opts.dry_run:
            utils.disable_subiquity()
        self.signal.emit_signal('quit')

    def default(self):
        log.debug('show_progress called')
        title = ("Installing system")
        excerpt = ("Please wait for the installation to finish.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 90)
        self.progress_view = ProgressView(self.model, self)
        if self.install_state < 0:
            self.curtin_error()
            self.ui.set_body(self.progress_view)
            return
        if self.install_state < InstallState.RUNNING_POSTINSTALL:
            self.progress_view.set_status("Running install step")
        else:
            self.progress_view.set_status("Running postinstall step")
        self.ui.set_body(self.progress_view)

        self.start_tail_proc()
