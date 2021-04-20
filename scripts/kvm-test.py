#!/usr/bin/env python3

import argparse
import contextlib
import copy
import crypt
import os
import sys
import tempfile
import yaml


cfg = '''
iso:
    basedir: /srv/iso
    release:
        hirsute: hirsute/hirsute-live-server-amd64.iso
        groovy: groovy/ubuntu-20.10-live-server-amd64.iso
        focal: focal/ubuntu-20.04.2-live-server-amd64.iso
'''


def salted_crypt(plaintext_password):
    # match subiquity documentation
    salt = '$6$exDY1mhS4KUYCE/2'
    return crypt.crypt(plaintext_password, salt)


class Context:
    def __init__(self, args):
        self.config = self.load_config()
        self.args = args
        self.baseiso = os.path.join(self.config["iso"]["basedir"],
                                    self.config["iso"]["release"][args.release])
        self.curdir = os.getcwd()
        self.iso = f'{self.curdir}/{args.release}-test.iso'
        self.hostname = f'{args.release}-test'
        self.target = f'{self.curdir}/{self.hostname}.img'
        password = salted_crypt('ubuntu')
        self.cloudconfig = f'''\
#cloud-config
autoinstall:
    version: 1
    identity:
        hostname: {self.hostname}
        password: "{password}"
        username: ubuntu
'''

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


parser = argparse.ArgumentParser()
parser.add_argument('-r', '--release', default='hirsute', action='store',
                    help='target release')
parser.add_argument('-a', '--autoinstall', default='', action='store',
                    help='merge supplied dict into default autoinstall')
subparsers = parser.add_subparsers(required=True)
scparsers = {}


def subcmd(fn):
    name = fn.__name__
    scparsers[name] = scparser = subparsers.add_parser(name)
    scparser.set_defaults(func=fn)
    return fn


def add_argument(name, *args, **kwargs):
    scparsers[name].add_argument(*args, **kwargs)


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
        return os.waitstatus_to_exitcode()
    if os.WIFEXITED(waitstatus):
        return os.WEXITSTATUS(waitstatus)
    if os.WIFSIGNALED(waitstatus):
        return -os.WTERMSIG(waitstatus)

    raise ValueError


class SubProcessFailure(Exception):
    pass


def run(cmds):
    for cmd in [cmd.strip() for cmd in cmds.splitlines()]:
        if len(cmd) < 1:
            continue
        # semi-simulate "bash -x"
        print(f'+ {cmd}')
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
def mounter(src, dest):
    run(f'sudo mount -r {src} {dest}')
    try:
        yield
    finally:
        run(f'sudo umount {dest}')


@subcmd
def build(ctx):
    run('sudo -v')
    run(f'rm -f {ctx.iso}')
    if ctx.args.quick:
        run(f'sudo ./scripts/quick-test-this-branch.sh {ctx.baseiso} {ctx.iso}')
    else:
        cleanarg = ''
        if not ctx.args.clean:
            cleanarg = 'subiquity'
        with delete_later('subiquity_test.snap') as snap:
            run(f'''
                snapcraft clean --use-lxd {cleanarg}
                snapcraft snap --use-lxd --output {snap}
                test -f {snap}
                sudo ./scripts/inject-subiquity-snap.sh {ctx.baseiso} {snap} \
                    {ctx.iso}
                ''')
    run(f'test -f {ctx.iso}')


add_argument('build', '-q', '--quick', default=False, action='store_true',
             help='build iso with quick-test-this-branch')
add_argument('build', '-c', '--clean', default=False, action='store_true',
             help='agressively clean the snapcraft build env')


def write(dest, data):
    with open(dest, 'w') as destfile:
        destfile.write(data)


def touch(dest):
    with open(dest, 'w'):
        pass


def create_seed(ctx, tempdir):
    write(f'{tempdir}/user-data', ctx.cloudconfig)
    touch(f'{tempdir}/meta-data')
    seed = f'{tempdir}/seed.iso'
    run(f'cloud-localds {seed} {tempdir}/user-data {tempdir}/meta-data')
    return seed


def drive(path, cache=False):
    cparam = 'none' if not cache else 'writethrough'
    return f'-drive file={path},format=raw,cache={cparam},if=virtio'


@subcmd
def install(ctx):
    if os.path.exists(ctx.target):
        if not ctx.args.overwrite:
            print('install refused: will not overwrite existing image')
            sys.exit(1)
        else:
            os.remove(ctx.target)

    run('sudo -v')

    with tempfile.TemporaryDirectory() as tempdir:
        mntdir = f'{tempdir}/mnt'
        os.mkdir(mntdir)

        kvm = f'kvm -no-reboot -m 1024 \
                {drive(ctx.target)} \
                -cdrom {ctx.iso} \
                -kernel {mntdir}/casper/vmlinuz \
                -initrd {mntdir}/casper/initrd'

        if not ctx.args.interactive:
            seed = create_seed(ctx, tempdir)
            kvm += f' {drive(seed, True)} -append autoinstall'

        run(f'truncate -s 10G {ctx.target}')
        with mounter(ctx.iso, mntdir):
            run(kvm)


add_argument('install', '-o', '--overwrite', default=False, action='store_true',
             help='allow overwrite of the target image')
add_argument('install', '-i', '--interactive', default=False,
             action='store_true',
             help='inhibit autoinstall')


@subcmd
def boot(ctx):
    run(f'kvm -no-reboot -m 1024 {drive(ctx.target)}')


@subcmd
def help(ctx):
    parser.print_usage()
    sys.exit(1)


try:
    ctx = Context(parser.parse_args())
except TypeError:
    help()
ctx.args.func(ctx)
