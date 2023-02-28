#!/usr/bin/env python3

""" Checks whether Active Directory setup respects autoinstall definitions. """

import argparse
import asyncio
import logging
import re
import os
from typing import List
from subiquity.models.ad import ADModel


class FailedTestCase(Exception):
    pass


async def target_packages() -> List[str]:
    """ Returns the list of packages the AD Model wants to install in the
        target system."""
    model = ADModel()
    model.do_join = True
    return await model.target_packages()


async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--tmpdir", type=str)

    args = vars(parser.parse_args())

    if args["debug"]:
        logging.getLogger().level = logging.DEBUG

    expected_packages = await target_packages()
    packages_lookup = {p: False for p in expected_packages}
    log_path = os.path.join(args["tmpdir"], "subiquity-server-debug.log")
    find_start = 'finish: subiquity/Install/install/postinstall/install_{}:'
    log_status = ' SUCCESS: installing {}'

    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines:
            for pack in packages_lookup:
                find_line = find_start.format(pack) + log_status.format(pack)
                pack_found = re.search(find_line, line) is None
                if pack_found:
                    packages_lookup[pack] = True

    for k, v in packages_lookup.items():
        logging.debug(f"Checking package {k}")
        if not v:
            raise FailedTestCase(f"package {k} not found in the target")


if __name__ == "__main__":
    asyncio.run(main())
