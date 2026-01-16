#!/usr/bin/env python3

import argparse
import contextlib
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


class CheckFailedError(Exception):
    pass


def read_local_enumeration(module: str, type: str) -> dict[str, str]:
    local_module = importlib.import_module(module)

    enumeration = getattr(local_module, type)

    ret = {}
    for entry in enumeration:
        ret[entry.name] = entry.value
    return ret


def read_snapd_constants(go_file: Path, type: str) -> dict[str, str]:
    cmd = [
        "go",
        "run",
        "scripts/extract-golang-constants.go",
        "--constant-type",
        type,  # Feels weird placing this before -- but ...
        "--",  # To make sure the next is not interpreted as a file to build
        str(go_file),
    ]

    return json.loads(subprocess.check_output(cmd))


def _check_secboot_type_on_sync(
    secboot_file: Path,
    secboot_type: str,
    local_module: str,
    local_type: str,
    secboot_ignored_names: list[str],
) -> None:
    snapd_name_to_value = read_snapd_constants(secboot_file, secboot_type)
    snapd_value_to_name = {v: k for k, v in snapd_name_to_value.items()}
    snapd_values = set(snapd_name_to_value.values())

    local_name_to_value = read_local_enumeration(local_module, local_type)
    local_value_to_name = {v: k for k, v in local_name_to_value.items()}
    local_values = set(local_name_to_value.values())

    check_ok = True
    for value in snapd_values.difference(local_values):
        # Constants that are in snapd but not in Subiquity
        name = snapd_value_to_name[value]
        if name in secboot_ignored_names:
            continue
        check_ok = False
        print(f"{name!r} => {value!r} is not present in Subiquity, consider adding.")
    for value in local_values.difference(snapd_values):
        # Constants that are in Subiquity but not in snapd
        name = local_value_to_name[value]
        print(f"{name!r} => {value!r} is not present in Snapd, consider removing.")
        check_ok = False

    if not check_ok:
        raise CheckFailedError


def check_secboot_error_kinds_on_sync(secboot_dir: Path) -> None:
    _check_secboot_type_on_sync(
        secboot_file=secboot_dir / "efi/preinstall/error_kinds.go",
        secboot_type="ErrorKind",
        local_module="subiquity.common.types.storage",
        local_type="CoreBootAvailabilityErrorKind",
        secboot_ignored_names=["ErrorKindNone"],
    )


def check_secboot_fix_actions_on_sync(secboot_dir: Path) -> None:
    _check_secboot_type_on_sync(
        secboot_file=secboot_dir / "efi/preinstall/actions.go",
        secboot_type="Action",
        local_module="subiquity.common.types.storage",
        local_type="CoreBootFixAction",
        secboot_ignored_names=["ActionNone"],
    )


@contextlib.contextmanager
def temporary_snapd_tree():
    with tempfile.TemporaryDirectory() as tdir:
        subprocess.run(["git", "clone", "https://github.com/canonical/snapd", tdir])
        yield Path(tdir)


def main() -> None:
    # Add the subiquity tree at the top
    sys.path.insert(0, str(Path(__file__).parent.parent))

    parser = argparse.ArgumentParser()

    parser.add_argument("--snapd-revision", default="master")
    parser.add_argument("--snapd-tree", type=Path)

    args = parser.parse_args()

    if args.snapd_tree is None:
        cm = temporary_snapd_tree()
    else:
        cm = contextlib.nullcontext(args.snapd_tree)

    with cm as snapd_tree:
        subprocess.run(
            ["git", "-C", snapd_tree, "switch", "--detach", args.snapd_revision]
        )

        # Secboot
        subprocess.run(
            ["go", "mod", "download", "github.com/snapcore/secboot"], cwd=snapd_tree
        )
        secboot_dir = Path(
            subprocess.check_output(
                ["go", "list", "-m", "-f", "{{.Dir}}", "github.com/snapcore/secboot"],
                cwd=snapd_tree,
                text=True,
            ).strip()
        )
        failed = set()
        try:
            check_secboot_error_kinds_on_sync(secboot_dir)
        except CheckFailedError:
            failed.add("error-kinds")
        try:
            check_secboot_fix_actions_on_sync(secboot_dir)
        except CheckFailedError:
            failed.add("fix-actions")

        if failed:
            raise RuntimeError(f"The following types checks failed: {failed}")


if __name__ == "__main__":
    main()
