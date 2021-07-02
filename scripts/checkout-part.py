#!/usr/bin/python3
import subprocess
import sys
import yaml

part = sys.argv[1]


def r(*args):
    print('running', args)
    subprocess.run(args, check=True)


with open("snapcraft.yaml") as f:
    config = yaml.safe_load(f)["parts"][part]

r('git', 'clone', config['source'], part)


c = None
for k in "source-commit", "source-tag", "source-branch":
    if k in config:
        c = config[k]
        break

if c is not None:
    r('git', '-c', 'advice.detachedHead=false', '-C', part, 'checkout', c)
