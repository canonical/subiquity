import contextlib
import json
import re
import subprocess
from tempfile import TemporaryDirectory
import time
from datetime import datetime
from pathlib import Path
from subprocess import DEVNULL, PIPE, CompletedProcess
from typing import Optional, Sequence

import pytest
import yaml

from subiquity.models.source import SourceModel

from . import Firmware


@contextlib.contextmanager
def mounter(src):
    with TemporaryDirectory() as td:
        runcmd(["fuseiso", str(src), td])
        try:
            yield Path(td)
        finally:
            runcmd(["fusermount", "-u", td])


def runcmd(cmd, check=True, **kwargs):
    print(f'running command "{cmd}"')
    return subprocess.run(cmd, check=check, **kwargs)


def merge_data(src: dict, dest: dict) -> dict:
    """ merge data from src to dest """
    dest = dest.copy()
    for key, value in src.items():
        if key in dest and type(value) != type(dest[key]):
            raise ValueError(
                f"merge undefined for {key=} src_val={value} dest_val={dest[key]}"
            )

        if isinstance(value, dict) and key in dest:
            dest[key] = merge_data(value, dest[key])
        elif isinstance(value, list) and key in dest:
            dest[key].extend(value)
        else:
            dest[key] = value
    return dest


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

    def __enter__(self):
        self.exit_stack = es = contextlib.ExitStack()
        dir = self.parent_tempdir
        self.tempdir = Path(es.enter_context(TemporaryDirectory(dir=dir)))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_stack.close()

    def _merge_cloud_config(self, cloud_config, pubkey) -> Path:
        """
        merge test_cloud_config with the base config, write the result to a
        temp file, add a few additional test requirements, and return that file
        """
        with open("base-cloud-config.yaml", "r") as fp:
            base_cc_data = yaml.safe_load(fp)

        if cloud_config is None:
            merged_cc = base_cc_data
        else:
            cc_data = yaml.safe_load(cloud_config)
            merged_cc = merge_data(cc_data, base_cc_data)

        # add test ssh key for install system
        merged_cc["users"][1]["ssh_authorized_keys"] = pubkey

        # add test ssh key for target system
        merged_cc["autoinstall"]["ssh"]["authorized-keys"] = [pubkey]

        # default to the minimal source.  As the id names vary by ISO, we have
        # to guess that out, but they should be the one that ends in -minimal.
        source = SourceModel()
        with mounter(self.vmm.option_iso) as iso:
            with Path(iso / "casper/install-sources.yaml").open() as fp:
                source.load_from_file(fp)
        for entry in source.catalog.sources:
            if entry.id.endswith("-minimal"):
                minimal_id = entry.id
                break
        else:
            ids = [entry.id for entry in source.catalog.sources]
            raise Exception(f"minimal catalog entry not found in {ids}")
        merged_cc["autoinstall"].setdefault("source", {})["id"] = minimal_id

        late_cmds = merged_cc["autoinstall"].setdefault("late-commands", [])
        # all tests should run these commands.  The first one allows us to know
        # that any test-defined late-commands have completed.  We want to run
        # test assertions after those test defined late-commands have executed.
        late_cmds.append("touch /run/wait_for_finish")
        # This second one is a documented trick for autoinstall to not reboot
        # until we're ready for it.  This holds the reboot and gives us room to
        # actually run the test assertions.  When we're ready to reboot to the
        # target system, we touch /run/finish to move things along.
        late_cmds.append("while [ ! -f /run/finish ] ; do sleep 1 ; done")

        result = self.tempdir / "cloud-config.yaml"
        result.write_text("#cloud-config\n" + yaml.dump(merged_cc))

        return result

    def _assert_state_late_commands(self, data: dict) -> None:
        match data["state"]:
            case "LATE_COMMANDS":
                # the good scenario - we have done autoinstall almost to the
                # end, and are only being held up by active late-commands.
                # Usually this is just waiting for /run/finish to exist, or it
                # could be late-commands in the test.
                return
            case "ERROR":
                # install failure
                pytest.fail("install failed and reached ERROR state")
            case _:
                # should never happen
                pytest.fail(f"unexpected state={data['state']}")

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
            runcmd(cmd, stdout=DEVNULL)

            self._wait_for_poweron()
            self._wait_for_ip()
            self._wait_for_ssh()
            self._wait_for_socket()
            self._wait_for_finish_sentinel()
            yield

            if self.live_boot:
                # we haven't done first boot yet, so do that now as a crude
                # check that first boot works.  Tests with assertions to run at
                # first boot should call reboot() before those assertions.
                self.reboot()

        except:
            # FIXME this works nicely but we don't want these logs in expected
            # failures cases, or at least not by default
            now = datetime.now()
            dest = Path(f"/tmp/subiquity-vmtest-{now:%Y-%m-%d-%H-%M-%S}")
            dest.mkdir(exist_ok=False)
            self._collect_logs(dest)
            print(f"logs written to {dest}")
            raise
        finally:
            try:
                runcmd(["virsh", "destroy", self.domain], check=False)

            finally:
                undefine = ["virsh", "undefine", self.domain, "--remove-all-storage"]
                runcmd(undefine, stdout=DEVNULL)

    def _collect_logs(self, dest):
        self.ssh(
            [
                "sudo",
                "sh -c 'journalctl -b > /var/log/installer/installer-journal.log'",
            ],
        )
        tarball = f"/tmp/subiquity-vmtest-{self.vmm.test_name}.tgz"
        # FIXME this may fail, especially early in the test attempt
        self.ssh(["sudo", "tar", "zcvf", tarball, "/var/log/installer"])
        self._scp_get(tarball, str(dest))

    def _scp_get(self, infile, dest) -> None:
        cmd = ["scp", *self._ssh_common(), f"ubuntu@{self.ip}:{infile}", dest]
        runcmd(cmd, stdout=PIPE, stderr=DEVNULL, check=True)

    def _get_ip(self) -> Optional[str]:
        cmd = ["virsh", "domifaddr", self.domain]
        sp = runcmd(cmd, stdout=PIPE, check=False)
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
            pytest.fail(f"{label} never happened")
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

    def _wait_for_socket(self):
        self._wait_for_ssh_cmd(["test", "-S", "/run/subiquity/socket"], "socket")

    def _wait_for_finish_sentinel(self):
        print("wait for end state.", end="", flush=True)
        while True:
            sp = self.ssh(
                ["curl", "--unix-socket", "/run/subiquity/socket", "a/meta/status"],
            )
            data = json.loads(sp.stdout)
            if data["state"] in ("LATE_COMMANDS", "DONE", "ERROR", "EXITED"):
                break
            print(".", end="", flush=True)
            time.sleep(1)
        print(f"done: {data['state']}")
        self._assert_state_late_commands(data)

        # We use late-commands to catch the install nearly being complete but
        # not 100% done.  If a test uses late commands, wait for those to be
        # done.  Before waiting on /run/finish, late-commands will create
        # /run/wait_for_finish, which signifies that that the install is
        # functionally complete and ready for our test assertions.
        sentinel_cmd = ["test", "-f", "/run/wait_for_finish"]
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

    def ssh(self, args, check=True) -> CompletedProcess:
        cmd = ["ssh", *self._ssh_common(), f"ubuntu@{self.ip}", "--", *args]
        return runcmd(cmd, stdout=PIPE, stderr=DEVNULL, check=check)

    def _wait_for_domstate(self, expected):
        def check_domstate() -> bool:
            sp = runcmd(["virsh", "domstate", self.domain], stdout=PIPE)
            return expected == sp.stdout.decode().splitlines()[0]

        self._retry_fn(check_domstate, f"domain {expected}")

    def _wait_for_poweroff(self):
        self._wait_for_domstate("shut off")

    def _wait_for_poweron(self):
        self._wait_for_domstate("running")

    def _poweroff(self) -> None:
        if self.live_boot:
            self.ssh(["sudo", "touch", "/run/finish"])
            self.live_boot = False
        else:
            runcmd(["virsh", "shutdown", self.domain], stdout=DEVNULL)
        self._wait_for_poweroff()

    def reboot(self) -> None:
        """
        Reboot the VM.  If this is the live install boot, signal to the
        installer that the install should finish cleanly.  Wait for poweroff,
        start the VM again, and wait for SSH to be available.
        """
        self._poweroff()
        runcmd(["virsh", "start", self.domain], stdout=DEVNULL)
        self._wait_for_poweron()
        self._wait_for_ip()
        self._wait_for_ssh()

    def lsblk(self) -> dict:
        """
        The dictionary representation of `lsblk -Jb`.
        """
        sp = self.ssh(["lsblk", "-Jb", "/dev/vda"])
        return json.loads(sp.stdout.decode())

    def in_target(self, cmd) -> CompletedProcess:
        """
        Run the supplied command underneath `curtin in-target`.  Only
        meaningful during the live install boot, use ssh() instead if testing
        first boot.
        """
        assert self.live_boot

        # FIXME subiquity.curtin only defined on the server ISO
        in_target = [
            "sudo",
            "subiquity.curtin",
            "in-target",
            "-i",
            "-t",
            "/target",
            "--",
        ]
        return self.ssh(in_target + cmd)


class VMM:
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
        self.exit_stack.enter_context(result._install())
        return result

    def _create_ssh_key(self) -> str:
        self.ssh_key = self.tempdir / "ssh_key"
        keygen = ["ssh-keygen", "-f", str(self.ssh_key), "-N", ""]
        runcmd(keygen, stdout=DEVNULL)
        return (self.tempdir / "ssh_key.pub").read_text().strip()


@pytest.fixture
def vmm(request, option_iso):
    assert option_iso is not None, "--iso=/path/to/file.iso must be supplied"

    isofile = Path(option_iso)
    if not isofile.exists() or not isofile.is_file():
        pytest.fail("{option_iso} not a valid install iso")

    with VMM(request, isofile) as _vmm:
        yield _vmm


def pytest_addoption(parser):
    parser.addoption("--iso", action="store")


@pytest.fixture
def option_iso(request):
    return request.config.getoption("--iso")
