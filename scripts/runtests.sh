#!/bin/bash
set -eux

testschema=.subiquity/test-autoinstall-schema.json
export PYTHONPATH=$PWD:$PWD/probert:$PWD/curtin

validate () {
    mode="install"
    [ $# -gt 0 ] && mode="$1"

    if [ "${mode}" = "install" ]; then
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
    elif [ "${mode}" = "system_setup" ]; then
        # TODO WSL: Compare generated wsl.conf to oracle
        echo "system setup validation"
    else
        echo "W: Unknown validation mode: ${mode}"
    fi
}

clean () {
    rm -f .subiquity/subiquity-curtin-install.conf
    rm -f .subiquity/subiquity-*.log
    rm -f "$testschema"
    rm -rf .subiquity/run/
    rm -rf .subiquity/etc/cloud/cloud.cfg.d/99-installer.cfg
    jobslist="$(jobs -p)"
    if [ -n "$jobslist" ] ; then
        kill $jobslist
    fi
}

scurl () {
    curl --unix-socket .subiquity/socket $*
}

error () {
    set +x  # show PASS/FAIL as the last line of output
    echo 'Runtests FAILURE'
}

trap error ERR
trap clean EXIT
tty=$(tty) || tty=/dev/console

export SUBIQUITY_REPLAY_TIMESCALE=100
for answers in examples/answers*.yaml; do
    clean
    if echo $answers|grep -vq system-setup; then
        config=$(sed -n 's/^#machine-config: \(.*\)/\1/p' $answers || true)
        if [ -z "$config" ]; then
            config=examples/simple.json
        fi
        serial=$(sed -n 's/^#serial/x/p' $answers || true)
        opts=''
        if [ -n "$serial" ]; then
            opts='--serial'
        fi
        # The --foreground is important to avoid subiquity getting SIGTTOU-ed.
        timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --bootloader uefi --answers $answers --dry-run --snaps-from-examples --machine-config $config $opts" < $tty
        validate
        grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing security updates' .subiquity/subiquity-server-debug.log
    else
        timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m system_setup.cmd.tui --answers $answers --dry-run " < $tty
        validate "system_setup"
    fi
done

clean
timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --autoinstall examples/autoinstall.yaml \
                               --dry-run --machine-config examples/existing-partitions.json --bootloader bios \
                               --kernel-cmdline 'autoinstall'"
validate
python3 scripts/check-yaml-fields.py .subiquity/subiquity-curtin-install.conf \
        debconf_selections.subiquity='"eek"' \
        storage.config[-1].options='"errors=remount-ro"'
python3 scripts/check-yaml-fields.py <(python3 scripts/check-yaml-fields.py .subiquity/etc/cloud/cloud.cfg.d/99-installer.cfg datasource.None.userdata_raw) \
        locale='"en_GB.UTF-8"' \
        timezone='"Pacific/Guam"' \
        'snap.commands=[snap install --channel=3.2/stable etcd]'
grep -q 'finish: subiquity/Install/install/postinstall/install_package1: SUCCESS: installing package1' \
     .subiquity/subiquity-server-debug.log
grep -q 'finish: subiquity/Install/install/postinstall/install_package2: SUCCESS: installing package2' \
     .subiquity/subiquity-server-debug.log
grep -q 'switching subiquity to edge' .subiquity/subiquity-server-debug.log
grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing all updates' \
    .subiquity/subiquity-server-debug.log

clean
timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --autoinstall examples/autoinstall-user-data.yaml \
                               --dry-run --machine-config examples/simple.json --kernel-cmdline 'autoinstall'"
validate
grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing security updates' .subiquity/subiquity-server-debug.log

timeout 30 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.server --dry-run --bootloader uefi --machine-config examples/win10.json" &
while ! scurl a/meta/status >& /dev/null ; do
    sleep .5
done
scurl a/storage/has_bitlocker | jq -M '. [0].partitions[2]' | grep -q BitLocker

# NOTE:
# This test doesnt do much ATM but it will be useful when we have more complex scenarios to test with the server and client code.
# Like generating a wsl.conf file and comparing it to the oracle.
clean
timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m system_setup.cmd.tui --autoinstall examples/autoinstall-system-setup.yaml --dry-run"

python3 -m subiquity.cmd.schema > "$testschema"
scripts/schema-cmp.py "autoinstall-schema.json" "$testschema"

python3 -m system_setup.cmd.schema > "$testschema"
scripts/schema-cmp.py "autoinstall-system-setup-schema.json" "$testschema" --ignore-tz

set +x  # show PASS/FAIL as the last line of output
echo 'Runtests all PASSED'
