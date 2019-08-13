# Copyright 2016 Canonical, Ltd.
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

from .filesystem import (
    FilesystemView,
    GuidedDiskSelectionView,
    )
from .bcache import BcacheView
from .ceph import CephDiskView
from .iscsi import IscsiDiskView
from .identity import IdentityView
from .installprogress import ProgressView
from .keyboard import KeyboardView
from .welcome import WelcomeView
from .zdev import ZdevView
__all__ = [
    'BcacheView',
    'CephDiskView',
    'FilesystemView',
    'GuidedDiskSelectionView',
    'IdentityView',
    'IscsiDiskView',
    'KeyboardView',
    'MAASView',
    'ProgressView',
    'WelcomeView',
    'ZdevView',
]
