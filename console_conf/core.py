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

import logging
import urwid
from tornado.ioloop import IOLoop
from tornado.util import import_object
from subiquitycore.signals import Signal
from subiquitycore.palette import STYLES, STYLES_MONO
from subiquitycore.prober import Prober, ProberException

from subiquitycore.core import CoreControllerError, Controller as ControllerBase

log = logging.getLogger('console_conf.core')


class Controller(ControllerBase):

    project = "console_conf"
    controllers = {
        "Welcome": None,
        "Network": None,
        "Identity": None,
        "Login": None,
    }

