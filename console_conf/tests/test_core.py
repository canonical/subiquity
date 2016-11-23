
from subiquitycore.prober import Prober
from subiquitycore.tests.utils import TestCase

from console_conf.core import ConsoleConf

class TestCore(TestCase):

    def setUp(self):
        super(TestCore, self).setUp()
        self.cf = ConsoleConf(self.prober, self.opts)

    def test_projectname(self):
        self.assertEquals("console_conf", self.cf.project)

    def test_controllers(self):
        self.assertEquals(len(self.cf.controllers), 3)
        self.assertIn("Welcome", self.cf.controllers)
        self.assertIn("Network", self.cf.controllers)
        self.assertIn("Identity", self.cf.controllers)
