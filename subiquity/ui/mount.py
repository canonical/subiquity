
import re

from urwid import connect_signal, Padding, Pile, WidgetWrap

from subiquitycore.ui.interactive import Selector, StringEditor

common_mountpoints = [
    '/',
    '/boot',
    '/home',
    '/srv',
    '/usr',
    '/var',
    '/var/lib',
    ('other', True, None)
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

class MountSelector(WidgetWrap):
    def __init__(self):
        self._selector = Selector(opts=common_mountpoints)
        connect_signal(self._selector, 'select', self._select_mount)
        self._other = _MountEditor(caption='', edit_text='/')
        super().__init__(Pile([self._selector]))

    def _showhide_other(self, show):
        if show:
            self._w.contents.append((Padding(self._other, left=4), self._w.options('pack')))
        else:
            del self._w.contents[-1]

    def _select_mount(self, sender, value):
        if (self._selector.value == None) != (value == None):
            self._showhide_other(value==None)
        if value == None:
            self._w.focus_position = 1

    @property
    def value(self):
        if self._selector.value is None:
            return self._other.value
        else:
            return self._selector.value
