
import re

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import FormField
from subiquitycore.ui.interactive import Selector, StringEditor
from subiquitycore.ui.utils import Color


common_mountpoints = [
    '/',
    '/boot',
    '/home',
    '/srv',
    '/usr',
    '/var',
    '/var/lib',
    ]


class _MountEditor(StringEditor):
    """ Mountpoint input prompt with input rules
    """

    def keypress(self, size, key):
        ''' restrict what chars we allow for mountpoints '''

        mountpoint = r'[a-zA-Z0-9_/\.\-]'
        if re.match(mountpoint, key) is None:
            return False

        return super().keypress(size, key)


OTHER = object()
LEAVE_UNMOUNTED = object()

suitable_mountpoints_for_existing_fs = [
    '/home',
    '/srv',
    OTHER,
    LEAVE_UNMOUNTED,
    ]


class MountSelector(WidgetWrap):

    signals = ['change']

    def __init__(self, mountpoints):
        opts = []
        first_opt = None
        for i, mnt in enumerate(common_mountpoints):
            if mnt not in mountpoints:
                if first_opt is None:
                    first_opt = i
                opts.append((mnt, True, mnt))
            else:
                opts.append((mnt, False))
        if first_opt is None:
            first_opt = len(opts)
        opts.append((_('Other'), True, OTHER))
        opts.append(('---', False)),
        opts.append((_('Leave unmounted'), True, LEAVE_UNMOUNTED))
        self._selector = Selector(opts, first_opt)
        connect_signal(self._selector, 'select', self._select_mount)
        self._other = _MountEditor()
        super().__init__(Pile([self._selector]))
        self._other_showing = False
        if self._selector.value is OTHER:
            # This can happen if all the common_mountpoints are in use.
            self._showhide_other(True)

    def disable_unsuitable_mountpoints_for_existing_fs(self):
        for opt in self._selector._options:
            if opt.value is not None:
                opt.enabled = opt.value in suitable_mountpoints_for_existing_fs

    def enable_common_mountpoints(self):
        for opt in self._selector._options:
            if isinstance(opt.value, str):
                opt.enabled = opt.value in common_mountpoints

    def _showhide_other(self, show):
        if show and not self._other_showing:
            self._w.contents.append(
                (Columns([(1, Text("/")), Color.string_input(self._other)]),
                 self._w.options('pack')))
            self._other_showing = True
        elif not show and self._other_showing:
            del self._w.contents[-1]
            self._other_showing = False

    def _select_mount(self, sender, value):
        self._showhide_other(value == OTHER)
        if value == OTHER:
            self._w.focus_position = 1
            value = "/" + self._other.value
        self._emit('change', value)

    @property
    def value(self):
        if self._selector.value is LEAVE_UNMOUNTED:
            return None
        elif self._selector.value is OTHER:
            return "/" + self._other.value
        else:
            return self._selector.value

    @value.setter
    def value(self, val):
        opt = self._selector.option_by_value(val)
        if val is None:
            self._selector.value = LEAVE_UNMOUNTED
            self._showhide_other(False)
        elif opt is not None and opt.enabled:
            self._selector.value = val
            self._showhide_other(False)
        else:
            self._selector.value = OTHER
            self._showhide_other(True)
            if not val.startswith('/'):
                raise ValueError("%s does not start with /", val)
            self._other.value = val[1:]


class MountField(FormField):

    takes_default_style = False

    def _make_widget(self, form):
        return MountSelector(form.mountpoints)
