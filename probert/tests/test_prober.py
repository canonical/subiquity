import testtools
import json
import argparse

from mock import patch

from probert.prober import Prober
from probert.storage import Storage
from probert.network import NetworkProber
from probert.tests.fakes import FAKE_PROBE_ALL_JSON


class ProbertTestProber(testtools.TestCase):

    def test_prober_init(self):
        p = Prober()
        self.assertNotEqual(p, None)

    @patch.object(Prober, 'probe_all')
    def test_prober_probe_all(self, _probe_all):
        p = Prober()
        p.probe_all()
        self.assertTrue(_probe_all.called)

    @patch.object(Prober, 'probe_network')
    @patch.object(Prober, 'probe_storage')
    def test_prober_probe_all_invoke_others(self, _storage, _network):
        p = Prober()
        p.probe_all()
        self.assertTrue(_storage.called)
        self.assertTrue(_network.called)

    def test_prober_get_results(self):
        p = Prober()
        self.assertEqual({}, p.get_results())

    @patch.object(NetworkProber, 'probe')
    @patch.object(Storage, 'probe')
    def test_prober_probe_all_check_results(self, _storage, _network):
        p = Prober()
        results = {
            'storage': {'lambic': 99},
            'network': {'saison': 99},
        }
        _storage.return_value = results['storage']
        _network.return_value = results['network']
        p.probe_all()
        self.assertTrue(_storage.called)
        self.assertTrue(_network.called)
        self.assertEqual(results, p.get_results())
