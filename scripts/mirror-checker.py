#!/usr/bin/env python3

import argparse
import os
import shlex
import subprocess
import sys
import tempfile


def run_cmd(cmd: list[str]) -> int:
    """Run a cmd list. Return output."""
    # Print out command bash -x style
    print(f"+ {shlex.join(cmd)}")
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    ) as proc:
        try:
            for line in iter(proc.stdout.readline, ""):
                print(line, end="")
        except KeyboardInterrupt:
            print("Killed by user.")
        finally:
            proc.stdout.close()
            proc.wait()

        return proc.returncode


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Use debootstrap to test mirror health. Requires root.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "country_code",
        help="- two letter country code",
    )
    parser.add_argument(
        "release",
        nargs="?",
        default="noble",
        help="- release",
    )

    return parser.parse_args()


def main() -> int:

    args = parse_args()

    if os.geteuid() != 0:
        print("mirror-checker requires sudo")
        return 1

    release: str = args.release
    mirror: str = f"http://{args.country_code}.archive.ubuntu.com/ubuntu/"

    with tempfile.TemporaryDirectory() as tempdir:

        print(f"Creating schroot in: {tempdir}")
        print(f"Targeting release: {release}")
        print(f"Using mirror: {mirror}")

        debootstrap_cmd = ["debootstrap", release, tempdir, mirror]
        ret = run_cmd(debootstrap_cmd)

    return ret


if __name__ == "__main__":
    sys.exit(main())
