#!/usr/bin/python3

# This is just a helper script to generate lszdev commands
# later will use this more for "help" and description stuff

import subprocess
import shlex
columns=subprocess.check_output(['lszdev', '--pairs', '--list-columns'], universal_newlines=True)
rows = [shlex.split(i) for i in columns.splitlines()]
desired_columns=[]
for row in rows:
    record = dict([k.split('=',1) for k in row])
    if record['COLUMN'] not in ('TYPE', 'ATTR:', 'ATTRPATH:'):
        desired_columns.append(record['COLUMN'].lower())
cmd = ['lszdev', '--quiet', '--pairs','--columns',','.join(desired_columns)]
print(cmd)
print(' '.join(cmd))
