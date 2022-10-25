#!/usr/bin/env python3

import argparse
from typing import List, Tuple

discourse_substitutions = [
    ("autoinstall.md", "/t/automated-server-installs/16612"),
    ("autoinstall-reference.md", "/t/automated-server-install-reference/16613"),
    ("autoinstall-quickstart.md", "/t/automated-server-install-quickstart/16614"),
    ("autoinstall-schema.md", "/t/automated-server-install-schema/16615"),
    ("autoinstall-quickstart-s390x.md", "/t/automated-server-install-schema/16616"),
]
md_to_html_substitutions = [
    ("autoinstall.md", "autoinstall.html"),
    ("autoinstall-reference.md", "autoinstall-reference.html"),
    ("autoinstall-quickstart.md", "autoinstall-quickstart.html"),
    ("autoinstall-schema.md", "autoinstall-schema.html"),
    ("autoinstall-quickstart-s390x.md", "autoinstall-quickstart-s390x.html"),
]

def perform_substitutions(content: str, substitutions: List[Tuple[str, str]]) -> str:
    for old, new in substitutions:
        content = content.replace(old, new)
    return content


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", "-i", type=argparse.FileType(mode="r"), default="-")
    parser.add_argument("--output", "-o", type=argparse.FileType(mode="w"), default="-")
    parser.add_argument("action", choices=("md-to-discourse", "md-to-html"))

    args = vars(parser.parse_args())

    if args["action"] == "md-to-discourse":
        substitutions = discourse_substitutions
    else:
        substitutions = md_to_html_substitutions

    print(perform_substitutions(
            args["input"].read(),
            substitutions=substitutions),
        file=args["output"])


if __name__ == "__main__":
    main()
