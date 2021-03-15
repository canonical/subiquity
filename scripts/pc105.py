# Copyright 2018 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# The keyboard autodetection process is driven by the data in
# /usr/share/console-setup/pc105.tree. This code parses that data into
# subclasses of Step.

"""Parses the pc105.tree file into Steps"""

from subiquity.common.types import (
    StepKeyPresent,
    StepPressKey,
    StepResult,
    )


class PC105Tree:
    # This is adapted (quite heavily) from the code in ubiquity.

    def __init__(self):
        self.steps = {}

    def _add_step_from_lines(self, lines):
        step_cls = None
        args = None
        step_index = None
        for line in lines:
            if line.startswith('STEP '):
                step_index = line[5:].strip()
            elif line.startswith('PRESS '):
                # Ask the user to press a character on the keyboard.
                if step_cls is None:
                    step_cls = StepPressKey
                    args = {
                        'symbols': [],
                        'keycodes': {},
                        }
                elif step_cls is not StepPressKey:
                    raise Exception
                args['symbols'].append(line[6:].strip())
            elif line.startswith('CODE '):
                # Direct the evaluating code to process step ## next if the
                # user has pressed a key which returned that keycode.
                if step_cls is not StepPressKey:
                    raise Exception
                keycode = int(line[5:line.find(' ', 5)])
                s = line[line.find(' ', 5) + 1:].strip()
                args['keycodes'][keycode] = s
            elif line.startswith('FIND '):
                # Ask the user whether that character is present on their
                # keyboard.
                if step_cls is None:
                    step_cls = StepKeyPresent
                    args = {
                        'symbol': line[5:].strip(),
                        }
                else:
                    raise Exception
            elif line.startswith('FINDP '):
                # Equivalent to FIND, except that the user is asked to consider
                # only the primary symbols (i.e. Plain and Shift).
                if step_cls is None:
                    step_cls = StepKeyPresent
                    args = {'symbol': line[5:].strip()}
                else:
                    raise Exception
            elif line.startswith('YES '):
                # Direct the evaluating code to process step ## next if the
                # user does have this key.
                if step_cls is not StepKeyPresent:
                    raise Exception
                args['yes'] = line[4:].strip()
            elif line.startswith('NO '):
                # Direct the evaluating code to process step ## next if the
                # user does not have this key.
                if step_cls is not StepKeyPresent:
                    raise Exception
                args['no'] = line[3:].strip()
            elif line.startswith('MAP '):
                # This step uniquely identifies a keymap.
                if step_cls is None:
                    step_cls = StepResult
                    arg = line[4:].strip()
                    if ':' in arg:
                        layout, variant = arg.split(':')
                    else:
                        layout, variant = arg, ''
                    args = {'layout': layout, 'variant': variant}
                else:
                    raise Exception
            else:
                raise Exception
        if step_cls is None or step_index is None:
            raise Exception
        self.steps[step_index] = step_cls(**args)

    def read_steps(self):
        cur_step_lines = []
        with open('/usr/share/console-setup/pc105.tree') as fp:
            for line in fp:
                if line.startswith('STEP '):
                    if cur_step_lines:
                        self._add_step_from_lines(cur_step_lines)
                    cur_step_lines = [line]
                else:
                    cur_step_lines.append(line)
        if cur_step_lines:
            self._add_step_from_lines(cur_step_lines)
