#!/usr/bin/python3

""" Script that replays curtin events from a journald export.
curtin events are injected back in journald and log lines are written to a log
file. """

import argparse
import json
import os
import sys
import time
from typing import TextIO

from systemd import journal

scale_factor = float(os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "4"))

def time_for_entry(e):
    return int(e['__MONOTONIC_TIMESTAMP'])/1e6

rc = 0

def report(e, log_file: TextIO, event_identifier: str):
    global rc
    if e['SYSLOG_IDENTIFIER'].startswith("curtin_event"):
        e['SYSLOG_IDENTIFIER'] = event_identifier
        e['CODE_LINE'] = int(e['CODE_LINE'])
        journal.send(**e)
        r = e.get("CURTIN_RESULT")
        if r == "SUCCESS":
            rc = 0
        elif r == "FAIL":
            rc = 1
    elif e['SYSLOG_IDENTIFIER'].startswith("curtin_log") and scale_factor < 10:
        log_file.write(e['MESSAGE'] + '\n')


def main() -> int:
    """ Entry point. """
    parser = argparse.ArgumentParser()

    parser.add_argument("replay-file")
    parser.add_argument("--event-identifier", required=True)
    parser.add_argument("--output", type=argparse.FileType("w"), default="-")

    args = vars(parser.parse_args())

    prev_ev = None
    for line in open(args["replay-file"]):
        ev = json.loads(line.strip())
        if prev_ev is not None:
            report(prev_ev, args["output"],
                   event_identifier=args["event_identifier"])
            delay = time_for_entry(ev) - time_for_entry(prev_ev)
            time.sleep(min(delay, 8)/scale_factor)
        prev_ev = ev
    report(ev, args["output"], event_identifier=args["event_identifier"])
    return rc


if __name__ == "__main__":
    sys.exit(main())
