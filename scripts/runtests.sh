#!/bin/bash
set -eux
python3 -m unittest discover
export SUBIQUITY_REPLAY_TIMESCALE=100
for answers in examples/answers*.yaml; do
    rm -f .subiquity/subiquity-curtin-install.conf
    # The --foreground is important to avoid subiquity getting SIGTTOU-ed.
    timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --answers $answers --dry-run --machine-config examples/mwhudson.json"
    python3 scripts/validate-yaml.py .subiquity/subiquity-curtin-install.conf
done
