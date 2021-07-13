#!/usr/bin/env python3

# usage: schema-cmp.py expected.json actual.json
# schema comparison should match, except timezones which we just spot
# check for a few expected values and expect that reality is a superset
import json
import sys

def load(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    tz = data['properties']['timezone']['enum']
    del data['properties']['timezone']['enum']
    return data, tz

expected, _ = load(sys.argv[1])
actual, actual_tz = load(sys.argv[2])

if expected != actual:
    print('schema mismatch')
    print('expected:')
    print(expected)
    print('actual:')
    print(actual)
    sys.exit(1)

expected_tz = [
    '',
    'geoip',
    'UTC',
    'America/New_York',
]

for tz in expected_tz:
    assert tz in actual_tz, f'tz {tz} not found'
