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

import logging
from subiquity import models
import argparse
from probert import prober

log = logging.getLogger('subiquity.filesystemView')


class NetworkModel(models.Model):
    """ Model representing network interfaces
    """

    additional_options = ['Set default route',
                          'Bond interfaces',
                          'Install network driver']

    def __init__(self):
        self.network = {}
        self.options = argparse.Namespace(probe_storage=False,
                                          probe_network=True)
        self.prober = prober.Prober(self.options)

    def probe_network(self):
        self.prober.probe()
        self.network = self.prober.get_results().get('network')

    def get_interfaces(self):
        return [iface for iface in self.network.keys()
                if self.network[iface]['type'] == 'eth' and
                not self.network[iface]['hardware']['DEVPATH'].startswith(
                    '/devices/virtual/net')]

    def get_vendor(self, iface):
        hwinfo = self.network[iface]['hardware']
        vendor_keys = [
            'ID_VENDOR_FROM_DATABASE',
            'ID_VENDOR',
            'ID_VENDOR_ID'
        ]
        for key in vendor_keys:
            try:
                return hwinfo[key]
            except KeyError:
                log.warn('Failed to get key '
                         '{} from interface {}'.format(key, iface))
                pass

        return 'Unknown Vendor'

    def get_model(self, iface):
        hwinfo = self.network[iface]['hardware']
        model_keys = [
            'ID_MODEL_FROM_DATABASE',
            'ID_MODEL',
            'ID_MODEL_ID'
        ]
        for key in model_keys:
            try:
                return hwinfo[key]
            except KeyError:
                log.warn('Failed to get key '
                         '{} from interface {}'.format(key, iface))
                pass

        return 'Unknown Model'

    def get_iface_info(self, iface):
        ipinfo = self.network[iface]['ip']
        return "{}/{} -- {} {}".format(ipinfo['addr'],
                                       ipinfo['netmask'],
                                       self.get_vendor(iface),
                                       self.get_model(iface))
