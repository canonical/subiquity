
from subiquitycore.models.network import NetworkModel
from .identity import IdentityModel


class ConsoleConfModel:
    """The overall model for console-conf."""

    def __init__(self, app):
        self.network = NetworkModel(support_wlan=True)
        self.identity = IdentityModel()
