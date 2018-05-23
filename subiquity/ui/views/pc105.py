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


class Step:
    def __repr__(self):
        kvs = []
        for k, v in self.__dict__.items():
            kvs.append("%s=%r" % (k, v))
        return "%s(%s)" % (self.__class__.__name__, ", ".join(sorted(kvs)))

    def check(self):
        pass


class StepPressKey(Step):
    # "Press one of the following keys"
    def __init__(self):
        self.symbols = []
        self.keycodes = {}

    def check(self):
        if len(self.symbols) == 0 or len(self.keycodes) == 0:
            raise Exception


class StepKeyPresent(Step):
    # "Is this symbol present on your keyboard"
    def __init__(self, symbol):
        self.symbol = symbol
        self.yes = None
        self.no = None

    def check(self):
        if self.yes is None or self.no is None:
            raise Exception


class StepResult(Step):
    # "This is the autodetected layout"
    def __init__(self, result):
        self.result = result


class PC105Tree:
    """Parses the pc105.tree file into subclasses of Step"""
    # This is adapted (quite heavily) from the code in ubiquity.

    def __init__(self):
        self.steps = {}

    def _add_step_from_lines(self, lines):
        step = None
        step_index = -1
        for line in lines:
            if line.startswith('STEP '):
                step_index = int(line[5:])
            elif line.startswith('PRESS '):
                # Ask the user to press a character on the keyboard.
                if step is None:
                    step = StepPressKey()
                elif not isinstance(step, StepPressKey):
                    raise Exception
                step.symbols.append(line[6:].strip())
            elif line.startswith('CODE '):
                # Direct the evaluating code to process step ## next if the
                # user has pressed a key which returned that keycode.
                if not isinstance(step, StepPressKey):
                    raise Exception
                keycode = int(line[5:line.find(' ', 5)])
                s = int(line[line.find(' ', 5) + 1:])
                step.keycodes[keycode] = s
            elif line.startswith('FIND '):
                # Ask the user whether that character is present on their
                # keyboard.
                if step is None:
                    step = StepKeyPresent(line[5:].strip())
                else:
                    raise Exception
            elif line.startswith('FINDP '):
                # Equivalent to FIND, except that the user is asked to consider
                # only the primary symbols (i.e. Plain and Shift).
                if step is None:
                    step = StepKeyPresent(line[6:].strip())
                else:
                    raise Exception
            elif line.startswith('YES '):
                # Direct the evaluating code to process step ## next if the
                # user does have this key.
                if not isinstance(step, StepKeyPresent):
                    raise Exception
                step.yes = int(line[4:].strip())
            elif line.startswith('NO '):
                # Direct the evaluating code to process step ## next if the
                # user does not have this key.
                if not isinstance(step, StepKeyPresent):
                    raise Exception
                step.no = int(line[3:].strip())
            elif line.startswith('MAP '):
                # This step uniquely identifies a keymap.
                if step is None:
                    step = StepResult(line[4:].strip())
                else:
                    raise Exception
            else:
                raise Exception
        if step is None or step_index == -1:
            raise Exception
        step.check()
        self.steps[step_index] = step

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
