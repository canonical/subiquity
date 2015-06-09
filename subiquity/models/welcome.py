# Copyright 2015 Canonical, Ltd.

""" Welcome Model

Welcome model provides user with installation options

"""

from subiquity import models


class WelcomeModel(models.Model):
    """ Model representing installation type
    """

    install_type = None
