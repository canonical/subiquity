from dataclasses import dataclass
from typing import Optional
import re


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
    """ Represent the version of a snap in either of the following forms:
        * {major}.{minor}.{patch}
        * {major}.{minor}.{patch}+git{buildId}.{commitId}
    """
    major: int
    minor: int
    patch: int
    git_build_id: Optional[int] = None
    git_commit_id: Optional[str] = None

    @classmethod
    def from_string(cls, s: str) -> "SnapVersion":
        """ Construct a SnapVersion object from a string representation """
        try:
            major, minor, patch = s.split(".", maxsplit=2)
            git_build_id = None
            git_commit_id = None
            # Check if what we assume is the patch number does not contain a
            # +git... information
            match = re.fullmatch(r"(\d+)\+git(\d+)\.([0-9a-f]+)", patch)
            if match:
                patch, git_build_id, git_commit_id = match.groups()
            return cls(int(major), int(minor), int(patch),
                       None if git_build_id is None else int(git_build_id),
                       git_commit_id)
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

        if self.git_build_id is not None and other.git_build_id is None:
            return True
        elif self.git_build_id is None and other.git_build_id is not None:
            return False

        return self.git_build_id > other.git_build_id
