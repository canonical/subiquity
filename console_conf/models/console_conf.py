
from subiquitycore.models.network import NetworkModel
from .identity import IdentityModel


class ConsoleConfModel:
    """The overall model for console-conf."""

    def __init__(self):
        self.network = NetworkModel("console-conf")
        self.identity = IdentityModel()
