#!/usr/bin/python3

import json
import logging
import random
import sys
import time

from curtin import reporter
from curtin.reporter import events

url = sys.argv[1]

logger = logging.getLogger('')
logger.setLevel('DEBUG')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(name)s:%(lineno)d %(message)s"))
logger.addHandler(handler)

json_file = sys.argv[2]

c = {'subiquity': {'type': 'webhook', 'endpoint': url}, 'print': {'type': 'print'}}

reporter.update_configuration(c)

ev_dict = {"origin": "curtin", "event_type": "start", "level": "DEBUG", "timestamp": 1505187478.3402257, "name": "cmd-install", "description": "curtin command install"}

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

for line in open(json_file):
    d = json.loads(line.strip())
    ev = FakeEvent(d)
    events.report_event(ev)
    time.sleep(random.expovariate(2))
