import unittest

from subiquity.common.snap import SnapVersion, SnapVersionParsingError


class TestSnapSnapVersion(unittest.TestCase):
    def test_snap_version_from_string(self):
        obj = SnapVersion.from_string("19.04.2")

        self.assertEqual(obj.major, 19)
        self.assertEqual(obj.minor, 4)
        self.assertEqual(obj.patch, 2)
        self.assertIsNone(obj.git_build_id)
        self.assertIsNone(obj.git_commit_id)

        obj = SnapVersion.from_string("21.10.3+git136.cde71504")

        self.assertEqual(obj.major, 21)
        self.assertEqual(obj.minor, 10)
        self.assertEqual(obj.patch, 3)
        self.assertEqual(obj.git_build_id, 136)
        self.assertEqual(obj.git_commit_id, "cde71504")

    def test_snap_version_from_string_invalid(self):
        # Test with no patch number
        with self.assertRaises(SnapVersionParsingError):
            SnapVersion.from_string("19.02")

        # Test unsupported version with RC (we support only +git)
        with self.assertRaises(SnapVersionParsingError):
            SnapVersion.from_string("19.02.2-rc1")

    def test_snap_version_compare(self):
        self.assertGreater(SnapVersion(20, 4, 2), SnapVersion(19, 4, 2))
        self.assertGreater(SnapVersion(19, 5, 2), SnapVersion(19, 4, 1))
        self.assertLess(SnapVersion(19, 4, 2), SnapVersion(20, 3, 2))
        # Consider the version is greater if one has a build ID
        self.assertGreater(SnapVersion.from_string("21.10.3+git136.cde71504"),
                           SnapVersion.from_string("21.10.3"))
        # Consider the version is greater if the build ID is greater
        self.assertGreater(SnapVersion.from_string("21.10.3+git136.cde71504"),
                           SnapVersion.from_string("21.10.3+git135.deadbeef"))
        # Make sure we ignore the build ID when the patch version is different
        self.assertLess(SnapVersion.from_string("21.10.2+git255.deadbeef"),
                        SnapVersion.from_string("21.10.3+git135.deadbeef"))
