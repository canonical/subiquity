#!/bin/bash
python3 -m unittest discover
# The --foreground is important to avoid subiquity getting SIGTTOU-ed.
timeout --foreground 60 sh -c 'LANG=C.UTF-8 PYTHONPATH=. python3 bin/subiquity-tui --answers examples/answers.yaml --dry-run --machine-config examples/mwhudson.json'
