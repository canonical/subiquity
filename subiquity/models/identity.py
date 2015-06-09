# Copyright 2015 Canonical, Ltd.

""" Identity Model

Represents information related to identification, for example,
User's first and last name, timezone, country, language preferences.
"""

from subiquity import models


class UserModel(models.Model):
    """ User class to support personal information
    """
    username = None
    language = None
    keyboard = None
    timezone = None
