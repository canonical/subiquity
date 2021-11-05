#!/usr/bin/env python3

'''kvm-test - boot a kvm with a test iso, possibly building that test iso first

kvm-test --build -q --install -o --boot
   slimy build, install, overwrite existing image if it exists,
   and boot the result after install

See kvm-test -h for options and more examples.
'''

import argparse
import contextlib
import copy
import crypt
import os
import random
import socket
import sys
import tempfile
import yaml


cfg = '''
iso:
    basedir: /srv/iso
    release:
        edge: jammy/subiquity-edge/jammy-live-server-subiquity-edge-amd64.iso
        canary: jammy/jammy-desktop-canary-amd64.iso
        jammy: jammy/jammy-live-server-amd64.iso
        desktop: impish/jammy-desktop-amd64.iso
        impish: impish/ubuntu-21.10-live-server-amd64.iso
        hirsute: hirsute/ubuntu-21.04-live-server-amd64.iso
        groovy: groovy/ubuntu-20.10-live-server-amd64.iso
        focal: focal/ubuntu-20.04.3-live-server-amd64.iso
        bionic: bionic/bionic-live-server-amd64.iso
    default: edge
'''

sys_memory = '8G'


def salted_crypt(plaintext_password):
    # match subiquity documentation
    salt = '$6$exDY1mhS4KUYCE/2'
    return crypt.crypt(plaintext_password, salt)


class Context:
    def __init__(self, args):
        self.config = self.load_config()
        self.args = args
        self.release = args.release
        if not self.release:
            self.release = self.config["iso"]["default"]
        iso = self.config["iso"]
        try:
            self.baseiso = os.path.join(iso["basedir"],
                                        iso["release"][self.release])
        except KeyError:
            pass
        self.curdir = os.getcwd()
        # self.iso = f'{self.curdir}/{self.release}-test.iso'
        self.iso = f'/tmp/kvm-test/{self.release}-test.iso'
        self.hostname = f'{self.release}-test'
        # self.target = f'{self.curdir}/{self.hostname}.img'
        self.target = f'/tmp/kvm-test/{self.hostname}.img'
        self.password = salted_crypt('ubuntu')
        self.cloudconfig = f'''\
#cloud-config
autoinstall:
    version: 1
    locale:
        en_US.UTF-8
    ssh:
        install-server: true
        allow-pw: true
    identity:
        hostname: {self.hostname}
        password: "{self.password}"
        username: ubuntu
'''
    # refresh-installer:
    #     update: yes
    #     channel: candidate

    def merge(self, a, b):
        '''Take a pair of dictionaries, and provide the merged result.
           Assumes that any key conflicts have values that are themselves
           dictionaries and raises TypeError if found otherwise.'''
        result = copy.deepcopy(a)

        for key in b:
            if key in result:
                left = result[key]
                right = b[key]
                if type(left) is not dict or type(right) is not dict:
                    result[key] = right
                else:
                    result[key] = self.merge(left, right)
            else:
                result[key] = b[key]

        return result

    def load_config(self):
        result = yaml.safe_load(cfg)
        homecfg = f'{os.environ["HOME"]}/.kvm-test.yaml'
        if os.path.exists(homecfg):
            with open(homecfg, 'r') as f:
                result = self.merge(result, yaml.safe_load(f))

        return result


parser = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description='''\
Test isos and images written to /tmp/kvm-test

Sample usage:
    kvm-test --build -q --install -o -a --boot
        slimy build, run install, overwrite existing image, use autoinstall,
        boot final resulting image

    kvm-test --install -bo -rfocal
        boot the focal base iso unmodified and run install manually

See 'cfg' in script for expected layout of iso files,
which can be managed with ~/.kvm-test.yaml''')
parser.add_argument('-a', '--autoinstall', default=False,
                    action='store_true', help='use autoinstall')
parser.add_argument('-b', '--base', default=False, action='store_true',
                    help='use base iso')
parser.add_argument('--basesnap', default=None, action='store',
                    help='use slimy-update-snap on this snap')
parser.add_argument('--snap', default=None, action='store',
                    help='inject this snap into the ISO')
parser.add_argument('-B', '--bios', action='store_true', default=False,
                    help='boot in BIOS mode')
parser.add_argument('-c', '--channel', default=False, action='store',
                    help='build iso with snap from channel')
parser.add_argument('-d', '--disksize', default='12G', action='store',
                    help='size of disk to create (12G default)')
parser.add_argument('-f', '--autoinstall-file', action='store',
                    type=argparse.FileType(),
                    help='load autoinstall from file')
parser.add_argument('-i', '--img', action='store', help='use this img')
parser.add_argument('-n', '--nets', action='store', default=1, type=int,
                    help='number of network interfaces')
parser.add_argument('-o', '--overwrite', default=False, action='store_true',
                    help='allow overwrite of the target image')
parser.add_argument('-q', '--quick', default=False, action='store_true',
                    help='build iso with quick-test-this-branch')
parser.add_argument('-r', '--release', action='store', help='target release')
parser.add_argument('-s', '--serial', default=False, action='store_true',
                    help='attach to serial console')
parser.add_argument('-S', '--sound', default=False, action='store_true',
                    help='enable sound')
parser.add_argument('-t', '--this', action='store',
                    help='use this iso')
parser.add_argument('-u', '--update', action='store',
                    help='subiquity-channel argument')
parser.add_argument('--save', action='store_true',
                    help='preserve built snap')
parser.add_argument('--reuse', action='store_true',
                    help='reuse previously saved snap')
parser.add_argument('--build', default=False, action='store_true',
                    help='build test iso')
parser.add_argument('--install', default=False, action='store_true',
                    help='''install from iso - one must either build a test
                    iso, use a base iso, or reuse previous test iso''')
parser.add_argument('--boot', default=False, action='store_true',
                    help='boot test image')


def waitstatus_to_exitcode(waitstatus):
    '''If the process exited normally (if WIFEXITED(status) is true), return
    the process exit status (return WEXITSTATUS(status)): result greater
    than or equal to 0.

    If the process was terminated by a signal (if WIFSIGNALED(status) is
    true), return -signum where signum is the number of the signal that
    caused the process to terminate (return -WTERMSIG(status)): result less
    than 0.

    Otherwise, raise a ValueError.'''

    # This function is for python 3.9 compat

    if 'waitstatus_to_exitcode' in dir(os):
        return os.waitstatus_to_exitcode(waitstatus)
    if os.WIFEXITED(waitstatus):
        return os.WEXITSTATUS(waitstatus)
    if os.WIFSIGNALED(waitstatus):
        return -os.WTERMSIG(waitstatus)

    raise ValueError


class SubProcessFailure(Exception):
    pass


def run(cmds):
    for cmd in [line.strip() for line in cmds.splitlines()]:
        if len(cmd) < 1:
            continue
        # semi-simulate "bash -x"
        print(f'+ {cmd}')
        # FIXME subprocess check
        ec = waitstatus_to_exitcode(os.system(cmd))
        if ec != 0:
            raise SubProcessFailure(f'command [{cmd}] returned [{ec}]')


@contextlib.contextmanager
def delete_later(path):
    try:
        yield path
    finally:
        os.remove(path)


@contextlib.contextmanager
def noop(path):
    yield path


@contextlib.contextmanager
def mounter(src, dest):
    run(f'sudo mount -r {src} {dest}')
    try:
        yield
    finally:
        run(f'sudo umount {dest}')


def build(ctx):
    run('sudo -v')
    run(f'rm -f {ctx.iso}')
    project = os.path.basename(os.getcwd())

    snap_manager = noop if ctx.args.save else delete_later
    # FIXME generalize to
    # PYTHONPATH=$LIVEFS_EDITOR python3 -m livefs_edit $OLD_ISO $NEW_ISO
    # --inject-snap $SUBIQUITY_SNAP_PATH
    if project.startswith('subiquity'):
        if ctx.args.quick:
            with snap_manager('subiquity_new.snap') as snap:
                run(f'sudo ./scripts/quick-test-this-branch.sh {ctx.baseiso} \
                    {ctx.iso}')
        elif ctx.args.basesnap:
            with snap_manager('subiquity_test.snap') as snap:
                run(f'sudo ./scripts/slimy-update-snap.sh {ctx.args.basesnap} \
                    {snap}')
                run(f'sudo ./scripts/inject-subiquity-snap.sh {ctx.baseiso} \
                    {snap} {ctx.iso}')
        elif ctx.args.snap:
            run(f'sudo ./scripts/inject-subiquity-snap.sh {ctx.baseiso} \
                {ctx.args.snap} {ctx.iso}')
        elif ctx.args.channel:
            run(f'sudo PYTHONPATH=$LIVEFS_EDITOR python3 -m livefs_edit \
                    {ctx.baseiso} {ctx.iso} \
                    --add-snap-from-store subiquity {ctx.args.channel}')
        else:
            with snap_manager('subiquity_test.snap') as snap:
                if not ctx.args.reuse:
                    run(f'''
                        snapcraft clean --use-lxd
                        snapcraft snap --use-lxd --output {snap}
                        ''')
                run(f'''
                    test -f {snap}
                    sudo PYTHONPATH=$LIVEFS_EDITOR python3 -m livefs_edit \
                        {ctx.baseiso} {ctx.iso} \
                        --add-snap-from-store core20 stable \
                        --inject-snap {snap}
                    ''')
                # sudo ./scripts/inject-subiquity-snap.sh {ctx.baseiso} \
                #     {snap} {ctx.iso}
    elif project == 'ubuntu-desktop-installer':
        with snap_manager('udi_test.snap') as snap:
            run(f'''
                snapcraft clean --use-lxd
                snapcraft snap --use-lxd --output {snap}
                test -f {snap}
                sudo ./scripts/inject-snap {ctx.baseiso} \
                    {ctx.iso} {snap}
                ''')
    else:
        raise Exception(f'do not know how to build {project}')

    run(f'test -f {ctx.iso}')


def write(dest, data):
    with open(dest, 'w') as destfile:
        destfile.write(data)


def touch(dest):
    with open(dest, 'w'):
        pass


def create_seed(cloudconfig, tempdir):
    write(f'{tempdir}/user-data', cloudconfig)
    touch(f'{tempdir}/meta-data')
    seed = f'{tempdir}/seed.iso'
    run(f'cloud-localds {seed} {tempdir}/user-data {tempdir}/meta-data')
    return seed


def drive(path, format='qcow2'):
    kwargs = []
    serial = None
    cparam = 'writethrough'
    # if cache == False: cparam = 'none'
    # serial doesn't work..
    # serial = str(int(random.random() * 100000000)).zfill(8)
    kwargs += [f'file={path}']
    kwargs += [f'format={format}']
    kwargs += [f'cache={cparam}']
    kwargs += ['if=virtio']
    if serial:
        kwargs += [f'serial={serial}']

    return '-drive ' + ','.join(kwargs)


class PortFinder:
    def __init__(self):
        self.finder = self.port_generator()

    def port_generator(self):
        for port in range(2222, 8000):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                res = sock.connect_ex(('localhost', port))
                if res != 0:
                    yield port

    def get(self):
        return next(self.finder)


def nets(ctx):
    ports = PortFinder()

    ret = []
    if ctx.args.nets > 0:
        for _ in range(ctx.args.nets):
            port = ports.get()
            ret += ['-nic',
                    'user,model=virtio-net-pci,' +
                    f'hostfwd=tcp::{port}-:22']  # ,restrict=on']
    else:
        ret += ['-nic', 'none']
    return ret


def bios(ctx):
    ret = []
    # https://help.ubuntu.com/community/UEFI
    if not ctx.args.bios:
        ret += ['-bios', '/usr/share/qemu/OVMF.fd']
    return ret


def memory(ctx):
    return ['-m', str(sys_memory)]


def kvm_common(ctx):
    ret = ['kvm', '-no-reboot']
    ret.extend(('-vga', 'virtio'))
    ret.extend(memory(ctx))
    ret.extend(bios(ctx))
    ret.extend(nets(ctx))
    if ctx.args.sound:
        ret.extend(('-device', 'AC97', '-device', 'usb-ehci'))
    return ret


def grub_get_extra_args(mntdir):
    # The inject-snap process of livefs-edit adds a new layer squash
    # that must be in place, or the injected snap isn't there.
    # We don't want to hardcode the current value, because that layer
    # isn't there if a base iso is being used.
    # Parse the args out of grub.cfg and include them with ours.
    cfgpath = f'{mntdir}/boot/grub/grub.cfg'
    ret = []
    try:
        with open(cfgpath, 'r') as fp:
            for line in fp.readlines():
                chunks = line.strip().split('\t')
                # ['linux', '/casper/vmlinuz  ---']
                # layerfs-path=a.b.c.d.e.squashfs
                if not chunks or not chunks[0] == 'linux':
                    continue
                subchunks = chunks[1].split(' ')
                if not subchunks or not subchunks[0] == '/casper/vmlinuz':
                    continue
                for sc in subchunks[1:]:
                    if sc != '---':
                        ret.append(sc)
                break
        # breakpoint()
    except FileNotFoundError:
        pass
    return ret


def get_initrd(mntdir):
    for initrd in ('initrd', 'initrd.lz', 'initrd.lz4'):
        path = f'{mntdir}/casper/{initrd}'
        if os.path.exists(path):
            return path
    raise Exception('initrd not found')


def install(ctx):
    if os.path.exists(ctx.target):
        if ctx.args.overwrite:
            os.remove(ctx.target)

    run('sudo -v')

    with tempfile.TemporaryDirectory() as tempdir:
        mntdir = f'{tempdir}/mnt'
        os.mkdir(mntdir)
        appends = []

        kvm = kvm_common(ctx)

        if ctx.args.this:
            iso = ctx.args.this
        elif ctx.args.base:
            iso = ctx.baseiso
        else:
            iso = ctx.iso

        kvm += ['-cdrom', iso]

        if ctx.args.serial:
            kvm += ['-nographic']
            appends += ['console=ttyS0']

        if ctx.args.autoinstall or ctx.args.autoinstall_file:
            if ctx.args.autoinstall_file:
                ctx.cloudconfig = ctx.args.autoinstall_file.read()
            kvm += [drive(create_seed(ctx.cloudconfig, tempdir), 'raw')]
            appends += ['autoinstall']

        if ctx.args.update:
            appends += ['subiquity-channel=candidate']

        kvm += [drive(ctx.target)]
        if not os.path.exists(ctx.target) or ctx.args.overwrite:
            run(f'qemu-img create -f qcow2 {ctx.target} {ctx.args.disksize}')

        # drive2 = f'{ctx.curdir}/drive2.img'

        # appends += ['subiquity-channel=edge']

        with mounter(iso, mntdir):
            if len(appends) > 0:
                appends += grub_get_extra_args(mntdir)
                # if we're passing kernel args, we need to manually specify
                # kernel / initrd
                kvm += ['-kernel', f'{mntdir}/casper/vmlinuz']
                kvm += ['-initrd', get_initrd(mntdir)]
                toappend = ' '.join(appends)
                kvm += ['-append', f'"{toappend}"']

            run(' '.join(kvm))


def boot(ctx):
    target = ctx.target
    if ctx.args.img:
        target = ctx.args.img

    kvm = kvm_common(ctx)
    kvm += [drive(target)]
    run(' '.join(kvm))


def help(ctx):
    parser.print_usage()
    sys.exit(1)


def cloud(ctx):
    print(ctx.cloudconfig)


try:
    ctx = Context(parser.parse_args())
except TypeError:
    help()

if ctx.args.base and ctx.args.build:
    raise Exception('cannot use base iso and build')

os.makedirs('/tmp/kvm-test', exist_ok=True)

if ctx.args.build:
    build(ctx)
if ctx.args.install:
    install(ctx)
if ctx.args.boot:
    boot(ctx)
if True not in (ctx.args.build, ctx.args.install, ctx.args.boot):
    parser.print_help()
