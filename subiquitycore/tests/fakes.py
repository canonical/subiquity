import os
import yaml

TOP_DIR = os.path.join('/'.join(__file__.split('/')[:-3]))
TEST_DATA = os.path.join(TOP_DIR, 'tests', 'data')
FAKE_MACHINE_JSON = os.path.join(TEST_DATA, 'fake_machine.json')
FAKE_MACHINE_JSON_DATA = yaml.safe_load(open(FAKE_MACHINE_JSON))
FAKE_MACHINE_STORAGE_DATA = FAKE_MACHINE_JSON_DATA.get('storage')
