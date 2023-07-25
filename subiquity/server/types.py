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

from subiquitycore.pubsub import CoreChannels

# This module defines constants to be used with "hub.{a,}broadcast" to
# allow controllers to find out when various things have happened.


class InstallerChannels(CoreChannels):
    # This message is sent when a value is provided for the http proxy
    # setting.
    NETWORK_PROXY_SET = "network-proxy-set"
    # This message is sent there has been a network change that might affect
    # snapd's ability to talk to the network.
    SNAPD_NETWORK_CHANGE = "snapd-network-change"
    # This message is send when results from the geoip service are received.
    GEOIP = "geoip"
    # (CONFIGURED, $model_name) is sent when a model is marked
    # configured. Note that this can happen several times for each controller
    # (at least in theory) if the users goes back to a screen and makes a
    # different choice.
    CONFIGURED = "configured"
    # This message is sent when apt has been configured in the overlay that
    # will be used as the source for the install step of the
    # installation. Currently this is only done once, but this might change in
    # the future.
    APT_CONFIGURED = "apt-configured"
    # This message is sent when the user has confirmed that the install has
    # been confirmed. Once this has happened one can be sure that all the
    # models in the "install" side of the install/postinstall divide will not
    # be reconfigured.
    INSTALL_CONFIRMED = "install-confirmed"
    # This message is sent as late as possible, and just before shutdown.  This
    # step is after logfiles have been copied to the system, so should be used
    # sparingly and only as absolutely required.
    PRE_SHUTDOWN = "pre-shutdown"
