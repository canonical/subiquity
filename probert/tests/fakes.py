import os
import yaml

TOP_DIR = os.path.join('/'.join(__file__.split('/')[:-3]))
TEST_DATA = os.path.join(TOP_DIR, 'probert', 'tests', 'data')
FAKE_PROBE_ALL_JSON = os.path.join(TEST_DATA, 'fake_probe_all.json')
