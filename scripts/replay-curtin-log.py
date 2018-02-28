#!/usr/bin/python3

import json
import os
import sys
import time

from systemd import journal

json_file = sys.argv[1]
event_identifier = sys.argv[2]

scale_factor = float(os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "4"))

def time_for_entry(e):
    return int(e['__MONOTONIC_TIMESTAMP'])/1e6

def report(e):
    if e['SYSLOG_IDENTIFIER'].startswith("curtin_event"):
        e['SYSLOG_IDENTIFIER'] = event_identifier
        e['CODE_LINE'] = int(e['CODE_LINE'])
        journal.send(**e)
    elif e['SYSLOG_IDENTIFIER'].startswith("curtin_log"):
        print(e['MESSAGE'], flush=True)

prev_ev = None
for line in open(json_file):
    ev = json.loads(line.strip())
    if prev_ev is not None:
        report(prev_ev)
        time.sleep(min((time_for_entry(ev) - time_for_entry(prev_ev)), 8)/scale_factor)
    prev_ev = ev
report(prev_ev)
