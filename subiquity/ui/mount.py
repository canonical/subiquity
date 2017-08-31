
import os
import re

import gettext
gettext.install('subiquity')

from urwid import connect_signal, Padding, Pile, WidgetWrap

from subiquitycore.ui.form import FormField
from subiquitycore.ui.interactive import Selector, StringEditor

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

class MountSelector(WidgetWrap):
    def __init__(self, model):
        mounts = model.get_mountpoint_to_devpath_mapping()
        opts = []
        first_opt = None
        max_len = max(map(len, common_mountpoints))
        for i, mnt in enumerate(common_mountpoints):
            devpath = mounts.get(mnt)
            if devpath is None:
                if first_opt is None:
                    first_opt = i
                opts.append((mnt, True, mnt))
            else:
                opts.append(("%-*s (%s)"%(max_len, mnt, devpath), False))
        if first_opt is None:
            first_opt = len(opts)
        opts.append((_('other'), True, OTHER))
        opts.append(('---', False)),
        opts.append((_('leave unmounted'), True, LEAVE_UNMOUNTED))
        self._selector = Selector(opts, first_opt)
        connect_signal(self._selector, 'select', self._select_mount)
        self._other = _MountEditor(edit_text='/')
        super().__init__(Pile([self._selector]))
        if self._selector.value is OTHER:
            # This can happen if all the common_mountpoints are in use.
            self._showhide_other(True)

    def _showhide_other(self, show):
        if show:
            self._w.contents.append((Padding(self._other, left=4), self._w.options('pack')))
        else:
            del self._w.contents[-1]

    def _select_mount(self, sender, value):
        if (self._selector.value == OTHER) != (value == OTHER):
            self._showhide_other(value==OTHER)
        if value == OTHER:
            self._w.focus_position = 1

    @property
    def value(self):
        if self._selector.value is LEAVE_UNMOUNTED:
            return None
        elif self._selector.value is OTHER:
            return self._other.value
        else:
            return self._selector.value


class MountField(FormField):

    def _make_widget(self, form):
        return MountSelector(form.model)

    def clean(self, value):
        if value is None:
            return value
        if not value.startswith('/'):
            raise ValueError('Does not start with /')
        return os.path.realpath(value)
