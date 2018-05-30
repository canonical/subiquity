import contextlib
import imp
import importlib
import mock
from unittest import TestCase


def builtin_module_name():
    options = ('builtins', '__builtin__')
    for name in options:
        try:
            imp.find_module(name)
        except ImportError:
            continue
        else:
            print('importing and returning: %s' % name)
            importlib.import_module(name)
            return name


@contextlib.contextmanager
def simple_mocked_open(content=None):
    if not content:
        content = ''
    m_open = mock.mock_open(read_data=content)
    mod_name = builtin_module_name()
    m_patch = '{}.open'.format(mod_name)
    with mock.patch(m_patch, m_open, create=True):
        yield m_open


class CiTestCase(TestCase):
    def add_patch(self, target, attr, **kwargs):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        if 'autospec' not in kwargs:
            kwargs['autospec'] = True
        m = mock.patch(target, **kwargs)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)
