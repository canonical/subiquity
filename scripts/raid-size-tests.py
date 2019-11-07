#!/usr/bin/python3

# The fine details of how big a RAID device ends up as a function of the sizes
# of its components is somewhat hairier than one might think, with a certain
# fraction of each component device being given over to metadata storage. This
# script tests the estimates subiquity uses against reality by creating actual
# raid devices (backed by sparse files in a tmpfs) and comparing their sizes
# with the estimates. It must be run as root.

import os
import random
import subprocess
import sys
import tempfile
import uuid


from subiquity.models.filesystem import (
    align_down,
    dehumanize_size,
    get_raid_size,
    humanize_size,
    raidlevels,
    )
from subiquity.models.tests.test_filesystem import (
    FakeDev,
    )


tmpdir = tempfile.mkdtemp()

def run(cmd):
    try:
        subprocess.run(
            cmd, check=True,
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        raise

raids = []
loopdevs = []

def cleanraids():
    for raid in raids:
        run(['mdadm', '--verbose', '--stop', raid])
    del raids[:]

def cleanloops():
    for loopdev in loopdevs:
        subprocess.run(
            ['losetup', '-d', loopdev])
    del loopdevs[:]

def cleanup():
    cleanraids()
    cleanloops()


def create_devices_for_sizes(sizes):
    devs = []
    for size in sizes:
        fd, name = tempfile.mkstemp(dir=tmpdir)
        os.ftruncate(fd, size)
        os.close(fd)
        dev = subprocess.run(
            ['losetup', '-f', '--show', name],
            stdout=subprocess.PIPE, encoding='ascii').stdout.strip()
        devs.append(dev)
        loopdevs.append(dev)
    return devs


def create_raid(level, images):
    name = '/dev/md/test-{}'.format(uuid.uuid4())
    cmd = [
        'mdadm',
        '--verbose',
        '--create',
        '--metadata', 'default',
        '--level', level,
        '--run',
        '-n', str(len(images)),
        '--assume-clean',
        name,
        ] + images
    run(cmd)
    raids.append(name)
    return name


def get_real_raid_size(raid):
    return int(subprocess.run(
        ['blockdev', '--getsize64', raid],
        stdout=subprocess.PIPE, encoding='ascii').stdout.strip())


def verify_size_ok(level, sizes):
    r = False
    try:
        devs = create_devices_for_sizes(sizes)
        raid = create_raid(level, devs)
        devs = [FakeDev(size) for size in sizes]
        calc_size = get_raid_size(level, devs)
        real_size = get_real_raid_size(raid)
        if len(set(sizes)) == 1:
            sz = '[{}]*{}'.format(humanize_size(sizes[0]), len(sizes))
        else:
            sz = str([humanize_size(s) for s in sizes])
        print("level {} sizes {} -> calc_size {} real_size {}".format(
            level, sz , calc_size, real_size), end=' ')
        if calc_size > real_size:
            print("BAAAAAAAAAAAD", real_size - calc_size)
            if os.environ.get('DEBUG'):
                print(raid)
                input('waiting: ')
        elif calc_size == real_size:
            print("exactly right!")
            r = True
        else:
            print("subiquity wasted space", real_size - calc_size)
            r = True
    finally:
        cleanup()
    return r


fails = 0
run(['mount', '-t', 'tmpfs', 'tmpfs', tmpdir])
try:
    for size in '1G', '10G', '100G', '1T', '10T':
        size = dehumanize_size(size)
        for level in raidlevels:
            for count in range(2, 10):
                if count >= level.min_devices:
                    if not verify_size_ok(level.value, [size]*count):
                        fails += 1
                    if not verify_size_ok(level.value, [align_down(random.randrange(size, 10*size))]*count):
                        fails += 1
                    sizes = [align_down(random.randrange(size, 10*size)) for _ in range(count)]
                    if not verify_size_ok(level.value, sizes):
                        fails += 1
finally:
    run(['umount', '-l', tmpdir])

if fails > 0:
    print("{} fails".format(fails))
    sys.exit(1)
else:
    print("all ok!!")
