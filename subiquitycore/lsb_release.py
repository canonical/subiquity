# This file is part of subiquity. See LICENSE file for license information.
import shlex

LSB_RELEASE_FILE = "/etc/lsb-release"


def lsb_release(path=None):
    """return a dictionary of values from /etc/lsb-release.
    keys are lower case with DISTRIB_ prefix removed."""
    if path is None:
        path = LSB_RELEASE_FILE

    ret = {}
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


if __name__ == '__main__':
    print(lsb_release())
