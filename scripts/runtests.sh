#!/bin/bash
set -eux

export PYTHONPATH=$PWD:$PWD/probert:$PWD/curtin

RELEASE=$(lsb_release -rs)

tmpdir=$(mktemp -d)
subiquity_pid=""

validate () {
    if [ -d $tmpdir/var/crash -a -n "$(ls -A $tmpdir/var/crash)" ] ; then
        echo "error: subiquity crashed"
        exit 1
    fi

    if [ -s $tmpdir/server-stderr ]; then
        echo "error: unexpected output on stderr"
        cat $tmpdir/server-stderr
        exit 1
    fi

    cfgs=()
    for stage in partitioning formatting; do
        cfg="$tmpdir"/var/log/installer/curtin-install/subiquity-$stage.conf
        if [ -e "$cfg" ]; then
            cfgs+=("$cfg")
        fi
    done
    if grep passw0rd $tmpdir/subiquity-client-debug.log $tmpdir/subiquity-server-debug.log | grep -v "Loaded answers" | grep -v "answers_action"; then
        echo "password leaked into log file"
        exit 1
    fi
    case $testname in
        autoinstall-reset-only)
            python3 scripts/validate-yaml.py --no-root-mount "${cfgs[@]}"
            ;;
        answers-core-desktop|answers-uc24)
            ;;
        *)
            python3 scripts/validate-yaml.py "${cfgs[@]}"
            ;;
    esac
    if [ ! -e $tmpdir/subiquity-client-debug.log ] || [ ! -e $tmpdir/subiquity-server-debug.log ]; then
        echo "log file not created"
        exit 1
    fi
    case $testname in
        answers-core-desktop|answers-uc24)
            ;;
        answers-bridge)
            python3 scripts/check-yaml-fields.py $tmpdir/var/log/installer/curtin-install/subiquity-curthooks.conf \
                    kernel.package="linux-generic-brg-22.04"
            ;;
        *)
            python3 scripts/validate-autoinstall-user-data.py --legacy --check-link < $tmpdir/var/log/installer/autoinstall-user-data
            # After the lunar release and the introduction of mirror testing, it
            # came to our attention that new Ubuntu installations have the security
            # repository configured with the primary mirror URL (i.e.,
            # http://<cc>.archive.ubuntu.com/ubuntu) instead of
            # http://security.ubuntu.com/ubuntu. Let's ensure we instruct curtin
            # not to do that.
            # If we run an autoinstall that customizes the security section as part
            # of the test-suite, we will need to adapt this test.
            python3 scripts/check-yaml-fields.py $tmpdir/var/log/installer/curtin-install/subiquity-curtin-apt.conf \
                apt.security[0].uri='"http://security.ubuntu.com/ubuntu/"' \
                apt.security[0].arches='["amd64", "i386"]' \
                apt.security[1].uri='"http://ports.ubuntu.com/ubuntu-ports"'
            ;;
    esac
    if [ "$testname" == autoinstall-fallback-offline ]; then
        grep -F -- 'skipping installation of package ubuntu-restricted-addons' "$tmpdir"/subiquity-server-debug.log
    fi
    netplan generate --root $tmpdir
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
        if [ -n "${GITHUB_ACTIONS:-}" -a -d $tmpdir/var/crash -a -n "$(ls -A $tmpdir/var/crash)" ] ; then
            for file in $tmpdir/var/crash/*.crash; do
                echo "--- Start crash file $file ---"
                cat $file
                echo "--- End crash file $file   ---"
            done
        fi
    fi

    if [ -n "$subiquity_pid" ] ; then
        kill "$subiquity_pid"
    fi

    exit $ec
}

trap on_exit EXIT
tty=$(tty) || tty=/dev/console

export SUBIQUITY_REPLAY_TIMESCALE=100

for answers in examples/answers/*.yaml; do
    testname=answers-$(basename $answers .yaml)
    config=$(sed -n 's/^#machine-config: \(.*\)/\1/p' $answers || true)
    catalog=$(sed -n 's/^#source-catalog: \(.*\)/\1/p' $answers || true)
    dr_config=$(sed -n 's/^#dr-config: \(.*\)/\1/p' "$answers" || true)
    if [ -z "$config" ]; then
        config=examples/machines/simple.json
    fi
    if [ -z "$catalog" ]; then
        catalog=examples/sources/install.yaml
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
    LANG=C.UTF-8 timeout --foreground 60 \
        python3 -m subiquity.cmd.tui < "$tty" \
        --dry-run \
        --output-base "$tmpdir" \
        --answers "$answers" \
        "${opts[@]}" \
        --machine-config "$config" \
        --bootloader uefi \
        --snaps-from-examples \
        --source-catalog $catalog
    validate install
    case $testname in
        answers-core-desktop|answers-uc24)
            ;;
        *)
            grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing security updates' $tmpdir/subiquity-server-debug.log
            ;;
    esac
    clean
done

testname=autoinstall-most-options
LANG=C.UTF-8 timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/machines/existing-partitions.json \
    --bootloader bios \
    --autoinstall examples/autoinstall/most-options.yaml \
    --dry-run-config examples/dry-run-configs/apt-local-mirror.yaml \
    --kernel-cmdline autoinstall \
    --source-catalog examples/sources/install.yaml
validate
python3 scripts/check-yaml-fields.py $tmpdir/var/log/installer/curtin-install/subiquity-curtin-apt.conf \
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
python3 scripts/check-yaml-fields.py "$tmpdir"/var/log/installer/curtin-install/subiquity-curthooks.conf \
        kernel-crash-dumps.enabled=false
grep -q 'finish: subiquity/Install/install/postinstall/install_package1: SUCCESS: installing package1' \
     $tmpdir/subiquity-server-debug.log
grep -q 'finish: subiquity/Install/install/postinstall/install_package2: SUCCESS: installing package2' \
     $tmpdir/subiquity-server-debug.log
grep -q 'switching subiquity to edge' $tmpdir/subiquity-server-debug.log
grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing all updates' \
    $tmpdir/subiquity-server-debug.log

clean
testname=autoinstall-simple
LANG=C.UTF-8 timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/machines/simple.json \
    --autoinstall examples/autoinstall/user-data.yaml \
    --kernel-cmdline autoinstall \
    --source-catalog examples/sources/install.yaml
validate
python3 scripts/check-yaml-fields.py "$tmpdir"/var/log/installer/autoinstall-user-data \
        'autoinstall.source.id="ubuntu-server-minimal"'
grep -q 'finish: subiquity/Install/install/postinstall/run_unattended_upgrades: SUCCESS: downloading and installing security updates' $tmpdir/subiquity-server-debug.log
python3 scripts/check-yaml-fields.py "$tmpdir"/var/log/installer/curtin-install/subiquity-curthooks.conf \
        kernel-crash-dumps.enabled=null

clean
testname=autoinstall-hybrid
LANG=C.UTF-8 timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/machines/simple.json \
    --autoinstall examples/autoinstall/hybrid.yaml \
    --dry-run-config examples/dry-run-configs/tpm.yaml \
    --bootloader uefi \
    --kernel-cmdline autoinstall \
    --source-catalog examples/sources/tpm.yaml
validate

clean
testname=autoinstall-kernel-components
# components install with fake nvidia pci devices
LANG=C.UTF-8 timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/machines/simple.json \
    --autoinstall examples/autoinstall/hybrid.yaml \
    --dry-run-config examples/dry-run-configs/tpm.yaml \
    --bootloader uefi \
    --snaps-from-examples \
    --kernel-cmdline autoinstall \
    --source-catalog examples/sources/tpm.yaml
validate
grep -q "finish_install: kernel_components=\['nvidia-510-ko', 'nvidia-510-user'\]" \
	$tmpdir/subiquity-server-debug.log

clean
testname=autoinstall-reset-only
LANG=C.UTF-8 timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/machines/simple.json \
    --autoinstall examples/autoinstall/reset-only.yaml \
    --kernel-cmdline autoinstall \
    --source-catalog examples/sources/install.yaml
validate

clean
testname=autoinstall-fallback-offline
LANG=C.UTF-8 timeout --foreground 60 \
    python3 -m subiquity.cmd.tui \
    --dry-run \
    --output-base "$tmpdir" \
    --machine-config examples/machines/simple.json \
    --autoinstall examples/autoinstall/fallback-offline.yaml \
    --kernel-cmdline autoinstall \
    --source-catalog examples/sources/install.yaml
validate

python3 -m subiquity.cmd.schema > $tmpdir/test-schema.json
diff -u "autoinstall-schema.json" $tmpdir/test-schema.json

clean
