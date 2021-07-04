#!/usr/bin/python3
import os
import subprocess
import sys
import yaml

part = sys.argv[1]


def r(*args, **kw):
    print('running', args)
    subprocess.run(args, check=True, **kw)


def o(*args, **kw):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE).stdout


with open("snapcraft.yaml") as f:
    config = yaml.safe_load(f)["parts"][part]


c = "master"
for k in "source-commit", "source-tag", "source-branch":
    if k in config:
        c = config[k]
        break

if not os.path.isdir(part):
    r('git', 'clone', config['source'], part)

expected = o('git', '-C', part, 'rev-parse', c)
actual = o('git', '-C', part, 'rev-parse', 'HEAD')

if expected != actual:
    try:
        r('git', '-c', 'advice.detachedHead=false', '-C', part, 'checkout', c)
    except subprocess.CalledProcessError:
        r('git', '-C', part, 'fetch', config['source'])
        r('git', '-c', 'advice.detachedHead=false', '-C', part, 'checkout', c)
