#!/usr/bin/env python3

# usage: schema-cmp.py expected.json actual.json
# schema comparison should match, except timezones which we just spot
# check for a few expected values and expect that reality is a superset
import json
import sys

def load(filename, ignore_tz):
    with open(filename, 'r') as f:
        data = json.load(f)
    tz = None
    if not ignore_tz:
        tz = data['properties']['timezone'].pop('enum')
    return data, tz

ignore_tz = False
if len(sys.argv) > 3 and sys.argv[3].lower() == "--ignore-tz":
    ignore_tz = True

expected, _ = load(sys.argv[1], ignore_tz)
actual, actual_tz = load(sys.argv[2], ignore_tz)

if expected != actual:
    print('schema mismatch')
    print('expected:')
    print(expected)
    print('actual:')
    print(actual)
    sys.exit(1)

if ignore_tz:
    sys.exit(0)

expected_tz = [
    '',
    'geoip',
    'UTC',
    'America/New_York',
]

for tz in expected_tz:
    assert tz in actual_tz, f'tz {tz} not found'
