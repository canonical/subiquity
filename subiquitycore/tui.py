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
import inspect
import logging
import yaml

import urwid

from subiquitycore.async_helpers import schedule_task
from subiquitycore.core import Application
from subiquitycore.palette import (
    PALETTE_COLOR,
    PALETTE_MONO,
    )
from subiquitycore.screen import make_screen
from subiquitycore.tuicontroller import Skip
from subiquitycore.ui.utils import LoadingDialog
from subiquitycore.ui.frame import SubiquityCoreUI
from subiquitycore.utils import arun_command

log = logging.getLogger('subiquitycore.tui')


def extend_dec_special_charmap():
    urwid.escape.DEC_SPECIAL_CHARMAP.update({
        ord('\N{BLACK RIGHT-POINTING SMALL TRIANGLE}'): '>',
        ord('\N{BLACK LEFT-POINTING SMALL TRIANGLE}'): '<',
        ord('\N{BLACK DOWN-POINTING SMALL TRIANGLE}'): 'v',
        ord('\N{BLACK UP-POINTING SMALL TRIANGLE}'): '^',
        ord('\N{check mark}'): '+',
        ord('\N{bullet}'): '*',
        ord('\N{lower half block}'): '=',
        ord('\N{upper half block}'): '=',
        ord('\N{FULL BLOCK}'): urwid.escape.DEC_SPECIAL_CHARMAP[
            ord('\N{BOX DRAWINGS LIGHT VERTICAL}')],
    })


# When waiting for something of unknown duration, block the UI for at
# most this long before showing an indication of progress.
MAX_BLOCK_TIME = 0.1
# If an indication of progress is shown, show it for at least this
# long to avoid excessive flicker in the UI.
MIN_SHOW_PROGRESS_TIME = 1.0


class TuiApplication(Application):

    make_ui = SubiquityCoreUI

    def __init__(self, opts):
        super().__init__(opts)
        self.ui = self.make_ui()

        self.answers = {}
        if opts.answers is not None:
            self.answers = yaml.safe_load(opts.answers.read())
            log.debug("Loaded answers %s", self.answers)
            if not opts.dry_run:
                open('/run/casper-no-prompt', 'w').close()

        # Set rich_mode to the opposite of what we want, so we can
        # call toggle_rich to get the right things set up.
        self.rich_mode = opts.run_on_serial
        self.urwid_loop = None
        self.cur_screen = None

    def run_command_in_foreground(self, cmd, before_hook=None, after_hook=None,
                                  **kw):
        screen = self.urwid_loop.screen

        async def _run():
            await arun_command(
                cmd, stdin=None, stdout=None, stderr=None, **kw)
            screen.start()
            if after_hook is not None:
                after_hook()

        screen.stop()
        urwid.emit_signal(
            screen, urwid.display_common.INPUT_DESCRIPTORS_CHANGED)
        if before_hook is not None:
            before_hook()
        schedule_task(_run())

    async def make_view_for_controller(self, new):
        new.context.enter("starting UI")
        if self.opts.screens and new.name not in self.opts.screens:
            raise Skip
        try:
            maybe_view = new.make_ui()
            if inspect.iscoroutine(maybe_view):
                view = await maybe_view
            else:
                view = maybe_view
        except Skip:
            new.context.exit("(skipped)")
            raise
        else:
            self.cur_screen = new
            return view

    async def _wait_with_indication(self, awaitable, show, hide=None):
        """Wait for something but tell the user if it takes a while.

        When waiting for something that can take an unknown length of
        time, we want to tell the user if it takes more than a moment
        (defined as MAX_BLOCK_TIME) but make sure that we display any
        indication for long enough that the UI is not flickering
        incomprehensibly (MIN_SHOW_PROGRESS_TIME).
        """
        min_show_task = None

        def _show():
            self.ui.block_input = False
            nonlocal min_show_task
            min_show_task = self.aio_loop.create_task(
                asyncio.sleep(MIN_SHOW_PROGRESS_TIME))
            show()

        self.ui.block_input = True
        show_handle = self.aio_loop.call_later(MAX_BLOCK_TIME, _show)
        try:
            result = await awaitable
        finally:
            if min_show_task:
                await min_show_task
                if hide is not None:
                    hide()
            else:
                self.ui.block_input = False
                show_handle.cancel()

        return result

    def show_progress(self):
        raise NotImplementedError

    async def wait_with_text_dialog(self, awaitable, message,
                                    *, can_cancel=False):
        ld = None

        task_to_cancel = None
        if can_cancel:
            if not isinstance(awaitable, asyncio.Task):
                async def w():
                    return await awaitable
                task_to_cancel = self.aio_loop.create_task(w())
            else:
                task_to_cancel = awaitable

        def show_load():
            nonlocal ld
            ld = LoadingDialog(
                self.ui.body, self.aio_loop, message, task_to_cancel)
            self.ui.body.show_overlay(ld, width=ld.width)

        def hide_load():
            ld.close()

        return await self._wait_with_indication(
            awaitable, show_load, hide_load)

    async def _move_screen(self, increment, coro):
        if coro is not None:
            await coro
        old, self.cur_screen = self.cur_screen, None
        if old is not None:
            old.context.exit("completed")
            old.end_ui()
        cur_index = self.controllers.index
        while True:
            self.controllers.index += increment
            if self.controllers.index < 0:
                self.controllers.index = cur_index
                return None
            if self.controllers.index >= len(self.controllers.instances):
                self.exit()
                return None
            new = self.controllers.cur
            try:
                return await self.make_view_for_controller(new)
            except Skip:
                log.debug("skipping screen %s", new.name)
                continue
            except Exception:
                self.controllers.index = cur_index
                raise
            else:
                return

    async def move_screen(self, increment, coro):
        view = await self._wait_with_indication(
            self._move_screen(increment, coro), self.show_progress)
        if view is not None:
            self.ui.set_body(view)

    def next_screen(self, coro=None):
        self.aio_loop.create_task(self.move_screen(1, coro))

    def prev_screen(self):
        self.aio_loop.create_task(self.move_screen(-1, None))

    def select_initial_screen(self):
        self.next_screen()

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

        def _run_script():
            log.debug("running %s", ss.scripts[0])
            exec(ss.scripts[0], ss.ns)
            if ss.waiting:
                return
            ss.scripts = ss.scripts[1:]
            if ss.scripts:
                self.aio_loop.call_soon(_run_script)

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

            def next():
                ss.waiting = False
                if func is not None:
                    func()
                if not ss.waiting:
                    ss.scripts = ss.scripts[1:]
                    if ss.scripts:
                        _run_script()
            self.aio_loop.call_later(delay, next)

        ss.ns['c'] = c
        ss.ns['wait'] = wait
        ss.ns['ui'] = self.ui

        self.aio_loop.call_later(0.06, _run_script)

    def toggle_rich(self):
        if self.rich_mode:
            urwid.util.set_encoding('ascii')
            new_palette = PALETTE_MONO
            self.rich_mode = False
        else:
            urwid.util.set_encoding('utf-8')
            new_palette = PALETTE_COLOR
            self.rich_mode = True
        urwid.CanvasCache.clear()
        self.urwid_loop.screen.register_palette(new_palette)
        self.urwid_loop.screen.clear()

    def unhandled_input(self, key):
        if self.opts.dry_run and key == 'ctrl x':
            self.exit()
        elif key == 'f3':
            self.urwid_loop.screen.clear()
        elif self.opts.run_on_serial and key in ['ctrl t', 'f4']:
            self.toggle_rich()

    def extra_urwid_loop_args(self):
        return {}

    def make_screen(self, inputf=None, outputf=None):
        return make_screen(self.opts.ascii, inputf, outputf)

    def start_urwid(self, input=None, output=None):
        screen = self.make_screen(input, output)
        screen.register_palette(PALETTE_COLOR)
        self.urwid_loop = urwid.MainLoop(
            self.ui, screen=screen,
            handle_mouse=False, pop_ups=True,
            unhandled_input=self.unhandled_input,
            event_loop=urwid.AsyncioEventLoop(loop=self.aio_loop),
            **self.extra_urwid_loop_args()
            )
        extend_dec_special_charmap()
        self.toggle_rich()
        self.urwid_loop.start()
        self.select_initial_screen()

    async def start(self, start_urwid=True):
        await super().start()
        if start_urwid:
            self.start_urwid()

    def run(self):
        if self.opts.scripts:
            self.run_scripts(self.opts.scripts)
        try:
            super().run()
        finally:
            if self.urwid_loop is not None:
                self.urwid_loop.stop()
