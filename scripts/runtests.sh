#!/bin/bash
set -eux

testschema=.subiquity/test-autoinstall-schema.json
export PYTHONPATH=$PWD:$PWD/probert:$PWD/curtin

RELEASE=$(lsb_release -rs)

validate () {
    mode="install"
    [ $# -gt 0 ] && mode="$1"

    if [ -d .subiquity/var/crash -a -n "$(ls -A .subiquity/var/crash)" ] ; then
        echo "subiquity crashed"
        exit 1
    fi

    if [ "${mode}" = "install" ]; then
        python3 scripts/validate-yaml.py .subiquity/var/log/installer/subiquity-curtin-install.conf
        if [ ! -e .subiquity/subiquity-client-debug.log ] || [ ! -e .subiquity/subiquity-server-debug.log ]; then
            echo "log file not created"
            exit 1
        fi
        python3 scripts/validate-autoinstall-user-data.py < .subiquity/var/log/installer/autoinstall-user-data
        if grep passw0rd .subiquity/subiquity-client-debug.log .subiquity/subiquity-server-debug.log | grep -v "Loaded answers" | grep -v "answers_action"; then
            echo "password leaked into log file"
            exit 1
        fi
        netplan generate --root .subiquity
    elif [ "${mode}" = "system_setup" ]; then
        setup_mode="$2"
        launcher_cmds=".subiquity/run/launcher-command"
        echo "system setup validation for $setup_mode"
        echo "checking ${launcher_cmds}"
        if [ ! -f ${launcher_cmds} ]; then
            echo "Expected launcher commands to be written to the file."
            exit 1
        elif [ -z "$(grep action ${launcher_cmds})" ] && [ "${setup_mode}" != "autoinstall-no-shutdown" ]; then
            echo "Expected action to be set in launcher commands."
            exit 1
        elif [ -z "$(grep defaultUid ${launcher_cmds})" ] && [ "${setup_mode}" != "answers-reconf" ]; then
            echo "Expected defaultUid to be set in launcher commands."
            exit 1
        else
            cat ${launcher_cmds}
        fi
        expected_status="reboot"
        if [ "${setup_mode}" = "autoinstall-full" ]; then
            expected_status="shutdown"
        elif [ "${setup_mode}" = "autoinstall-no-shutdown" ]; then
            expected_status=""
        fi
        result_status="$(cat ${launcher_cmds} | grep action | cut -d = -f 2)"
        if [ "${result_status}" != "${expected_status}" ]; then
            echo "incorrect ${launcher_cmds}: expect ${expected_status}, got ${result_status}"
            exit 1
        fi
        echo "checking generated config"
        [ -d ".subiquity/etc/" ] || (echo "etc/ dir not created for config"; exit 1)
        if [ "${setup_mode}" = "autoinstall-no-shutdown" ]; then
            setup_mode="autoinstall"
        fi
        [ -d "system_setup/tests/golden/${setup_mode}" ] || (echo "tests/golden not found in system_setup"; exit 1)
        for file in system_setup/tests/golden/${setup_mode}/*.conf; do
            filename=$(basename ${file})
            conf_filepath=".subiquity/etc/${filename}"
            diff -NBup "${file}" "${conf_filepath}" || exit 1
        done
        if [ "${setup_mode}" != "answers-reconf" ]; then
            echo "checking user created"
            [ -d ".subiquity/home/" ] || (echo "home/ dir not created for the environment"; exit 1)
            [ -d ".subiquity/home/ubuntu" ] || (echo "home folder not created for the user"; exit 1)
            if grep -v ubuntu .subiquity/etc/passwd ; then
                echo "user definition not included in etc/passwd"
                exit 1
            fi
            if grep -v Ubuntu .subiquity/etc/passwd ; then
                echo "username not added in etc/passwd"
                exit 1
            fi
            if grep -v ubuntu .subiquity/etc/shadow ; then
                echo "user definition not included in etc/shadow"
                exit 1
            fi
            if ! grep -q sudo .subiquity/etc/group ; then
                echo "expected group sudo not included in etc/group"
                exit 1
            fi
            if ! (grep sudo .subiquity/etc/group | grep -q ubuntu) ; then
                echo "user not assigned with the expected group sudo"
                exit 1
            fi
            # Extract value of the LANG variable from etc/default/locale (with or without quotes)
            lang="$(grep -Eo 'LANG=([^.@ _]+)' .subiquity/etc/default/locale | cut -d= -f 2- | cut -d\" -f 2-)"
            if ! ls .subiquity/var/cache/apt/archives/ | grep --fixed-strings --quiet -- "$lang"; then
                echo "expected $lang language packs in directory var/cache/apt/archives/"
                exit 1
            fi
            if [ -z "$( diff -Nup .subiquity/etc/locale.gen .subiquity/etc/locale.gen.test)" ] ; then
                echo "expected changes in etc/locale.gen"
                exit 1
            fi
        fi
    else
        echo "W: Unknown validation mode: ${mode}"
    fi
}

clean () {
    rm -rf .subiquity/var/log/
    rm -f .subiquity/subiquity-*.log
    rm -f "$testschema"
    rm -rf .subiquity/run/
    rm -rf .subiquity/home/
    rm -rf .subiquity/etc/.pwd.lock
    rm -rf .subiquity/etc/default/locale
    rm -rf .subiquity/etc/{locale*,passwd*,shadow*,group*,gshadow*,subgid*,subuid*}
    rm -rf .subiquity/etc/*.conf
    rm -rf .subiquity/etc/cloud/cloud.cfg.d/99-installer.cfg
    rm -rf .subiquity/var/crash
    rm -rf .subiquity/var/cache
    rm -rf .subiquity/run/subiquity/states
}

error () {
    set +x  # show PASS/FAIL as the last line of output
    echo 'Runtests FAILURE'
}

trap error ERR
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
        # The OOBE doesn't exist in WSL < 20.04
        if [ "${RELEASE%.*}" -ge 20 ]; then
            # check if it is reconf
            reconf_settings="false"
            validate_subtype="answers"
            if echo $answers|grep -q reconf; then
                reconf_settings="true"
                validate_subtype="answers-reconf"
            fi
            timeout --foreground 60 sh -c "DRYRUN_RECONFIG=$reconf_settings LANG=C.UTF-8 python3 -m system_setup.cmd.tui --answers $answers --dry-run " < $tty
            validate "system_setup" "$validate_subtype"
        fi
    fi
done

clean
timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --autoinstall examples/autoinstall.yaml \
                               --dry-run --machine-config examples/existing-partitions.json --bootloader bios \
                               --kernel-cmdline 'autoinstall' \
                               --source-catalog=examples/install-sources.yaml"
validate
python3 scripts/check-yaml-fields.py .subiquity/var/log/installer/subiquity-curtin-apt.conf \
        apt.disable_components='[non-free, restricted]' \
        apt.preferences[0].pin-priority=200 \
        apt.preferences[0].pin='"origin *ubuntu.com*"' \
        apt.preferences[1].package='"python-*"' \
        apt.preferences[1].pin-priority=-1
python3 scripts/check-yaml-fields.py .subiquity/var/log/installer/subiquity-curtin-install.conf \
        debconf_selections.subiquity='"eek"' \
        storage.config[-1].options='"errors=remount-ro"'
python3 scripts/check-yaml-fields.py <(python3 scripts/check-yaml-fields.py .subiquity/etc/cloud/cloud.cfg.d/99-installer.cfg datasource.None.userdata_raw) \
        locale='"en_GB.UTF-8"' \
        timezone='"Pacific/Guam"' \
        ubuntu_advantage.token='"C1NWcZTHLteJXGVMM6YhvHDpGrhyy7"' \
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

# The OOBE doesn't exist in WSL < 20.04
if [ "${RELEASE%.*}" -ge 20 ]; then
    for mode in "" "-full" "-no-shutdown"; do
        clean
        timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m system_setup.cmd.tui --autoinstall examples/autoinstall-system-setup${mode}.yaml --dry-run"
        validate "system_setup" "autoinstall${mode}"
    done

    python3 -m system_setup.cmd.schema > "$testschema"
    diff -u "autoinstall-system-setup-schema.json" "$testschema"
fi

python3 -m subiquity.cmd.schema > "$testschema"
diff -u "autoinstall-schema.json" "$testschema"

set +x  # show PASS/FAIL as the last line of output
echo 'Runtests all PASSED'
