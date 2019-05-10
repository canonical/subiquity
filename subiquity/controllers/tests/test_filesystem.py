# Copyright 2019 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from collections import defaultdict
import unittest

from subiquity.controllers.filesystem import (
    FilesystemController,
    )
from subiquity.models.tests.test_filesystem import (
    make_model_and_disk,
    )


class FakeBaseModel:
    pass


def make_controller_and_disk():
    common = defaultdict(type(None))
    bm = FakeBaseModel()
    bm.filesystem, disk = make_model_and_disk()
    common['base_model'] = bm
    common['answers'] = {}
    controller = FilesystemController(common)
    return controller, disk


class TestFilesystemController(unittest.TestCase):

    def test_delete_encrypted_vg(self):
        controller, disk = make_controller_and_disk()
        spec = {
            'password': 'passw0rd',
            'devices': {disk},
            'name': 'vg0',
            }
        vg = controller.create_volgroup(spec)
        controller.delete_volgroup(vg)
        dm_crypts = [
            a for a in controller.model._actions if a.type == 'dm_crypt']
        self.assertEqual(dm_crypts, [])
