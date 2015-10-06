import os
import yaml

TOP_DIR = os.path.join('/'.join(__file__.split('/')[:-3]))
TEST_DATA = os.path.join(TOP_DIR, 'subiquity', 'tests', 'data')
FAKE_MACHINE_JSON = os.path.join(TEST_DATA, 'fake_machine.json')

