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

""" Model Classes

Model's represent the stateful data bound from
input from the user.
"""

import json
import yaml


class Model:
    """Base model"""

    fields = []

    def to_json(self):
        """Marshals the model to json"""
        return json.dumps(self.__dict__)

    def to_yaml(self):
        """Marshals the model to yaml"""
        return yaml.dump(self.__dict__)


class Field:
    """Base field class

    New field types inherit this class, provides access to
    validation checks and type definitions.
    """
    default_error_messages = {
        'invalid_choice': ('Value %(value)r is not a valid choice.'),
        'blank': ('This field cannot be blank.')
    }

    def __init__(self, name=None, blank=False):
        self.name = name
        self.blank = blank


class ChoiceField(Field):
    """ Choices Field

    Provide a list of known options

    :param list options: list of options to choose from
    """

    def __init__(self, options):
        self.options = options

    def list_options(cls):
        return cls.options
