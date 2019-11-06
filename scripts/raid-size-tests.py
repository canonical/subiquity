#!/usr/bin/python3

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

import attr

from subiquity.models.filesystem import (
    dehumanize_size,
    get_raid_size,
    humanize_size,
    raidlevels,
    )


tmpdir = tempfile.mkdtemp()

raids = []
loopdevs = []

_cmdoutput = []

def run(cmd):
    try:
        subprocess.run(
            cmd, check=True,
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        raise


def cleanup():
    for raid in raids:
        subprocess.run(
            ['mdadm', '--verbose', '--stop', raid])
    for loopdev in loopdevs:
        subprocess.run(
            ['losetup', '-d', loopdev])
    shutil.rmtree(tmpdir)


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
    name = '/dev/md/{}'.format(uuid.uuid4())
    cmd = [
        'mdadm',
        '--verbose',
        '--create',
        '--metadata', 'default',
        '--level', level,
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


@attr.s
class FakeDev:
    size = attr.ib()


def verify_size_ok(level, sizes):
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
        r = False
    else:
        print("OK by", real_size - calc_size)
        r = True
    run(['mdadm', '--verbose', '--stop', raid])
    raids.remove(raid)
    return r


fails = 0
for size in '1G', '10G', '100G', '1T', '10T', '100T':
    size = dehumanize_size(size)
    for level in raidlevels:
        for count in range(2, 10):
            if count >= level.min_devices:
                if not verify_size_ok(level.value, [size]*count):
                    fails += 1

if fails > 0:
    print("{} fails".format(fails))
    sys.exit(1)
else:
    print("all ok!!")
