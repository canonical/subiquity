# This file is part of subiquity. See LICENSE file for license information.
import shlex
from pathlib import Path

LSB_RELEASE_FILE = Path("/etc/lsb-release")
LSB_RELEASE_EXAMPLE = Path("examples/lsb-release-focal")


def lsb_release_from_path(path: Path) -> dict[str, str]:
    ret: dict[str, str] = {}
    try:
        content = path.read_text()
    except FileNotFoundError:
        return ret

    for tok in shlex.split(content):
        k, _, v = tok.partition("=")
        if not k.startswith("DISTRIB_") or not v:
            continue
        ret[k.replace("DISTRIB_", "").lower()] = v
    return ret


def lsb_release(path: Path | None = None, dry_run: bool = False) -> dict[str, str]:
    """return a dictionary of values from /etc/lsb-release.
    keys are lower case with DISTRIB_ prefix removed."""
    if dry_run and path is not None:
        raise ValueError("Both dry_run and path are specified.")

    if path is None:
        path = LSB_RELEASE_EXAMPLE if dry_run else LSB_RELEASE_FILE

    return lsb_release_from_path(path)
