class KeyboardDetector:
    UNKNOWN, PRESS_KEY, KEY_PRESENT, KEY_PRESENT_P, RESULT = list(range(5))

    def __init__(self):
        self.current_step = -1
        f = '/usr/share/console-setup/pc105.tree'
        self.fp = open(f)

        # Dictionary of keycode -> step.
        self.keycodes = {}
        self.symbols = []
        self.present = -1
        self.not_present = -1
        self.result = ''

    def __del__(self):
        if self.fp:
            self.fp.close()

    def read_step(self, step):
        if self.current_step != -1:
            valid_steps = (
                list(self.keycodes.values()) +
                [self.present] + [self.not_present])
            if step not in valid_steps:
                raise KeyError('invalid argument')
            if self.result:
                raise Exception('already done')

        step_type = KeyboardDetector.UNKNOWN
        self.keycodes = {}
        self.symbols = []
        self.present = -1
        self.not_present = -1
        self.result = ''

        for line in self.fp:
            if line.startswith('STEP '):
                # This line starts a new step.
                if self.current_step == step:
                    self.current_step = int(line[5:])
                    return step_type
                else:
                    self.current_step = int(line[5:])
            elif self.current_step != step:
                continue
            elif line.startswith('PRESS '):
                # Ask the user to press a character on the keyboard.
                if step_type == KeyboardDetector.UNKNOWN:
                    step_type = KeyboardDetector.PRESS_KEY
                if step_type != KeyboardDetector.PRESS_KEY:
                    raise Exception
                self.symbols.append(line[6:].strip())
            elif line.startswith('CODE '):
                # Direct the evaluating code to process step ## next if the
                # user has pressed a key which returned that keycode.
                if step_type != KeyboardDetector.PRESS_KEY:
                    raise Exception
                keycode = int(line[5:line.find(' ', 5)])
                s = int(line[line.find(' ', 5) + 1:])
                self.keycodes[keycode] = s
            elif line.startswith('FIND '):
                # Ask the user whether that character is present on their
                # keyboard.
                if step_type == KeyboardDetector.UNKNOWN:
                    step_type = KeyboardDetector.KEY_PRESENT
                else:
                    raise Exception
                self.symbols = [line[5:].strip()]
            elif line.startswith('FINDP '):
                # Equivalent to FIND, except that the user is asked to consider
                # only the primary symbols (i.e. Plain and Shift).
                if step_type == KeyboardDetector.UNKNOWN:
                    step_type = KeyboardDetector.KEY_PRESENT_P
                else:
                    raise Exception
                self.symbols = [line[6:].strip()]
            elif line.startswith('YES '):
                # Direct the evaluating code to process step ## next if the
                # user does have this key.
                if (step_type != KeyboardDetector.KEY_PRESENT_P and
                        step_type != KeyboardDetector.KEY_PRESENT):
                    raise Exception
                self.present = int(line[4:].strip())
            elif line.startswith('NO '):
                # Direct the evaluating code to process step ## next if the
                # user does not have this key.
                if (step_type != KeyboardDetector.KEY_PRESENT_P and
                        step_type != KeyboardDetector.KEY_PRESENT):
                    raise Exception
                self.not_present = int(line[3:].strip())
            elif line.startswith('MAP '):
                # This step uniquely identifies a keymap.
                if step_type == KeyboardDetector.UNKNOWN:
                    step_type = KeyboardDetector.RESULT
                self.result = line[4:].strip()
                return step_type
            else:
                raise Exception
