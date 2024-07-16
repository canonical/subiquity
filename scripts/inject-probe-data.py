#!/usr/bin/env python3

"""Bugs filed against Subiquity on Launchpad include a file named
"ProbeData.txt" ; which contains the storage data extracted by probert.
Some of the bugs can easily be reproduced in dry-run mode if we feed the
storage data back to Subiquity. To do so, we can replace the "storage" section
of the machine-config with the contents of ProbeData.txt.

This script is meant to simplify this process.
"""

import argparse
import contextlib
import json
import sys


def parse_cmdline() -> argparse.Namespace:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description=__doc__)

    parser.add_argument("--storage-probe-data", type=argparse.FileType("r"), default="ProbeData.txt",
                        help="Path to the ProbeData.txt file.")
    parser.add_argument("--machine-config", type=argparse.FileType("r"), default="examples/machines/simple.json",
                        help="Read machine-config from the specified file.")
    parser.add_argument("--overwrite-machine-config", action="store_true",
                        help="Overwrite machine-config file rather than printing to stdout.")

    return parser.parse_args()


def main() -> None:
    args = parse_cmdline()

    storage_data = json.load(args.storage_probe_data)
    machine_config = json.load(args.machine_config)

    machine_config["storage"] = storage_data

    if args.overwrite_machine_config:
        context = open(args.machine_config.name, mode="w",
                       encoding=args.machine_config.encoding)
    else:
        context = contextlib.nullcontext(sys.stdout)

    with context as stream:
        json.dump(machine_config, stream, indent=4),


if __name__ == "__main__":
    main()
