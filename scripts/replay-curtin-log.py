#!/usr/bin/python3

import json
import logging
import os
import sys
import time

from curtin import reporter
from curtin.reporter import events

logger = logging.getLogger('')
logger.setLevel('DEBUG')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(name)s:%(lineno)d %(message)s"))
logger.addHandler(handler)

json_file = sys.argv[1]

c = {'subiquity': {'type': 'journald', 'identifier': sys.argv[2]}, 'print': {'type': 'print'}}

reporter.update_configuration(c)

## ev_dict = {
##     "origin": "curtin",
##     "event_type": "start",
##     "level": "DEBUG",
##     "timestamp": 1505187478.3402257,
##     "name": "cmd-install",
##     "description": "curtin command install"
##     }

class FakeEvent:
    def __init__(self, ev_dict):
        self._ev_dict = ev_dict
        for k, v in ev_dict.items():
            setattr(self, k, v)
    def as_string(self):
        return '{0}: {1}: {2}'.format(
            self._ev_dict['event_type'], self._ev_dict['name'], self._ev_dict['description'])
    def as_dict(self):
        return self._ev_dict

scale_factor = float(os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "4"))

prev_ev = None
for line in open(json_file):
    d = json.loads(line.strip())
    ev = FakeEvent(d)
    if prev_ev is not None:
        events.report_event(prev_ev)
        time.sleep(min((ev.timestamp - prev_ev.timestamp), 8)/scale_factor)
    prev_ev = ev
events.report_event(prev_ev)
