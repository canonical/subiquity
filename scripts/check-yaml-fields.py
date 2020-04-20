#!/usr/bin/python3
import sys

import yaml


config = yaml.safe_load(open(sys.argv[1]))


def main():

    for arg in sys.argv[2:]:
        k, expected = arg.split('=', 1)
        expected = yaml.safe_load(expected)
        v = config
        for part in k.split('.'):
            v = v[part]
        assert v == expected, "{!r} != {!r}".format(v, expected)

main()
