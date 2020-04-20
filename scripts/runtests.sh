#!/bin/bash
set -eux
python3 -m unittest discover
export SUBIQUITY_REPLAY_TIMESCALE=100
for answers in examples/answers*.yaml; do
    rm -f .subiquity/subiquity-curtin-install.conf
    rm -f .subiquity/subiquity-debug.log
    rm -f .subiquity/run/subiquity/updating
    config=$(sed -n 's/^#machine-config: \(.*\)/\1/p' $answers || true)
    if [ -z "$config" ]; then
        config=examples/simple.json
    fi
    # The --foreground is important to avoid subiquity getting SIGTTOU-ed.
    timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --answers $answers --dry-run --snaps-from-examples --machine-config $config"
    python3 scripts/validate-yaml.py .subiquity/subiquity-curtin-install.conf
    if [ ! -e .subiquity/subiquity-debug.log ]; then
        echo "log file not created"
        exit 1
    fi
    if grep passw0rd .subiquity/subiquity-debug.log | grep -v "Loaded answers" | grep -v "answers_action"; then
        echo "password leaked into log file"
        exit 1
    fi
done
TTY=$(tty || true)
timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --autoinstall examples/autoinstall.yaml \
                               --dry-run --machine-config examples/simple.json \
                               --kernel-cmdline 'autoinstall console=\"${TTY#/dev/}\"'"
python3 scripts/validate-yaml.py .subiquity/subiquity-curtin-install.conf
python3 scripts/check-yaml-fields.py .subiquity/subiquity-curtin-install.conf \
        debconf_selections.subiquity='"eek"'
python3 scripts/check-yaml-fields.py .subiquity/var/lib/cloud/seed/nocloud-net/user-data \
        locale='"en_UK.UTF-8"'
grep -q 'finish: subiquity/InstallProgress/postinstall/install_package1: SUCCESS: installing package1' \
     .subiquity/subiquity-debug.log
grep -q 'finish: subiquity/InstallProgress/postinstall/install_package2: SUCCESS: installing package2' \
     .subiquity/subiquity-debug.log
grep -q 'switching subiquity to edge' .subiquity/subiquity-debug.log

timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --autoinstall examples/autoinstall-user-data.yaml \
                               --dry-run --machine-config examples/simple.json \
                               --kernel-cmdline 'autoinstall console=\"${TTY#/dev/}\"'"
python3 scripts/validate-yaml.py .subiquity/subiquity-curtin-install.conf
