
from subiquitycore.models.network import NetworkModel
from .identity import IdentityModel


class ConsoleConfModel:
    """The overall model for console-conf."""

    def __init__(self, common):
        self.network = NetworkModel(support_wlan=True)
        self.identity = IdentityModel()
