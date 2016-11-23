
import testtools
import argparse
import logging
from mock import patch
from subiquitycore.prober import Prober
from subiquitycore.tests import fakes

from console_conf.core import ConsoleConf

class TestCore(testtools.TestCase):

    def setUp(self):
        super(TestCore, self).setUp()
        logging.disable(logging.CRITICAL)
        self.make_mock()

    # mocking the reading of the fake data saves on IO
    @patch.object(Prober, '_load_machine_config')
    @patch.object(Prober, 'get_storage')
    def make_mock(self, _get_storage, _load_machine_config):
        _get_storage.return_value = fakes.FAKE_MACHINE_STORAGE_DATA
        _load_machine_config.return_value = fakes.FAKE_MACHINE_JSON_DATA
        self.opts = argparse.Namespace()
        self.opts.machine_config = fakes.FAKE_MACHINE_JSON
        self.opts.dry_run = True
        self.prober = Prober(self.opts)
        self.storage = fakes.FAKE_MACHINE_STORAGE_DATA
        self.cf = ConsoleConf(self.prober, self.opts)

    def test_projectname(self):
        self.assertEquals("console_conf", self.cf.project)

    def test_controllers(self):
        self.assertEquals(len(self.cf.controllers), 3)
        self.assertIn("Welcome", self.cf.controllers)
        self.assertIn("Network", self.cf.controllers)
        self.assertIn("Identity", self.cf.controllers)
