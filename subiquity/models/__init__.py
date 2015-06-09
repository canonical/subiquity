# Copyright 2015 Canonical, Ltd.

""" Model Classes

Model's represent the stateful data bound from
input from the user.
"""


class Model:
    """Base model"""

    def to_json(self):
        """Marshals the model to json"""
        return NotImplementedError

    def create(self):
        """Creates model instance with validation"""
        return NotImplementedError


class Field:
    """Base field class

    New field types inherit this class, provides access to
    validation checks and type definitions.
    """
    default_error_messages = {
        'invalid_choice': ('Value %(value)r is not a valid choice.'),
        'null': ('This field cannot be null.'),
        'blank': ('This field cannot be blank.')
    }

    def __init__(self, name=None, blank=False, null=False):
        self.name = name
        self.blank, self.null = blank, null
