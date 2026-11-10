import contextlib
import json
import re
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path
from subprocess import DEVNULL, PIPE, CompletedProcess
from tempfile import TemporaryDirectory
from typing import Optional, Sequence

import pytest
import yaml
from cloudinit.util import mergemanydict

from subiquity.models.source import SourceModel

from . import Firmware

# REBOOT_HOLD_READY_SENTINEL_FILE is created by late-commands to signal that
# the install is functionally complete and the system has entered the
# reboot-hold: the window after install is done but before Subiquity exits and
# reboots, during which install-time assertions can run.
REBOOT_HOLD_READY_SENTINEL_FILE = "/run/reboot-hold-ready"

# REBOOT_HOLD_RELEASE_SENTINEL_FILE is created by the test harness, after the
# install-time assertions have run, to release the reboot-hold and let
# Subiquity proceed to reboot.
REBOOT_HOLD_RELEASE_SENTINEL_FILE = "/run/reboot-hold-release"


@contextlib.contextmanager
def _timer(label):
    start_time = time.perf_counter()
    try:
        yield
    finally:
        end_time = time.perf_counter()
        print(f"{label} took {end_time - start_time:.4f}s")


class VM:
    def __init__(
        self,
        vmm,
        firmware=Firmware.UEFI,
        memory_GiB=4,
        disk_sizes_GiB=[10],
        cloud_config=None,
    ):
        self.vmm = vmm
        self.firmware = firmware
        self.memory_GiB = memory_GiB
        self.disk_sizes_GiB = disk_sizes_GiB
        self.cloud_config = cloud_config
        self.parent_tempdir = vmm.tempdir
        self.live_boot = True
        self.ip = None

    def __enter__(self):
        self.exit_stack = es = contextlib.ExitStack()
        dir = self.parent_tempdir
        self.tempdir = Path(es.enter_context(TemporaryDirectory(dir=dir)))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_stack.close()

    def ssh(self, cmd: Sequence[str], check=True) -> CompletedProcess:
        """
        SSH to system and run the command, either the installation environment
        if before first reboot, or to the target system.
        """
        if self.ip is None:
            raise RuntimeError("attempted to ssh prior to SUT having an IP")
        cmd = ["ssh", *self._ssh_common(), f"ubuntu@{self.ip}", "--", *cmd]
        return _runcmd(cmd, stdout=PIPE, stderr=DEVNULL, check=check)

    def in_target(self, cmd: Sequence[str]) -> CompletedProcess:
        """
        Run the supplied command underneath `curtin in-target`.  Only
        meaningful during the live install boot, use ssh() instead if testing
        the first boot of the target system.
        """
        assert self.live_boot

        in_target = [
            "sudo",
            *self._curtin_cmd(),
            "in-target",
            "-i",
            "-t",
            "/target",
            "--",
        ]
        return self.ssh(in_target + cmd)

    def lsblk(self) -> dict:
        """
        The dictionary representation of `lsblk -Jb`.
        """
        sp = self.ssh(["lsblk", "-Jb", "/dev/vda"])
        return json.loads(sp.stdout.decode())

    def reboot(self) -> None:
        """
        Reboot the VM.  If this is the live install boot, signal to the
        installer that the install should finish cleanly.  Wait for poweroff,
        start the VM again, and wait for SSH to be available.
        """
        self._poweroff()
        _virsh(["start", self.domain], stdout=DEVNULL)
        self._wait_for_poweron()
        self._wait_for_ip()
        self._wait_for_ssh()

    def _merge_cloud_config(self, cloud_config, pubkey) -> Path:
        """
        Merge cloud_config from the test with the base cloud configuration,
        set some required infrastructure in that merged config, write the
        result to a temp file, and return the Path to that file.
        """
        with open("vmtests/base-cloud-config.yaml", "r") as fp:
            base_cc_data = yaml.safe_load(fp)

        # Examine install-sources.yaml and select the minimal source.
        # TODO: take a parameter to choose standard instead, so that tests of
        # the standard source are generic to server/desktop/flavors.
        source = SourceModel()
        with _mounter(self.vmm.option_iso) as iso:
            with Path(iso / "casper/install-sources.yaml").open() as fp:
                source.load_from_file(fp)
        for entry in source.catalog.sources:
            if entry.id.endswith("-minimal"):
                minimal_id = entry.id
                break
        else:
            ids = [entry.id for entry in source.catalog.sources]
            raise RuntimeError(f"minimal catalog entry not found in {ids}")
        base_cc_data["autoinstall"].setdefault("source", {})["id"] = minimal_id

        if cloud_config is None:
            merged_cc = base_cc_data
        else:
            # Merge test cloud-config over base config. Uses cloud-init's
            # standard merger rules; cc_data wins on scalar/dict conflicts,
            # and lists are NOT concatenated (first source's list is kept).
            # See https://cloudinit.readthedocs.io/en/latest/reference/merging.html
            cc_data = yaml.safe_load(cloud_config)
            merged_cc = mergemanydict([cc_data, base_cc_data])

        # add test ssh key for install system.  This, and everything else
        # below, is done after merge of test cloud-config because it's core
        # infrastructure that tests may not overwrite.
        merged_cc["users"][1]["ssh_authorized_keys"] = pubkey

        # add test ssh key for target system.
        merged_cc["autoinstall"]["ssh"]["authorized-keys"] = [pubkey]

        # all tests must run these commands.
        late_cmds = merged_cc["autoinstall"].setdefault("late-commands", [])
        # Signal that the install is functionally complete and the
        # reboot-hold has been entered, so VMM.install() may return and
        # assertions can proceed.
        late_cmds.append(f"touch {REBOOT_HOLD_READY_SENTINEL_FILE}")
        # Hold the reboot in the reboot-hold window until assertions have run.
        # This is the documented trick to keep autoinstall from rebooting
        # until we're ready; touching REBOOT_HOLD_RELEASE_SENTINEL_FILE from
        # the harness releases the hold and lets Subiquity proceed to reboot.
        late_cmds.append(
            f"while [ ! -f {REBOOT_HOLD_RELEASE_SENTINEL_FILE} ] ; do sleep 1 ; done"
        )

        result = self.tempdir / "cloud-config.yaml"
        result.write_text("#cloud-config\n" + yaml.dump(merged_cc))

        return result

    def _assert_state_late_commands(self, data: dict) -> None:
        match data["state"]:
            case "LATE_COMMANDS":
                # the good scenario - we have done autoinstall almost to the
                # end, and are only being held up by active late-commands.
                # Usually this is waiting for REBOOT_HOLD_RELEASE_SENTINEL_FILE
                # to exist, or it could be late-commands in the test.
                return
            case "ERROR":
                # install failure
                raise RuntimeError("install failed and reached ERROR state")
            case _:
                # should never happen
                raise RuntimeError(f"unexpected state={data['state']}")

    @contextlib.contextmanager
    def _install(self, **kwargs) -> None:
        """
        Actually do the install.  Typically initiated from VMM.install().
        """
        cc_file = self._merge_cloud_config(self.cloud_config, self.vmm.ssh_key_data)

        self.domain = f"subiquity-vmtest-{self.vmm.test_name}-{self.tempdir.name}"

        self.empty = self.tempdir / "meta-data"
        self.empty.touch()

        cmd = [
            "virt-install",
            "--os-variant",
            "ubuntu-lts-latest",
            "--name",
            self.domain,
            "--memory",
            str(self.memory_GiB << 10),
            "--disk",
            f"size={self.disk_sizes_GiB[0]},target.dev=vda",
            "--location",
            f"{str(self.vmm.option_iso)},kernel=/casper/vmlinuz,initrd=/casper/initrd",
            "--cloud-init",
            f"user-data={cc_file},meta-data={self.empty}",
            "--extra-args",
            "autoinstall",
            "--noautoconsole",
        ]

        try:
            print(f"creating install domain {self.domain}")
            _runcmd(cmd, stdout=DEVNULL)

            self._wait_for_poweron()
            self._wait_for_ip()
            self._wait_for_ssh()
            self._detect_SNAP()
            self._wait_for_socket()
            self._wait_for_reboot_hold()
            yield

            if self.live_boot:
                # we haven't done first boot yet, so do that now as a crude
                # check that first boot works.  Tests with assertions to run at
                # first boot should call reboot() before those assertions.
                self.reboot()

        except Exception, KeyboardInterrupt:
            now = datetime.now()
            ts = f"{now:%Y-%m-%d-%H-%M-%S}"
            label = f"subiquity-vmtest-{self.vmm.test_name}-{ts}"
            dest = Path(f"/tmp/{label}")
            dest.mkdir(exist_ok=False)
            try:
                self._collect_logs(label, dest)
                print(f"logs written to {dest}")
            except Exception:
                print(f"log collection to {dest} failed")
                traceback.print_exc()
            raise

        finally:
            try:
                _virsh(["destroy", self.domain], check=False)

            finally:
                undefine = [
                    "undefine",
                    self.domain,
                    "--remove-all-storage",
                    "--nvram",
                ]
                _virsh(undefine, stdout=DEVNULL)

    def _collect_logs(self, label, dest):
        self.ssh(
            [
                "sudo",
                "sh -c 'journalctl -b > /var/log/installer/installer-journal.log'",
            ],
            check=False,
        )
        tarball = f"/tmp/{label}.tgz"
        self.ssh(
            ["sudo", "tar", "zcvf", tarball, "/var/log/installer"],
            check=False,
        )
        self._scp_get(tarball, str(dest), check=False)

    def _scp_get(self, infile, dest, check=True) -> CompletedProcess:
        if self.ip is None:
            raise RuntimeError("attempted to ssh prior to SUT having an IP")
        cmd = ["scp", *self._ssh_common(), f"ubuntu@{self.ip}:{infile}", dest]
        return _runcmd(cmd, stdout=PIPE, stderr=DEVNULL, check=check)

    def _get_ip(self) -> Optional[str]:
        sp = _virsh(["domifaddr", self.domain], stdout=PIPE, check=False)
        if sp.returncode != 0:
            return None
        for line in sp.stdout.decode().splitlines():
            m = re.fullmatch(r".*ipv4\s+(\d+\.\d+\.\d+\.\d+).*", line)
            if m is not None:
                return m.group(1)
        return None

    def _retry_fn(self, fn, label, wait_seconds=300) -> None:
        print(f"wait for {label}.", end="", flush=True)
        for _ in range(wait_seconds):
            if fn():
                break
            time.sleep(1)
            print(".", end="", flush=True)
        else:
            raise RuntimeError(f"{label} never happened")
        print("done")

    def _wait_for_ip(self) -> None:
        def ip_getter() -> bool:
            self.ip = self._get_ip()
            return self.ip is not None

        self._retry_fn(ip_getter, "ip")

    def _wait_for_ssh_cmd(self, args, label, **kwargs):
        def ssh_cmd() -> bool:
            return self.ssh(args, check=False).returncode == 0

        self._retry_fn(ssh_cmd, label, **kwargs)

    def _wait_for_ssh(self):
        self._wait_for_ssh_cmd(["/bin/true"], "ssh")

    def _detect_SNAP(self) -> None:
        """is this subiquity or ubuntu-desktop-bootstrap?"""
        subscript = """
            ([ -d /snap/subiquity ] && echo subiquity) ||
            ([ -d /snap/ubuntu-desktop-bootstrap ] && echo ubuntu-desktop-bootstrap) ||
            echo UNKNOWN
        """
        sp = self.ssh(["sh", "-c", subscript])
        name = sp.stdout.decode().strip()
        if name == "UNKNOWN":
            raise RuntimeError("failed to detect installer snap")
        else:
            self.snap = name

    def _wait_for_socket(self):
        self._wait_for_ssh_cmd(["test", "-S", "/run/subiquity/socket"], "socket")

    def _wait_for_reboot_hold(self, wait_seconds=3600):
        print("wait for end state.", end="", flush=True)
        data = {"state": "UNKNOWN"}
        for i in range(wait_seconds):
            print(f"try {i} / {wait_seconds}", flush=True)
            sp = self.ssh(
                ["curl", "--unix-socket", "/run/subiquity/socket", "a/meta/status"],
                check=False,
            )
            # there can be a ssh socket reset, seemingly triggered by
            # cloud-init installing openssh-server (unconfirmed)
            # tolerate that and continue
            if sp.returncode == 0:
                data = json.loads(sp.stdout)
                print(f"data['state']={data['state']}", flush=True)
                if data["state"] in ("LATE_COMMANDS", "DONE", "ERROR", "EXITED"):
                    break
            print(".", end="", flush=True)
            time.sleep(1)
        else:
            raise RuntimeError(
                f"timed out waiting for final state, current state {data['state']}"
            )
        print(f"done: {data['state']}")
        self._assert_state_late_commands(data)

        # Subiquity has reached the LATE_COMMANDS state.  The late-commands
        # create REBOOT_HOLD_READY_SENTINEL_FILE just before blocking on the
        # reboot-hold, signifying the install is functionally complete and
        # assertions can run.  Wait for that sentinel to appear.
        sentinel_cmd = ["test", "-f", REBOOT_HOLD_READY_SENTINEL_FILE]
        self._wait_for_ssh_cmd(sentinel_cmd, "install completion")

    def _ssh_common(self) -> Sequence:
        return [
            "-i",
            str(self.vmm.ssh_key),
            "-F",
            "none",
            "-oStrictHostKeyChecking=off",
            "-oUserKnownHostsFile=/dev/null",
        ]

    def _wait_for_domstate(self, expected):
        def check_domstate() -> bool:
            sp = _virsh(["domstate", self.domain], stdout=PIPE)
            return expected == sp.stdout.decode().splitlines()[0]

        self._retry_fn(check_domstate, f"domain {expected}")

    def _wait_for_poweroff(self):
        self._wait_for_domstate("shut off")

    def _wait_for_poweron(self):
        self._wait_for_domstate("running")

    def _poweroff(self) -> None:
        if self.live_boot:
            self.ssh(["sudo", "touch", REBOOT_HOLD_RELEASE_SENTINEL_FILE])
            self.live_boot = False
        else:
            _virsh(["shutdown", self.domain], stdout=DEVNULL)
        self._wait_for_poweroff()

    def _curtin_cmd(self) -> Sequence[str]:
        if self.snap == "subiquity":
            return ["subiquity.curtin"]
        if self.snap == "ubuntu-desktop-bootstrap":
            return [
                "/snap/ubuntu-desktop-bootstrap/current/bin/subiquity/bin/subiquity-cmd",
                "curtin",
            ]
        raise RuntimeError("failed to detect installer snap")


class VMM:
    """
    The virtual machine manager is used to create a VM and start an install.
    """

    def __init__(self, request, option_iso):
        self.request = request
        self.option_iso = option_iso

    @property
    def test_name(self):
        return self.request.node.name

    def __enter__(self):
        self.exit_stack = es = contextlib.ExitStack()
        self.tempdir = Path(es.enter_context(TemporaryDirectory()))
        self.ssh_key_data = self._create_ssh_key()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_stack.close()

    def install(self, **kwargs) -> VM:
        """
        Build a VM, establish the hardware configuration, and start an install.
        """
        result = self.exit_stack.enter_context(VM(vmm=self, **kwargs))
        with _timer("install (pre-reboot)"):
            self.exit_stack.enter_context(result._install())
        return result

    def _create_ssh_key(self) -> str:
        self.ssh_key = self.tempdir / "ssh_key"
        keygen = ["ssh-keygen", "-f", str(self.ssh_key), "-N", ""]
        _runcmd(keygen, stdout=DEVNULL)
        return (self.tempdir / "ssh_key.pub").read_text().strip()


@pytest.fixture
def vmm(request, option_iso):
    assert option_iso is not None, "--iso=/path/to/file.iso must be supplied"

    isofile = Path(option_iso)
    if not isofile.exists() or not isofile.is_file():
        raise RuntimeError(f"{option_iso} is not a valid install iso")

    with VMM(request, isofile) as _vmm:
        yield _vmm


def pytest_addoption(parser):
    parser.addoption("--iso", action="store")


@pytest.fixture
def option_iso(request):
    return request.config.getoption("--iso")


@contextlib.contextmanager
def _mounter(src):
    with TemporaryDirectory() as td:
        _runcmd(["fuseiso", str(src), td])
        try:
            yield Path(td)
        finally:
            _runcmd(["fusermount", "-u", td])


def _runcmd(cmd, check=True, **kwargs) -> CompletedProcess:
    print(f'running command "{cmd}"')
    return subprocess.run(cmd, check=check, **kwargs)


def _virsh(cmd, **kwargs):
    return _runcmd(["virsh", "--connect", "qemu:///system"] + cmd, **kwargs)
