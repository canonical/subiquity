import contextlib
from datetime import datetime
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from subprocess import DEVNULL, PIPE, CompletedProcess
from typing import Optional, Sequence

import pytest
import yaml

from . import Firmware


# FIXME timeout

def runcmd(cmd, **kwargs):
    kwargs.setdefault("check", True)
    print(f'running command "{cmd}"')
    return subprocess.run(cmd, **kwargs)


def merge_data(src, dest):
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
        test_config=None,
    ):
        self.vmm = vmm
        self.firmware = firmware
        self.memory_GiB = memory_GiB
        self.disk_sizes_GiB = disk_sizes_GiB
        self.test_config = test_config
        self.parent_tempdir = vmm.tempdir
        self.live_boot = True

    def __enter__(self):
        self.exit_stack = es = contextlib.ExitStack()
        self.tempdir = Path(
            es.enter_context(tempfile.TemporaryDirectory(dir=self.parent_tempdir))
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_stack.close()

    def _merge_cloud_config(self, test_config_str, pubkey) -> Path:
        """
        merge test_config_str with the base config, write the result to a
        temp file, and return that file
        """
        with open("base-cloud-config.yaml", "r") as fp:
            base_config = yaml.safe_load(fp)

        test_config = yaml.safe_load(test_config_str)
        cloud_config = merge_data(test_config, base_config)

        # add test ssh key for install system
        cloud_config["users"][1]["ssh_authorized_keys"] = pubkey

        # add test ssh key for target system
        cloud_config["autoinstall"]["ssh"]["authorized-keys"] = [pubkey]

        result = self.tempdir / "cloud-config.yaml"
        with open(result, "w") as fp:
            fp.write("#cloud-config\n")
            fp.write(yaml.dump(cloud_config))

        return result

    def _assert_install_success(self, data: dict) -> None:
        match data["state"]:
            case "LATE_COMMANDS":
                # the good scenario - we have done autoinstall almost to the
                # end, and are only being held up by the late-command check
                # waiting for the /run/finish file to exist
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
        cloud_config = self._merge_cloud_config(self.test_config, self.vmm.ssh_key_data)

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
            f"user-data={cloud_config},meta-data={self.empty}",
            "--extra-args",
            "autoinstall",
            "--noautoconsole",
        ]

        try:
            print(f"creating install domain {self.domain}")
            runcmd(cmd, stdout=DEVNULL)

            self._wait_for_ip()
            self._wait_for_ssh()
            self._wait_for_socket()
            self._wait_for_install_end()
            yield

            if self.live_boot:
                # we haven't done first boot yet, so do that now as a crude
                # check that first boot works.
                self.reboot()

        except:
            # FIXME this works nicely but we don't want these logs in expected
            # failures cases, or at least not by default
            now = datetime.now()
            dest = Path(f"/tmp/subiquity-vmtest-{now:%Y-%m-%d-%H-%M}")
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

    def _retry_fn(self, fn, iterations, label) -> None:
        print(f"wait for {label}.", end="", flush=True)
        for _ in range(iterations):
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

        self._retry_fn(ip_getter, 30, "ip")

    def _wait_for_ssh_cmd(self, args, iterations, label):
        def ssh_cmd() -> bool:
            return self.ssh(args, check=False).returncode == 0

        self._retry_fn(ssh_cmd, iterations, label)

    def _wait_for_ssh(self):
        self._wait_for_ssh_cmd(["/bin/true"], 10, "ssh")

    def _wait_for_socket(self):
        self._wait_for_ssh_cmd(["test", "-S", "/run/subiquity/socket"], 30, "socket")

    def _wait_for_install_end(self):
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
        self._assert_install_success(data)

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

        self._retry_fn(check_domstate, 30, f"domain {expected}")

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

    def in_target(self, cmd) -> None:
        """
        Run the supplied command underneath `curtin in-target`.  Only
        meaningful during the live install boot, use ssh() instead if testing
        first boot.
        """
        assert self.live_boot

        in_target = [
            "sudo", "subiquity.curtin", "in-target", "-i", "-t", "/target", "--",
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
        self.tempdir = Path(es.enter_context(tempfile.TemporaryDirectory()))
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
