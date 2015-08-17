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

import logging
import urwid
import urwid.curses_display
import subprocess
from subiquity.signals import Signal
from subiquity.palette import STYLES, STYLES_MONO
from subiquity.curtin import (curtin_write_storage_actions,
                              curtin_write_postinst_config)

# Modes import ----------------------------------------------------------------
from subiquity.models import (WelcomeModel, NetworkModel, InstallpathModel,
                              FilesystemModel)
from subiquity.ui.views import (WelcomeView, NetworkView, InstallpathView,
                                DiskPartitionView, AddPartitionView,
                                FilesystemView, ProgressView, ProgressOutput)
from subiquity.ui.dummy import DummyView


BIOS_GRUB_SIZE_BYTES = 2 * 1024 * 1024   # 2MiB
log = logging.getLogger('subiquity.core')


class CoreControllerError(Exception):
    """ Basecontroller exception """
    pass


class Controller:
    def __init__(self, ui, opts):
        self.ui = ui
        self.opts = opts
        self.models = {
            "welcome": WelcomeModel(),
            "network": NetworkModel(),
            "installpath": InstallpathModel(),
            "filesystem": FilesystemModel()
        }
        self.signal = Signal()
        # self.signal.register_signals()
        self._connect_signals()

    def _connect_signals(self):
        """ Connect signals used in the core controller
        """
        signals = []

        # Add quit signal
        signals.append(('quit', self.exit))

        # Pull signals emitted from welcome path selections
        for model, model_class in self.models.items():
            for name, sig, cb in model_class.get_signals():
                signals.append((sig, getattr(self, cb)))

        self.signal.connect_signals(signals)
        log.debug(self.signal)

# EventLoop -------------------------------------------------------------------
    def redraw_screen(self):
        if hasattr(self, 'loop'):
            try:
                self.loop.draw_screen()
            except AssertionError as e:
                log.critical("Redraw screen error: {}".format(e))

    def set_alarm_in(self, interval, cb):
        self.loop.set_alarm_in(interval, cb)
        return

    def update(self, *args, **kwds):
        """ Update loop """
        pass

    def exit(self):
        raise urwid.ExitMainLoop()

    def header_hotkeys(self, key):
        if key in ['q', 'Q', 'ctrl c']:
            self.exit()

    def run(self):
        if not hasattr(self, 'loop'):
            palette = STYLES
            additional_opts = {
                'screen': urwid.raw_display.Screen(),
                'unhandled_input': self.header_hotkeys,
                'handle_mouse': False
            }
            if self.opts.run_on_serial:
                palette = STYLES_MONO
                additional_opts['screen'] = urwid.curses_display.Screen()
            else:
                additional_opts['screen'].set_terminal_properties(colors=256)
                additional_opts['screen'].reset_default_terminal_palette()

            self.loop = urwid.MainLoop(
                self.ui, palette, **additional_opts)

        try:
            self.set_alarm_in(0.05, self.welcome)
            self.install_progress_fd = self.loop.watch_pipe(
                self.install_progress_status)
            self.loop.run()
        except:
            log.exception("Exception in controller.run():")
            raise

# Base UI Actions -------------------------------------------------------------
    def set_body(self, w):
        self.ui.set_body(w)
        self.redraw_screen()

    def set_header(self, title=None, excerpt=None):
        self.ui.set_header(title, excerpt)
        self.redraw_screen()

    def set_footer(self, message):
        self.ui.set_footer(message)
        self.redraw_screen()

# Modes ----------------------------------------------------------------------
    # Welcome -----------------------------------------------------------------
    def welcome(self, *args, **kwargs):
        title = "Wilkommen! Bienvenue! Welcome! Zdrastvutie! Welkom!"
        excerpt = "Please choose your preferred language"
        footer = ("Use UP, DOWN arrow keys, and ENTER, to "
                  "select your language.")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        view = WelcomeView(self.models['welcome'], self.signal)
        self.ui.set_body(view)

    # InstallPath -------------------------------------------------------------
    def installpath(self):
        title = "15.10"
        excerpt = ("Welcome to Ubuntu! The world's favourite platform "
                   "for clouds, clusters and amazing internet things. "
                   "This is the installer for Ubuntu on servers and "
                   "internet devices.")
        footer = ("Use UP, DOWN arrow keys, and ENTER, to "
                  "navigate options")

        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(InstallpathView(self.models["installpath"],
                                         self.signal))

    def install_ubuntu(self):
        log.debug("Installing Ubuntu path chosen.")
        self.signal.emit_signal('network:show')

    def install_maas_region_server(self):
        self.ui.set_body(DummyView(self.signal))

    def install_maas_cluster_server(self):
        self.ui.set_body(DummyView(self.signal))

    def test_media(self):
        self.ui.set_body(DummyView(self.signal))

    def test_memory(self):
        self.ui.set_body(DummyView(self.signal))

    # Network -----------------------------------------------------------------
    def network(self):
        title = "Network connections"
        excerpt = ("Configure at least the main interface this server will "
                   "use to talk to other machines, and preferably provide "
                   "sufficient access for updates.")
        footer = ("Additional networking info here")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(NetworkView(self.models["network"], self.signal))

    def set_default_route(self):
        self.ui.set_body(DummyView(self.signal))

    def bond_interfaces(self):
        self.ui.set_body(DummyView(self.signal))

    def install_network_driver(self):
        self.ui.set_body(DummyView(self.signal))

    # Filesystem --------------------------------------------------------------
    def filesystem(self, reset=False):
        # FIXME: Is this the best way to zero out this list for a reset?
        if reset:
            log.info("Resetting Filesystem model")
            self.models["filesystem"].reset()

        title = "Filesystem setup"
        footer = ("Select available disks to format and mount")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        self.ui.set_body(FilesystemView(self.models["filesystem"],
                                        self.signal))

    def filesystem_handler(self, reset=False, actions=None):
        if actions is None and reset is False:
            urwid.emit_signal(self.signal, 'network:show')

        log.info("Rendering curtin config from user choices")
        curtin_write_storage_actions(actions=actions)
        log.info("Generating post-install config")
        curtin_write_postinst_config()
        self.install_progress()

    # Filesystem/Disk partition -----------------------------------------------
    def disk_partition(self, disk):
        log.debug("In disk partition view, using {} as the disk.".format(disk))
        title = ("Partition, format, and mount {}".format(disk))
        footer = ("Partition the disk, or format the entire device "
                  "without partitions.")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        dp_view = DiskPartitionView(self.models["filesystem"],
                                    self.signal,
                                    disk)

        self.ui.set_body(dp_view)

    def disk_partition_handler(self, spec=None):
        log.debug("Disk partition: {}".format(spec))
        if spec is None:
            urwid.emit_signal(self.signal, 'filesystem:show', [])
        urwid.emit_signal(self.signal, 'filesystem:show-disk-partition', [])

    def add_disk_partition(self, disk):
        log.debug("Adding partition to {}".format(disk))
        footer = ("Select whole disk, or partition, to format and mount.")
        self.ui.set_footer(footer)
        adp_view = AddPartitionView(self.models["filesystem"],
                                    self.signal,
                                    disk)
        self.ui.set_body(adp_view)

    def add_disk_partition_handler(self, disk, spec):
        current_disk = self.models["filesystem"].get_disk(disk)

        ''' create a gpt boot partition if one doesn't exist '''
        if current_disk.parttype == 'gpt' and \
           len(current_disk.disk.partitions) == 0:
            log.debug('Adding grub_bios gpt partition first')
            current_disk.add_partition(partnum=1,
                                       size=BIOS_GRUB_SIZE_BYTES,
                                       fstype=None,
                                       flag='bios_grub')

        if spec["fstype"] in ["swap"]:
            current_disk.add_partition(partnum=spec["partnum"],
                                       size=spec["bytes"],
                                       fstype=spec["fstype"])
        else:
            current_disk.add_partition(partnum=spec["partnum"],
                                       size=spec["bytes"],
                                       fstype=spec["fstype"],
                                       mountpoint=spec["mountpoint"])
        log.debug("FS Table: {}".format(current_disk.get_fs_table()))
        self.signal.emit_signal('filesystem:show-disk-partition', disk)

    def connect_iscsi_disk(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def connect_ceph_disk(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def create_volume_group(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def create_raid(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def setup_bcache(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def add_first_gpt_partition(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def create_swap_entire_device(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    # Progress View -----------------------------------------------------------
    def install_progress(self):
        title = ("Installing system")
        excerpt = ("Please wait for the installation "
                   "to finish before rebooting.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        if self.opts.dry_run:
            log.debug("Filesystem: this is a dry-run")
            banner = [
                "**** DRY_RUN ****",
                "NOT calling:"
                "subprocess.check_call(/usr/local/bin/curtin_wrap.sh)"
                "",
                "",
                "Press (Q) to Quit."
            ]
            self.progress_output_w = ProgressOutput("\n".join(banner))
        else:
            log.debug("filesystem: this is the *real* thing")
            subprocess.Popen(["/usr/local/bin/curtin_wrap.sh"],
                             stdout=self.install_progress_fd,
                             bufsize=1,
                             universal_newlines=True)
            self.progress_output_w = ProgressOutput("Wait for it...\n\n")
        self.ui.set_body(ProgressView(self.signal, self.progress_output_w))

    def install_progress_status(self, data):
        self.progress_output_w.set_text(data)
