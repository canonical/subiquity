# Copyright 2021 Canonical, Ltd.
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
""" Module that defines the model for Ubuntu Advantage configuration. """

import logging

log = logging.getLogger("subiquity.models.ubuntu_advantage")


class UbuntuAdvantageModel:
    """
    Model that represents the Ubuntu Advantage configuration.
    Currently, we rely only on cloud-init so we have no means to validate that
    the provided token is correct ; nor to retrieve information about the
    subscription.
    """
    def __init__(self):
        """ Initialize the model. """
        self.token: str = ""

    def make_cloudconfig(self) -> dict:
        """
        Return a dictionary that will be included in cloud-init config.
        Having the token set to the empty-string disables the configuration.
        """
        if not self.token:
            return {}
        # Both "ubuntu_advantage" and "ubuntu-advantage" keys are accepted, but
        # "ubuntu-advantage" is deprecated despite not being mentioned in the
        # documentation.
        return {
            "ubuntu_advantage": {
                "token": self.token,
            },
        }
