from dataclasses import dataclass


class SnapVersionParsingError(Exception):
    """ Exception raised when a version string does not match the expected
    format
    """
    def __init__(self, message: str = "", version: str = ""):
        self.message = message
        self.version = version
        super().__init__()


@dataclass
class SnapVersion:
    """ Represent the version of a snap in the form {major}.{minor}.{patch} """
    major: int
    minor: int
    patch: int

    @classmethod
    def from_string(cls, s: str) -> "SnapVersion":
        """ Construct a SnapVersion object from a string representation """
        try:
            major, minor, patch = s.split(".")
            return cls(int(major), int(minor), int(patch))
        except (ValueError, TypeError):
            raise SnapVersionParsingError(version=s)

    def __gt__(self, other: "SnapVersion"):
        """ Tells whether a SnapVersion object is greater than the other """
        if self.major > other.major:
            return True
        elif self.major < other.major:
            return False

        if self.minor > other.minor:
            return True
        elif self.minor < other.minor:
            return False

        if self.patch > other.patch:
            return True
        elif self.patch < other.patch:
            return False

        return False
