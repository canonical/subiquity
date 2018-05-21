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

"""An abstraction for running a sequence of actions in the background.

The API is not exactly perfect, a bit object-happy with observers and
watchers and stuff all over the place and these 'stage' labels I am not
really sure make sense but well. It works!

Example usage:

class watcher(TaskWatcher):
    def __init__(self, controller, view):
        self.controller = controller
        self.view = view
    def task_complete(self, stage):
        self.view.progress_bar.advance()
    def tasks_finished(self):
        self.controller.done()
    def task_error(self, stage, info):
        self.view.show_error(stage, info)
tasks = [
    ('one', PythonSleep(5)),
    ('two', BackgroundTask(['sleep', '5'])),
]
ts = TaskSequence(self.run_in_bg, tasks, watcher)
ts.run()

"""

from abc import ABC, abstractmethod
import logging
import os
import select
import subprocess
import sys

from subiquitycore.utils import start_command

log = logging.getLogger('subiquitycore.tasksequence')


class BackgroundTask(ABC):
    """Something that runs without blocking the UI."""

    @abstractmethod
    def start(self):
        """Start the task.

        This is called on the UI thread, so must not block.
        """

    @abstractmethod
    def _bg_run(self):
        """Run the task.

        This is called on an arbitrary thread so don't do UI stuff!
        """

    @abstractmethod
    def end(self, observer, fut):
        """Call task_succeeded or task_failed on observer.

        This is called on the UI thread.

        fut is a concurrent.futures.Future holding the result of running
        run.

        TaskSequence doesn't interpret the return value of _bg_run at
        all, it's up to the task to determine whether True means success
        or an exception means failure or whatever (although *this*
        method raising an exception means failure so you don't have to
        catch an exception raised by fut.result() unless you want to
        handle that specially).
        """


class CancelableTask(BackgroundTask):
    """Something that runs without blocking the UI and can be canceled."""

    @abstractmethod
    def cancel(self):
        """Abort the task.

        Any calls to task_succeeded or task_failed on the observer will
        be ignored after this point so it doesn't really matter what run
        returns after this is called.
        """


class PythonSleep(CancelableTask):
    """A task that just waits for a while. Mostly an example."""

    def __init__(self, duration):
        self.duration = duration
        # Create a pipe that we will select on in a background thread
        # to see if we have been canceled.
        self.cancel_r, self.cancel_w = os.pipe()

    def __repr__(self):
        return 'PythonSleep(%r)'%(self.duration,)

    def start(self):
        pass

    def _bg_run(self):
        # Wait for the requested duration or cancelation, whichever
        # came first.
        select.select([self.cancel_r], [], [], self.duration)
        os.close(self.cancel_r)
        os.close(self.cancel_w)
        # The return value of _bg_run is ignored if we are canceled,
        # and there's no other way to fail so just return.

    def end(self, observer, fut):
        # Call fut.result() to cater for the case that _bg_run somehow managed to raise an exception.
        fut.result()
        # Call task_succeeded() because if we got here, we weren't canceled.
        observer.task_succeeded()

    def cancel(self):
        os.write(self.cancel_w, b'x')


class BackgroundProcess(CancelableTask):

    def __init__(self, cmd):
        self.cmd = cmd
        self.proc = None

    def __repr__(self):
        return 'BackgroundProcess(%r)'%(self.cmd,)

    def start(self):
        self.proc = start_command(self.cmd)

    def _bg_run(self):
        stdout, stderr = self.proc.communicate()
        cp = subprocess.CompletedProcess(
            self.proc.args, self.proc.returncode, stdout, stderr)
        self.proc = None
        return cp

    def end(self, observer, fut):
        cp = fut.result()
        if cp.returncode == 0:
            observer.task_succeeded()
        else:
            raise subprocess.CalledProcessError(
                cp.returncode, cp.args, output=cp.stdout, stderr=cp.stderr)

    def cancel(self):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
        except ProcessLookupError:
            pass # It's OK if the process has already terminated.


class TaskWatcher(ABC):
    @abstractmethod
    def task_complete(self, stage):
        """A task completed sucessfully."""

    @abstractmethod
    def tasks_finished(self):
        """All tasks completed sucessfully."""

    @abstractmethod
    def task_error(self, stage, info):
        """A task failed."""


class TaskSequence:
    """A sequence of tasks to run in the background."""

    def __init__(self, run_in_bg, tasks, watcher):
        assert isinstance(watcher, TaskWatcher)
        self.run_in_bg = run_in_bg
        self.tasks = tasks
        self.watcher = watcher
        self.canceled = False
        self.stage = None
        self.curtask = None
        self.task_complete_or_failed_called = False

    def run(self):
        self._run1()

    def cancel(self):
        if self.curtask is not None and isinstance(self.curtask, CancelableTask):
            log.debug("canceling %s", self.curtask)
            self.curtask.cancel()
        self.canceled = True

    def _run1(self):
        self.stage, self.curtask = self.tasks[0]
        self.tasks = self.tasks[1:]
        log.debug('running %s for stage %s', self.curtask, self.stage)
        self.curtask.start()
        self.run_in_bg(self.curtask._bg_run, self._call_end)

    def _call_end(self, fut):
        log.exception("%s ended", self.stage)
        if self.canceled:
            return
        self.task_complete_or_failed_called = False
        try:
            self.curtask.end(self, fut)
        except:
            log.exception("%s failed", self.stage)
            self.task_failed(sys.exc_info())
        if not self.task_complete_or_failed_called:
            raise RuntimeError("{} {}.end did not call task_complete or task_failed".format(self.stage, self.curtask))

    def task_succeeded(self):
        self.task_complete_or_failed_called = True
        self.watcher.task_complete(self.stage)
        if len(self.tasks) == 0:
            self.watcher.tasks_finished()
        else:
            self._run1()

    def task_failed(self, info=None):
        self.task_complete_or_failed_called = True
        self.watcher.task_error(self.stage, info)
