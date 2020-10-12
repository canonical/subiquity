#!/bin/bash
set -eux
python3 -m unittest discover

validate () {
    python3 scripts/validate-yaml.py .subiquity/subiquity-curtin-install.conf
    if [ ! -e .subiquity/subiquity-client-debug.log ] || [ ! -e .subiquity/subiquity-server-debug.log ]; then
        echo "log file not created"
        exit 1
    fi
    if grep passw0rd .subiquity/subiquity-client-debug.log .subiquity/subiquity-server-debug.log | grep -v "Loaded answers" | grep -v "answers_action"; then
        echo "password leaked into log file"
        exit 1
    fi
    netplan generate --root .subiquity
}

clean () {
    rm -f .subiquity/subiquity-curtin-install.conf
    rm -f .subiquity/subiquity-*.log
    rm -rf .subiquity/run/
}

export SUBIQUITY_REPLAY_TIMESCALE=100
for answers in examples/answers*.yaml; do
    clean
    config=$(sed -n 's/^#machine-config: \(.*\)/\1/p' $answers || true)
    if [ -z "$config" ]; then
        config=examples/simple.json
    fi
    # The --foreground is important to avoid subiquity getting SIGTTOU-ed.
    timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --answers $answers --dry-run --snaps-from-examples --machine-config $config"
    validate
done

clean
timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --autoinstall examples/autoinstall.yaml \
                               --dry-run --machine-config examples/existing-partitions.json --bootloader bios \
                               --kernel-cmdline 'autoinstall'"
validate
python3 scripts/check-yaml-fields.py .subiquity/subiquity-curtin-install.conf \
        debconf_selections.subiquity='"eek"'
python3 scripts/check-yaml-fields.py <(python3 scripts/check-yaml-fields.py .subiquity/etc/cloud/cloud.cfg.d/99-installer.cfg datasource.None.userdata_raw) \
        locale='"en_GB.UTF-8"'
grep -q 'finish: subiquity/Install/install/postinstall/install_package1: SUCCESS: installing package1' \
     .subiquity/subiquity-server-debug.log
grep -q 'finish: subiquity/Install/install/postinstall/install_package2: SUCCESS: installing package2' \
     .subiquity/subiquity-server-debug.log
grep -q 'switching subiquity to edge' .subiquity/subiquity-server-debug.log

clean
timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --autoinstall examples/autoinstall-user-data.yaml \
                               --dry-run --machine-config examples/simple.json --kernel-cmdline 'autoinstall'"
validate
