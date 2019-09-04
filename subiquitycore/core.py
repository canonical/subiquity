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

from concurrent import futures
import fcntl
import json
import logging
import os
import struct
import subprocess
import sys
import tty

import urwid
import yaml

from subiquitycore.controller import RepeatedController
from subiquitycore.signals import Signal
from subiquitycore.prober import Prober, ProberException
from subiquitycore.ui.frame import SubiquityCoreUI

log = logging.getLogger('subiquitycore.core')


class ApplicationError(Exception):
    """ Basecontroller exception """
    pass


class Skip(Exception):
    """Raise this from a controller's default method to skip a screen."""


# From uapi/linux/kd.h:
KDGKBTYPE = 0x4B33  # get keyboard type

GIO_CMAP = 0x4B70  # gets colour palette on VGA+
PIO_CMAP = 0x4B71  # sets colour palette on VGA+
UO_R, UO_G, UO_B = 0xe9, 0x54, 0x20

# /usr/include/linux/kd.h
K_RAW = 0x00
K_XLATE = 0x01
K_MEDIUMRAW = 0x02
K_UNICODE = 0x03
K_OFF = 0x04

KDGKBMODE = 0x4B44  # gets current keyboard mode
KDSKBMODE = 0x4B45  # sets current keyboard mode


class ISO_8613_3_Screen(urwid.raw_display.Screen):

    def __init__(self, _urwid_name_to_rgb):
        self._fg_to_rgb = _urwid_name_to_rgb.copy()
        self._fg_to_rgb['default'] = _urwid_name_to_rgb['light gray']
        self._bg_to_rgb = _urwid_name_to_rgb.copy()
        self._bg_to_rgb['default'] = _urwid_name_to_rgb['black']
        super().__init__()

    def _attrspec_to_escape(self, a):
        f_r, f_g, f_b = self._fg_to_rgb[a.foreground]
        b_r, b_g, b_b = self._bg_to_rgb[a.background]
        return "\x1b[38;2;{};{};{};48;2;{};{};{}m".format(f_r, f_g, f_b,
                                                          b_r, b_g, b_b)


def is_linux_tty():
    try:
        r = fcntl.ioctl(sys.stdout.fileno(), KDGKBTYPE, ' ')
    except IOError as e:
        log.debug("KDGKBTYPE failed %r", e)
        return False
    log.debug("KDGKBTYPE returned %r", r)
    return r == b'\x02'


def setup_screen(colors, styles):
    """Return a palette and screen to be passed to MainLoop.

    colors is a list of exactly 8 tuples (name, (r, g, b))

    styles is a list of tuples (stylename, fg_color, bg_color) where
    fg_color and bg_color are defined in 'colors'
    """
    # The part that makes this "fun" is that urwid insists on referring
    # to the basic colors by their "standard" names but we overwrite
    # these colors to mean different things.  So we convert styles into
    # an urwid palette by mapping the names in colors to the standard
    # name, and then either overwrite the first 8 colors to be the
    # colors from 'colors' (on the linux vt) or use a custom screen
    # class that displays maps the standard color name to the value
    # specified in colors using 24-bit control codes.
    if len(colors) != 8:
        raise Exception(
            "setup_screen must be passed a list of exactly 8 colors")
    urwid_8_names = (
        'black',
        'dark red',
        'dark green',
        'brown',
        'dark blue',
        'dark magenta',
        'dark cyan',
        'light gray',
    )
    urwid_name = dict(zip([c[0] for c in colors], urwid_8_names))

    urwid_palette = []
    for name, fg, bg in styles:
        urwid_palette.append((name, urwid_name[fg], urwid_name[bg]))

    if is_linux_tty():
        curpal = bytearray(16*3)
        fcntl.ioctl(sys.stdout.fileno(), GIO_CMAP, curpal)
        for i in range(8):
            for j in range(3):
                curpal[i*3+j] = colors[i][1][j]
        fcntl.ioctl(sys.stdout.fileno(), PIO_CMAP, curpal)
        return urwid.raw_display.Screen(), urwid_palette
    else:
        _urwid_name_to_rgb = {}
        for i, n in enumerate(urwid_8_names):
            _urwid_name_to_rgb[n] = colors[i][1]
        return ISO_8613_3_Screen(_urwid_name_to_rgb), urwid_palette


class KeyCodesFilter:
    """input_filter that can pass (medium) raw keycodes to the application

    See http://lct.sourceforge.net/lct/x60.html for terminology.

    Call enter_keycodes_mode()/exit_keycodes_mode() to switch into and
    out of keycodes mode. In keycodes mode, the only events passed to
    the application are "press $N" / "release $N" where $N is the
    keycode the user pressed or released.

    Much of this is cribbed from the source of the "showkeys" utility.
    """

    def __init__(self):
        self._fd = os.open("/proc/self/fd/0", os.O_RDWR)
        self.filtering = False

    def enter_keycodes_mode(self):
        log.debug("enter_keycodes_mode")
        self.filtering = True
        # Read the old keyboard mode (it will proably always be K_UNICODE but
        # well).
        o = bytearray(4)
        fcntl.ioctl(self._fd, KDGKBMODE, o)
        self._old_mode = struct.unpack('i', o)[0]
        # Set the keyboard mode to K_MEDIUMRAW, which causes the keyboard
        # driver in the kernel to pass us keycodes.
        log.debug("old mode was %s, setting mode to %s",
                  self._old_mode, K_MEDIUMRAW)
        fcntl.ioctl(self._fd, KDSKBMODE, K_MEDIUMRAW)

    def exit_keycodes_mode(self):
        log.debug("exit_keycodes_mode")
        self.filtering = False
        log.debug("setting mode back to %s", self._old_mode)
        fcntl.ioctl(self._fd, KDSKBMODE, self._old_mode)

    def filter(self, keys, codes):
        # Luckily urwid passes us the raw results from read() we can
        # turn into keycodes.
        if self.filtering:
            i = 0
            r = []
            n = len(codes)
            while i < len(codes):
                # This is straight from showkeys.c.
                if codes[i] & 0x80:
                    p = 'release '
                else:
                    p = 'press '
                if i + 2 < n and (codes[i] & 0x7f) == 0:
                    if (codes[i + 1] & 0x80) != 0:
                        if (codes[i + 2] & 0x80) != 0:
                            kc = (((codes[i + 1] & 0x7f) << 7) |
                                  (codes[i + 2] & 0x7f))
                            i += 3
                else:
                    kc = codes[i] & 0x7f
                    i += 1
                r.append(p + str(kc))
            return r
        else:
            return keys


class DummyKeycodesFilter:
    # A dummy implementation of the same interface as KeyCodesFilter
    # we can use when not running in a linux tty.

    def enter_keycodes_mode(self):
        pass

    def exit_keycodes_mode(self):
        pass

    def filter(self, keys, codes):
        return keys


class Application:

    # A concrete subclass must set project and controllers attributes, e.g.:
    #
    # project = "subiquity"
    # controllers = [
    #         "Welcome",
    #         "Network",
    #         "Filesystem",
    #         "Identity",
    #         "InstallProgress",
    # ]
    # The 'next-screen' and 'prev-screen' signals move through the list of
    # controllers in order, calling the default method on the controller
    # instance.

    make_ui = SubiquityCoreUI

    def __init__(self, opts):
        try:
            prober = Prober(opts)
        except ProberException as e:
            err = "Prober init failed: {}".format(e)
            log.exception(err)
            raise ApplicationError(err)

        self.ui = self.make_ui()
        self.opts = opts
        opts.project = self.project

        self.root = '/'
        if opts.dry_run:
            self.root = '.subiquity'
        self.state_dir = os.path.join(self.root, 'run', self.project)
        os.makedirs(os.path.join(self.state_dir, 'states'), exist_ok=True)

        self.answers = {}
        if opts.answers is not None:
            self.answers = yaml.safe_load(opts.answers.read())
            log.debug("Loaded answers %s", self.answers)
            if not opts.dry_run:
                open('/run/casper-no-prompt', 'w').close()

        if is_linux_tty():
            log.debug("is_linux_tty")
            self.input_filter = KeyCodesFilter()
        else:
            self.input_filter = DummyKeycodesFilter()

        self.scale_factor = float(
            os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "1"))
        self.updated = os.path.exists(os.path.join(self.state_dir, 'updating'))
        self.signal = Signal()
        self.prober = prober
        self.loop = None
        self.pool = futures.ThreadPoolExecutor(10)
        if opts.screens:
            self.controllers = [c for c in self.controllers
                                if c in opts.screens]
        else:
            self.controllers = self.controllers[:]
        self.ui.progress_completion = len(self.controllers)
        self.controller_instances = dict.fromkeys(self.controllers)
        self.controller_index = -1

    def run_in_bg(self, func, callback):
        """Run func() in a thread and call callback on UI thread.

        callback will be passed a concurrent.futures.Future containing
        the result of func(). The result of callback is discarded. An
        exception will crash the process so be careful!
        """
        fut = self.pool.submit(func)

        def in_main_thread(ignored):
            self.loop.remove_watch_pipe(pipe)
            os.close(pipe)
            callback(fut)

        pipe = self.loop.watch_pipe(in_main_thread)

        def in_random_thread(ignored):
            os.write(pipe, b'x')
        fut.add_done_callback(in_random_thread)

    def run_command_in_foreground(self, cmd, **kw):
        screen = self.loop.screen

        def run():
            subprocess.run(cmd, **kw)

        def restore(fut):
            screen.start()
            # Calling screen.start() sends the INPUT_DESCRIPTORS_CHANGED
            # signal. This calls _reset_input_descriptors() which calls
            # unhook_event_loop / hook_event_loop on the screen. But this all
            # happens before _started is set on the screen, so hook_event_loop
            # does not actually do anything -- and we end up not listening to
            # stdin, obviously a defective situation for a console
            # application. So send it again now the screen is started...
            urwid.emit_signal(
                screen, urwid.display_common.INPUT_DESCRIPTORS_CHANGED)
            tty.setraw(0)

        screen.stop()
        self.run_in_bg(run, restore)

    def _connect_base_signals(self):
        """ Connect signals used in the core controller
        """
        signals = []

        signals.append(('quit', self.exit))
        if self.opts.dry_run:
            signals.append(('control-x-quit', self.exit))
        signals.append(('refresh', self.redraw_screen))
        signals.append(('next-screen', self.next_screen))
        signals.append(('prev-screen', self.prev_screen))
        self.signal.connect_signals(signals)

        # Registers signals from each controller
        for controller_class in self.controller_instances.values():
            controller_class.register_signals()
        log.debug(self.signal)

    def save_state(self):
        if self.controller_index < 0:
            return
        cur_controller_name = self.controllers[self.controller_index]
        cur_controller = self.controller_instances[cur_controller_name]
        state_path = os.path.join(
            self.state_dir, 'states', cur_controller_name)
        with open(state_path, 'w') as fp:
            json.dump(cur_controller.serialize(), fp)

    def select_screen(self, index):
        self.controller_index = index
        self.ui.progress_current = index
        controller_name = self.controllers[self.controller_index]
        log.debug("moving to screen %s", controller_name)
        controller = self.controller_instances[controller_name]
        controller.default()
        state_path = os.path.join(self.state_dir, 'last-screen')
        with open(state_path, 'w') as fp:
            fp.write(controller_name)

    def next_screen(self, *args):
        self.save_state()
        while True:
            if self.controller_index == len(self.controllers) - 1:
                self.exit()
            try:
                self.select_screen(self.controller_index + 1)
            except Skip:
                controller_name = self.controllers[self.controller_index]
                log.debug("skipping screen %s", controller_name)
                continue
            else:
                return

    def prev_screen(self, *args):
        self.save_state()
        while True:
            if self.controller_index == 0:
                self.exit()
            try:
                self.select_screen(self.controller_index - 1)
            except Skip:
                controller_name = self.controllers[self.controller_index]
                log.debug("skipping screen %s", controller_name)
                continue
            else:
                return

# EventLoop -------------------------------------------------------------------
    def redraw_screen(self):
        if self.loop is not None:
            try:
                self.loop.draw_screen()
            except AssertionError as e:
                log.critical("Redraw screen error: {}".format(e))

    def exit(self):
        raise urwid.ExitMainLoop()

    def run_scripts(self, scripts):
        # run_scripts runs (or rather arranges to run, it's all async)
        # a series of python snippets in a helpful namespace. This is
        # all in aid of being able to test some part of the UI without
        # having to click the same buttons over and over again to get
        # the UI to the part you are working on.
        #
        # In the namespace are:
        #  * everything from view_helpers
        #  * wait, delay execution of subsequent scripts for a while
        #  * c, a function that finds a button and clicks it. uses
        #    wait, above to wait for the button to appear in case it
        #    takes a while.
        from subiquitycore.testing import view_helpers

        class ScriptState:
            def __init__(self):
                self.ns = view_helpers.__dict__.copy()
                self.waiting = False
                self.wait_count = 0
                self.scripts = scripts

        ss = ScriptState()

        def _run_script(*args):
            log.debug("running %s", ss.scripts[0])
            exec(ss.scripts[0], ss.ns)
            if ss.waiting:
                return
            ss.scripts = ss.scripts[1:]
            if ss.scripts:
                self.loop.set_alarm_in(0.01, _run_script)

        def c(pat):
            but = view_helpers.find_button_matching(self.ui, '.*' + pat + '.*')
            if not but:
                ss.wait_count += 1
                if ss.wait_count > 10:
                    raise Exception("no button found matching %r after"
                                    "waiting for 10 secs" % pat)
                wait(1, func=lambda: c(pat))
                return
            ss.wait_count = 0
            view_helpers.click(but)

        def wait(delay, func=None):
            ss.waiting = True

            def next(loop, user_data):
                ss.waiting = False
                if func is not None:
                    func()
                if not ss.waiting:
                    ss.scripts = ss.scripts[1:]
                    if ss.scripts:
                        _run_script()
            self.loop.set_alarm_in(delay, next)

        ss.ns['c'] = c
        ss.ns['wait'] = wait
        ss.ns['ui'] = self.ui

        self.loop.set_alarm_in(0.06, _run_script)

    def unhandled_input(self, key):
        if key == 'ctrl x':
            self.signal.emit_signal('control-x-quit')

    def run(self):
        if (self.opts.run_on_serial and
                os.ttyname(0) != "/dev/ttysclp0"):
            palette = self.STYLES_MONO
            screen = urwid.raw_display.Screen()
        else:
            screen, palette = setup_screen(self.COLORS, self.STYLES)

        self.loop = urwid.MainLoop(
            self.ui, palette=palette, screen=screen,
            handle_mouse=False, pop_ups=True,
            input_filter=self.input_filter.filter,
            unhandled_input=self.unhandled_input)

        log.debug("Running event loop: {}".format(
            self.loop.event_loop))
        self.base_model = self.make_model()
        try:
            if self.opts.scripts:
                self.run_scripts(self.opts.scripts)
            controllers_mod = __import__('%s.controllers' % self.project,
                                         None, None, [''])
            for i, k in enumerate(self.controllers):
                if self.controller_instances[k] is None:
                    log.debug("Importing controller: {}".format(k))
                    klass = getattr(controllers_mod, k+"Controller")
                    self.controller_instances[k] = klass(self)
                else:
                    count = 1
                    for k2 in self.controllers[:i]:
                        if k2 == k or k2.startswith(k + '-'):
                            count += 1
                    orig = self.controller_instances[k]
                    k += '-' + str(count)
                    self.controllers[i] = k
                    self.controller_instances[k] = RepeatedController(
                        orig, count)
            log.debug("*** %s", self.controller_instances)

            initial_controller_index = 0

            if self.updated:
                for k in self.controllers:
                    state_path = os.path.join(self.state_dir, 'states', k)
                    if not os.path.exists(state_path):
                        continue
                    with open(state_path) as fp:
                        self.controller_instances[k].deserialize(
                            json.load(fp))

                last_screen = None
                state_path = os.path.join(self.state_dir, 'last-screen')
                if os.path.exists(state_path):
                    with open(state_path) as fp:
                        last_screen = fp.read().strip()

                if last_screen in self.controllers:
                    initial_controller_index = self.controllers.index(
                        last_screen)

            def select_initial_screen(loop, index):
                try:
                    self.select_screen(index)
                except Skip:
                    self.next_screen()

            self.loop.set_alarm_in(
                0.00, lambda loop, ud: tty.setraw(0))
            self.loop.set_alarm_in(
                0.05, select_initial_screen, initial_controller_index)
            self._connect_base_signals()

            for k in self.controllers:
                self.controller_instances[k].start()

            self.loop.run()
        except Exception:
            log.exception("Exception in controller.run():")
            raise
        finally:
            # concurrent.futures.ThreadPoolExecutor tries to join all
            # threads before exiting. We don't want that and this
            # ghastly hack prevents it.
            from concurrent.futures import thread
            thread._threads_queues = {}
