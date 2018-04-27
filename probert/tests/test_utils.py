import testtools

from probert import utils

class ProbertTestUtils(testtools.TestCase):
    def setUp(self):
        super(ProbertTestUtils, self).setUp()

    def test_utils_dict_merge(self):
        r1 = {'relations': ['m1', 'x1']}
        r2 = {'relations': ['m2', 'x2']}
        combined = {'relations': ['m1', 'm2', 'x1', 'x2']}
        test_result = utils.dict_merge(r1, r2)
        self.assertEqual(sorted(combined['relations']),
                         sorted(test_result['relations']))

    def test_utils_dict_merge_lists(self):
        r1 = ['m1', 'x1']
        r2 = ['m2', 'x2']
        combined = ['m1', 'm2', 'x1', 'x2']
        test_result = utils.dict_merge(r1, r2)
        self.assertEqual(sorted(combined), sorted(test_result))

    def test_utils_dict_merge_dicts(self):
        r1 = {'storage': {'/dev/sda': {'DEVTYPE': 'disk'}}}
        r2 = {'storage': {'/dev/sda': {'ID_MODEL': 'AWESOME'}}}
        combined = {
            'storage': {
                '/dev/sda': {
                    'DEVTYPE': 'disk',
                    'ID_MODEL': 'AWESOME',
                }
            }
        }
        test_result = utils.dict_merge(r1, r2)
        self.assertEqual(sorted(combined), sorted(test_result))
