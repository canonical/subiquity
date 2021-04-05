#!/usr/bin/python3
import sys

import yaml


config = yaml.safe_load(open(sys.argv[1]))


def main():

    for arg in sys.argv[2:]:
        if '=' in arg:
            k, expected = arg.split('=', 1)
            expected = yaml.safe_load(expected)
        else:
            k, expected = arg, None
        v = config
        for part in k.split('.'):
            if '[' in part:
                part, index = part.split('[')
                index = int(index[:-1])
            else:
                index = None
            v = v[part]
            if index is not None:
                v = v[index]
        if expected is None:
            print(v)
        else:
            assert v == expected, "{!r} != {!r}".format(v, expected)


main()
