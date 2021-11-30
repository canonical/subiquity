import unittest

from subiquity.common.snap import SnapVersion, SnapVersionParsingError


class TestSnapSnapVersion(unittest.TestCase):
    def test_snap_version_from_string(self):
        obj = SnapVersion.from_string("19.04.2")

        self.assertEqual(obj.major, 19)
        self.assertEqual(obj.minor, 4)
        self.assertEqual(obj.patch, 2)

        # Test with no patch number
        with self.assertRaises(SnapVersionParsingError):
            SnapVersion.from_string("19.02")

        # Test unsupported version with RC
        with self.assertRaises(SnapVersionParsingError):
            SnapVersion.from_string("19.02.2-rc1")

    def test_snap_version_compare(self):
        self.assertGreater(SnapVersion(20, 4, 2), SnapVersion(19, 4, 2))
        self.assertGreater(SnapVersion(19, 5, 2), SnapVersion(19, 4, 1))
        self.assertLess(SnapVersion(19, 4, 2), SnapVersion(20, 3, 2))
