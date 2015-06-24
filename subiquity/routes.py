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

from subiquity.controllers.welcome import WelcomeController
from subiquity.controllers.installpath import InstallpathController
from subiquity.controllers.network import NetworkController


class RoutesError(Exception):
    """ Error in routes """
    pass


class Routes:
    """ Defines application routes and maps to their controller

    Routes are inserted top down from start to finish. Maintaining
    this order is required for routing to work.
    """
    routes = [WelcomeController,
              InstallpathController,
              NetworkController]
    current_route_idx = 0

    @classmethod
    def route(cls, idx):
        """ Include route listing in controllers """
        try:
            _route = cls.routes[idx]
        except IndexError:
            raise RoutesError("Failed to load Route at index: {}".format(idx))
        return _route

    @classmethod
    def current_idx(cls):
        """ Returns current route index """
        return cls.current_route_idx

    @classmethod
    def reset(cls):
        """ Resets current route """
        cls.current_route_idx = 0

    @classmethod
    def first(cls):
        """ first controller/start of install """
        return cls.route(0)

    @classmethod
    def last(cls):
        """ end of install, last controller """
        return cls.route(-1)

    @classmethod
    def next(cls):
        cls.current_route_idx = cls.current_route_idx + 1
        return cls.route(cls.current_route_idx)

    @classmethod
    def prev(cls):
        cls.current_route_idx = cls.current_route_idx - 1
        return cls.route(cls.current_route_idx)
