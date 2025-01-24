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

import asyncio
import concurrent.futures
import logging
from typing import Optional

log = logging.getLogger("subiquitycore.async_helpers")


def _done(fut):
    try:
        fut.result()
    except asyncio.CancelledError:
        pass


def schedule_task(coro, propagate_errors=True):
    loop = asyncio.get_running_loop()
    if asyncio.iscoroutine(coro):
        task = asyncio.Task(coro)
    else:
        task = coro
    if propagate_errors:
        task.add_done_callback(_done)
    loop.call_soon(asyncio.ensure_future, task)
    return task


# Collection of tasks that we want to fire and forget.
# Keeping a reference to all background tasks ensures that the tasks don't get
# garbage collected before they are done.
# https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
background_tasks = set()


def run_bg_task(coro, *args, **kwargs) -> None:
    """Run a background task in a fire-and-forget style."""
    task = asyncio.create_task(coro, *args, **kwargs)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def run_in_thread(func, *args):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, func, *args)
    except concurrent.futures.CancelledError:
        raise asyncio.CancelledError


class TaskAlreadyRunningError(Exception):
    """Used to let callers know that a task hasn't been started due to
    cancel_restart == False and the task already running."""

    pass


class SingleInstanceTask:
    def __init__(self, func, propagate_errors=True, cancel_restart=True):
        self.func = func
        self.propagate_errors = propagate_errors
        self.task_created = asyncio.Event()
        self.task = None
        # if True, allow subsequent start calls to cancel a running task
        # raises TaskAlreadyRunningError if we skip starting the task.
        self.cancel_restart = cancel_restart

    async def _start(self, old):
        if old is not None:
            old.cancel()
            try:
                await old
            except BaseException:
                pass
        schedule_task(self.task, self.propagate_errors)

    async def start(self, *args, **kw):
        await self.start_sync(*args, **kw)
        return self.task

    def start_sync(self, *args, **kw):
        if not self.cancel_restart:
            if self.task is not None and not self.task.done():
                raise TaskAlreadyRunningError(
                    "Skipping invocation of task - already running"
                )
        old = self.task
        coro = self.func(*args, **kw)
        if asyncio.iscoroutine(coro):
            self.task = asyncio.Task(coro)
        else:
            self.task = coro
        self.task_created.set()
        return schedule_task(self._start(old))

    async def wait(self):
        await self.task_created.wait()
        while True:
            try:
                return await self.task
            except asyncio.CancelledError:
                pass

    def done(self):
        if self.task is None:
            return False
        return self.task.done()


def exclusive(coroutine_function):
    """Can be used to decorate a coroutine function that we do not want to run
    multiple times concurrently. It uses a lock internally.
    If the caller needs to know when the decorated coroutine starts executing
    (i.e., when it has acquired the exclusive lock), they can pass an
    asyncio.Event as the "started_event" keyword-only argument.
    """
    lock = asyncio.Lock()

    async def wrapped(*args, started_event: Optional[asyncio.Event] = None, **kwargs):
        async with lock:
            if started_event is not None:
                started_event.set()

            return await coroutine_function(*args, **kwargs)

    return wrapped
