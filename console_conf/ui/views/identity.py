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
from urwid import (Pile, Columns, Text, ListBox)
from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.interactive import (PasswordEditor,
                                          RealnameEditor,
                                          StringEditor,
                                          UsernameEditor)
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView
from subiquitycore.curtin import (curtin_write_postinst_config,
                                  curtin_configure_user)
from subiquitycore.ui.views.identity import IdentityView as CoreIdentityView

log = logging.getLogger("console_conf.views.identity")

USERADD_OPTIONS = "--extrausers"


class IdentityView(CoreIdentityView):
    pass

