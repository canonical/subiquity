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
import enum
import functools
import inspect


class Status(enum.Enum):
    SUCCESS = enum.auto()
    FAIL = enum.auto()
    WARN = enum.auto()


class Context:
    """Class to report when things start and finish.

    The expected way to use this is something like:

    with somecontext.child("operation"):
        await long_running_operation()

    but you can also call .enter() and .exit() if use as a context
    manager isn't possible.

    start and finish events are reported via the report_start_event and
    report_finish_event methods on app.

    You can override the message shown on exit by passing it to the .exit
    method or by assigning to description:

    with somecontext.child("operation") as context:
        result = await long_running_operation()
        context.description = "result was {}".format(result)
    """

    def __init__(self, app, name, description, parent, level, childlevel=None):
        self.app = app
        self.name = name
        self.description = description
        self.parent = parent
        self.level = level
        if childlevel is None:
            childlevel = level
        self.childlevel = childlevel
        self.data = {}

    @classmethod
    def new(cls, app):
        return cls(app, app.project, "", None, "INFO")

    def child(self, name, description="", level=None, childlevel=None):
        if level is None:
            level = self.childlevel
        return type(self)(self.app, name, description, self, level, childlevel)

    def full_name(self):
        c = self
        names = []
        while c is not None:
            names.append(c.name)
            c = c.parent
        return '/'.join(reversed(names))

    def enter(self, description=None):
        if description is None:
            description = self.description
        self.app.report_start_event(self, description)

    def exit(self, description=None, result=Status.SUCCESS):
        if description is None:
            description = self.description
        self.app.report_finish_event(self, description, result)

    def __enter__(self):
        self.enter()
        return self

    def __exit__(self, exc, value, tb):
        if exc is not None:
            result = Status.FAIL
            if isinstance(value, asyncio.CancelledError):
                description = "cancelled"
            else:
                description = str(value)
        else:
            result = Status.SUCCESS
            description = None
        self.exit(description, result)

    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        c = self
        while c is not None:
            if key in c.data:
                return c.data[key]
            c = c.parent
        return default


def with_context(name=None, description="", **context_kw):
    def decorate(meth):
        nonlocal name
        if name is None:
            name = meth.__name__

        def convargs(self, kw):
            context = kw.get('context')
            if context is None:
                context = self.context
            kw['context'] = context.child(
                name=name.format(**kw),
                description=description.format(**kw),
                **context_kw)
            return kw

        @functools.wraps(meth)
        def decorated_sync(self, **kw):
            kw = convargs(self, kw)
            with kw['context']:
                return meth(self, **kw)

        @functools.wraps(meth)
        async def decorated_async(self, **kw):
            kw = convargs(self, kw)
            with kw['context']:
                return await meth(self, **kw)

        if inspect.iscoroutinefunction(meth):
            return decorated_async
        else:
            return decorated_sync
    return decorate
