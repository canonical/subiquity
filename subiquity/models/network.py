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

""" Network Model

Provides network device listings and extended network information

"""

from subiquity import models
import argparse
from probert import prober


class NetworkModel(models.Model):
    """ Model representing network interfaces
    """

    additional_options = ['Set default route',
                          'Bond interfaces',
                          'Install network driver']

    def __init__(self):
        self.hwdata = {}
        self.options = argparse.Namespace(probe_storage=False, probe_network=True)
        self.prober = prober.Prober(self.options)

    def probe_network(self):
        self.prober.probe()
        self.hwdata = self.prober.get_results()

    def get_interfaces(self):
        return [n for n in self.hwdata['network'].keys() 
                if self.hwdata['network'][n]['type'] == 'eth']
