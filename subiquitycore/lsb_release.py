# This file is part of subiquity. See LICENSE file for license information.
import shlex
from typing import Dict

LSB_RELEASE_FILE = "/etc/lsb-release"
LSB_RELEASE_EXAMPLE = "examples/lsb-release-focal"


def lsb_release(path=None, dry_run: bool = False) -> Dict[str, str]:
    """return a dictionary of values from /etc/lsb-release.
    keys are lower case with DISTRIB_ prefix removed."""
    if dry_run and path is not None:
        raise ValueError("Both dry_run and path are specified.")

    if path is None:
        path = LSB_RELEASE_EXAMPLE if dry_run else LSB_RELEASE_FILE

    ret: Dict[str, str] = {}
    try:
        with open(path, "r") as fp:
            content = fp.read()
    except FileNotFoundError:
        return ret

    for tok in shlex.split(content):
        k, _, v = tok.partition("=")
        if not k.startswith("DISTRIB_") or not v:
            continue
        ret[k.replace("DISTRIB_", "").lower()] = v
    return ret


if __name__ == "__main__":
    print(lsb_release())
