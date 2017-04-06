#!/usr/bin/python3
'''
Mountall apport hook.
'''

import apport.hookutils
import glob

paths = ['/var/log/installer/*', '/root/curtin-*']

def add_info(report, ui):
    for path in paths:
        for f in glob.glob(path):
            apport.hookutils.attach_file(report, f)

