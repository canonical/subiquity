#!/bin/bash
set -eux

export PYTHONPATH=$PWD:$PWD/probert:$PWD/curtin

RELEASE=$(lsb_release -rs)

tmpdir=$(mktemp -d)
subiquity_pid=""

validate () {
    mode="install"
    [ $# -gt 0 ] && mode="$1"

    if [ -d $tmpdir/var/crash -a -n "$(ls -A $tmpdir/var/crash)" ] ; then
        echo "error: subiquity crashed"
        exit 1
    fi

    if [ -s $tmpdir/server-stderr ]; then
        echo "error: unexpected output on stderr"
        cat $tmpdir/server-stderr
        exit 1
    fi

    if [ "${mode}" = "install" ]; then
        cfgs=()
        for stage in partitioning formatting; do
            cfg="$tmpdir"/var/log/installer/curtin-install/subiquity-$stage.conf
            if [ -e "$cfg" ]; then
                cfgs+=("$cfg")
            fi
        done
        python3 scripts/validate-yaml.py "${cfgs[@]}"
        if [ ! -e $tmpdir/subiquity-client-debug.log ] || [ ! -e $tmpdir/subiquity-server-debug.log ]; then
            echo "log file not created"
            exit 1
        fi
        python3 scripts/validate-autoinstall-user-data.py < $tmpdir/var/log/installer/autoinstall-user-data
        if grep passw0rd $tmpdir/subiquity-client-debug.log $tmpdir/subiquity-server-debug.log | grep -v "Loaded answers" | grep -v "answers_action"; then
            echo "password leaked into log file"
            exit 1
        fi
        netplan generate --root $tmpdir
    elif [ "${mode}" = "system_setup" ]; then
        setup_mode="$2"
        launcher_cmds="$tmpdir/run/launcher-command"
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
        [ -d "$tmpdir/etc/" ] || (echo "etc/ dir not created for config"; exit 1)
        if [ "${setup_mode}" = "autoinstall-no-shutdown" ]; then
            setup_mode="autoinstall"
        fi
        [ -d "system_setup/tests/golden/${setup_mode}" ] || (echo "tests/golden not found in system_setup"; exit 1)
        for file in system_setup/tests/golden/${setup_mode}/*.conf; do
            filename=$(basename ${file})
            conf_filepath="$tmpdir/etc/${filename}"
            diff -NBup "${file}" "${conf_filepath}" || exit 1
        done
        if [ "${setup_mode}" != "answers-reconf" ]; then
            echo "checking user created"
            [ -d "$tmpdir/home/" ] || (echo "home/ dir not created for the environment"; exit 1)
            [ -d "$tmpdir/home/ubuntu" ] || (echo "home folder not created for the user"; exit 1)
            if grep -v ubuntu $tmpdir/etc/passwd ; then
                echo "user definition not included in etc/passwd"
                exit 1
            fi
            if grep -v Ubuntu $tmpdir/etc/passwd ; then
                echo "username not added in etc/passwd"
                exit 1
            fi
            if grep -v ubuntu $tmpdir/etc/shadow ; then
                echo "user definition not included in etc/shadow"
                exit 1
            fi
            if ! grep -q sudo $tmpdir/etc/group ; then
                echo "expected group sudo not included in etc/group"
                exit 1
            fi
            if ! (grep sudo $tmpdir/etc/group | grep -q ubuntu) ; then
                echo "user not assigned with the expected group sudo"
                exit 1
            fi
            # Extract value of the LANG variable from etc/default/locale (with or without quotes)
            lang="$(grep -Eo 'LANG=([^.@ _]+)' $tmpdir/etc/default/locale | cut -d= -f 2- | cut -d\" -f 2-)"
            if ! ls $tmpdir/var/cache/apt/archives/*.log | grep --fixed-strings --quiet -- "$lang"; then
                echo "expected $lang language packs in directory var/cache/apt/archives/"
                exit 1
            fi
            for f in $tmpdir/var/cache/apt/archives/*.log ; do
                if ! [ -s $f ]; then
                    echo "apt failed for package $f"
                    exit 1
                fi
            done
            if [ -z "$( diff -Nup $tmpdir/etc/locale.gen $tmpdir/etc/locale.gen.test)" ] ; then
                echo "expected changes in etc/locale.gen"
                exit 1
            fi
        fi
    else
        echo "W: Unknown validation mode: ${mode}"
    fi
}

clean () {
    [ -d "$tmpdir" ] && rm -fr $tmpdir
    tmpdir=$(mktemp -d)
}

on_exit () {
    ec=$?
    set +xe  # show PASS/FAIL in the last lines of output
    if [[ $ec = 0 ]] ; then
        echo 'Runtests all PASSED'
    else
        echo 'Runtests FAILURE'
        echo "Output from the last run is at $tmpdir"
    fi

    if [ -n "$subiquity_pid" ] ; then
        kill "$subiquity_pid"
    fi

    exit $ec
}

trap on_exit EXIT
tty=$(tty) || tty=/dev/console

export SUBIQUITY_REPLAY_TIMESCALE=100

for answers in examples/answers*.yaml; do
    if echo $answers|grep -vq system-setup; then
        config=$(sed -n 's/^#machine-config: \(.*\)/\1/p' $answers || true)
        catalog=$(sed -n 's/^#source-catalog: \(.*\)/\1/p' $answers || true)
        dr_config=$(sed -n 's/^#dr-config: \(.*\)/\1/p' "$answers" || true)
        if [ -z "$config" ]; then
            config=examples/simple.json
        fi
        if [ -z "$catalog" ]; then
            catalog=examples/install-sources.yaml
        fi
        serial=$(sed -n 's/^#serial/x/p' $answers || true)
        opts=()
        if [ -n "$serial" ]; then
            opts+=(--serial)
        fi
        if [ -n "$dr_config" ]; then
            opts+=(--dry-run-config "$dr_config")
        fi
        # The --foreground is important to avoid subiquity getting SIGTTOU-ed.
        ./scripts/background-runner -l $tmpdir/tui.log \
            env LANG=C.UTF-8 \
            timeout --foreground 60 \
            python3 -m subiquity.cmd.tui \
            --dry-run \
            --output-base "$tmpdir" \
            --answers "$answers" \
            "${opts[@]}" \
            --machine-config "$config" \
            --bootloader uefi \
            --snaps-from-examples \
            --source-catalog $catalog
        validate install
        grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing security updates' $tmpdir/subiquity-server-debug.log
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
            ./scripts/background-runner -l $tmpdir/tui.log \
                env DRYRUN_RECONFIG="$reconf_settings" LANG=C.UTF-8 \
                timeout --foreground 60 \
                python3 -m system_setup.cmd.tui \
                --dry-run \
                --answers "$answers" \
                --output-base "$tmpdir"
            validate "system_setup" "$validate_subtype"
        fi
    fi
    clean
done

./scripts/background-runner -l $tmpdir/tui.log \
    env LANG=C.UTF-8 \
    timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/existing-partitions.json \
    --bootloader bios \
    --autoinstall examples/autoinstall.yaml \
    --dry-run-config examples/dr-config-apt-local-mirror.yaml \
    --kernel-cmdline autoinstall \
    --source-catalog examples/install-sources.yaml
validate
python3 scripts/check-yaml-fields.py $tmpdir/var/log/installer/subiquity-curtin-apt.conf \
        apt.disable_components='[non-free, restricted]' \
        apt.preferences[0].pin-priority=200 \
        apt.preferences[0].pin='"origin *ubuntu.com*"' \
        apt.preferences[1].package='"python-*"' \
        apt.preferences[1].pin-priority=-1 \
        apt.debconf_selections.subiquity='"eek"'
python3 scripts/check-yaml-fields.py "$tmpdir"/var/log/installer/curtin-install/subiquity-curthooks.conf \
        storage.config[-1].options='"errors=remount-ro"'
python3 scripts/check-yaml-fields.py <(python3 scripts/check-yaml-fields.py $tmpdir/etc/cloud/cloud.cfg.d/99-installer.cfg datasource.None.userdata_raw) \
        locale='"en_GB.UTF-8"' \
        timezone='"Pacific/Guam"' \
        ubuntu_advantage.token='"C1NWcZTHLteJXGVMM6YhvHDpGrhyy7"' \
        'snap.commands=[snap install --channel=3.2/stable etcd]'
grep -q 'finish: subiquity/Install/install/postinstall/install_package1: SUCCESS: installing package1' \
     $tmpdir/subiquity-server-debug.log
grep -q 'finish: subiquity/Install/install/postinstall/install_package2: SUCCESS: installing package2' \
     $tmpdir/subiquity-server-debug.log
grep -q 'switching subiquity to edge' $tmpdir/subiquity-server-debug.log
grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing all updates' \
    $tmpdir/subiquity-server-debug.log

clean
./scripts/background-runner -l $tmpdir/tui.log \
    env LANG=C.UTF-8 \
    timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/simple.json \
    --autoinstall examples/autoinstall-user-data.yaml \
    --kernel-cmdline autoinstall \
    --source-catalog examples/install-sources.yaml
validate
python3 scripts/check-yaml-fields.py "$tmpdir"/var/log/installer/autoinstall-user-data \
        'autoinstall.source.id="ubuntu-server-minimal"'
grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing security updates' $tmpdir/subiquity-server-debug.log

# The OOBE doesn't exist in WSL < 20.04
if [ "${RELEASE%.*}" -ge 20 ]; then
    # Test TCP connectivity (system_setup only)
    clean
    port=50321
    LANG=C.UTF-8 python3 -m system_setup.cmd.server --dry-run --tcp-port=$port &
    subiquity_pid=$!
    next_time=10
    until [ $next_time -eq 0 ] || [ ! -z "$(ss -Hlt sport = $port)" ]; do
        sleep $(( next_time-- ))
    done
    if [ $next_time -eq 0 ]; then
        echo "Timeout reached before Subiquity TCP socket started listening"
        exit 1
    fi

    scripts/test-system-setup-loopback-only.py --port "$port" --debug

    # Test system_setup autoinstall.
    for mode in "" "-full" "-no-shutdown"; do
        clean
        ./scripts/background-runner -l $tmpdir/tui.log \
            env LANG=C.UTF-8 \
            timeout --foreground 60 \
            python3 -m system_setup.cmd.tui \
            --dry-run \
            --output-base "$tmpdir" \
            --autoinstall "examples/autoinstall-system-setup${mode}.yaml"
        validate "system_setup" "autoinstall${mode}"
    done

    python3 -m system_setup.cmd.schema > $tmpdir/test-schema.json
    diff -u "autoinstall-system-setup-schema.json" $tmpdir/test-schema.json
fi

python3 -m subiquity.cmd.schema > $tmpdir/test-schema.json
diff -u "autoinstall-schema.json" $tmpdir/test-schema.json

clean
