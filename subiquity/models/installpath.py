# Copyright 2015 Canonical, Ltd.
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

""" Install Path Model

Provides high level options for Ubuntu install

"""

from subiquity import models


class InstallpathModel(models.Model):
    """ Model representing install options
    """

    install_paths = ['Install Ubuntu',
                     'Install MAAS Region Server',
                     'Install MAAS Cluster Server',
                     'Test installation media',
                     'Test machine memory']
    selected_path = None
